from flask import Blueprint, request, jsonify, current_app, render_template, abort, redirect, url_for
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_login import login_required
from models import db, Vehicle, VehicleImage, User, Reservation
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from marshmallow import Schema, fields as ma_fields, validate
import uuid
import mimetypes
import io
from PIL import Image

# Tentative d'import de python-magic avec fallback
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    print("Warning: python-magic not available. Using alternative file validation.")

# Création du blueprint
vehicles_bp = Blueprint('vehicles', __name__)

# Route pour la liste des véhicules
@vehicles_bp.route('/')
def index():
    # Récupération des filtres
    marque = request.args.get('marque')
    prix_min = request.args.get('prix_min', type=float)
    prix_max = request.args.get('prix_max', type=float)
    annee = request.args.get('annee', type=int)

    # Construction de la requête
    query = Vehicle.query

    if marque:
        query = query.filter(Vehicle.marque == marque)
    if prix_min is not None:
        query = query.filter(Vehicle.prix_jour >= prix_min)
    if prix_max is not None:
        query = query.filter(Vehicle.prix_jour <= prix_max)
    if annee:
        query = query.filter(Vehicle.annee == annee)

    # Récupération des véhicules
    vehicles = query.all()

    # Récupération des filtres disponibles
    marques = db.session.query(Vehicle.marque).distinct().all()
    marques = [m[0] for m in marques if m[0]]

    annees = db.session.query(Vehicle.annee).distinct().all()
    annees = [a[0] for a in annees if a[0]]
    annees.sort(reverse=True)

    return render_template('vehicles/list.html',
                         vehicles=vehicles,
                         marques=marques,
                         annees=annees,
                         selected_marque=marque,
                         selected_prix_min=prix_min,
                         selected_prix_max=prix_max,
                         selected_annee=annee)

# Route pour les détails d'un véhicule
@vehicles_bp.route('/<int:id>')
def detail(id):
    vehicle = Vehicle.query.get_or_404(id)
    return render_template('vehicles/detail.html', vehicle=vehicle)

# Création du namespace pour la documentation Swagger
api = Namespace('vehicles', description='Opérations sur les véhicules')

# Modèle pour la documentation Swagger
vehicle_model = api.model('Vehicle', {
    'id': fields.Integer(readonly=True),
    'marque': fields.String(required=True, description='Marque du véhicule'),
    'modele': fields.String(required=True, description='Modèle du véhicule'),
    'annee': fields.Integer(required=True, description='Année du véhicule'),
    'description': fields.String(description='Description du véhicule'),
    'prix_journalier': fields.Float(required=True, description='Prix journalier du véhicule'),
    'statut': fields.String(description='Statut du véhicule (disponible, reserve, vendu)'),
    'images': fields.List(fields.Raw, description='Liste des images du véhicule (objets {id, filename, url} en sortie, URLs en entrée)'),
    'date_ajout': fields.DateTime(readonly=True)
})

# Schéma de validation
class VehicleSchema(Schema):
    marque = ma_fields.String(required=True, validate=validate.Length(min=1, max=50))
    modele = ma_fields.String(required=True, validate=validate.Length(min=1, max=50))
    annee = ma_fields.Integer(required=True, validate=validate.Range(min=1900, max=datetime.now().year))
    description = ma_fields.String(validate=validate.Length(max=500))
    prix_journalier = ma_fields.Float(required=True, validate=validate.Range(min=0))
    statut = ma_fields.String(validate=validate.OneOf(['disponible', 'reserve', 'vendu']))
    images = ma_fields.List(ma_fields.String())

vehicle_schema = VehicleSchema()

def validate_image(file):
    """Validate image file using available methods"""
    if not file:
        return False, "Aucun fichier n'a été fourni"

    # Vérification de la taille
    if len(file.read()) > 16 * 1024 * 1024:  # 16MB
        file.seek(0)
        return False, "Le fichier est trop volumineux (max 16MB)"

    # Vérification du type MIME
    file.seek(0)
    if MAGIC_AVAILABLE:
        mime = magic.from_buffer(file.read(2048), mime=True)
    else:
        # Fallback: utiliser mimetypes
        mime = mimetypes.guess_type(file.filename)[0]

    file.seek(0)
    allowed_types = ['image/jpeg', 'image/png', 'image/gif']
    if not mime or mime not in allowed_types:
        return False, f"Type de fichier non autorisé. Types acceptés: {', '.join(allowed_types)}"

    # Vérification de l'intégrité de l'image
    file.seek(0)
    try:
        Image.open(file).verify()
        file.seek(0)
    except Exception as e:
        return False, f"Fichier image corrompu: {str(e)}"

    return True, mime

def process_image(file, filename):
    """Traite et optimise l'image"""
    try:
        img = Image.open(file)
        
        # Redimensionner l'image si elle est trop grande
        max_size = (1920, 1080)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convertir en RGB si nécessaire
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Sauvegarder l'image optimisée
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        return output
    except Exception as e:
        current_app.logger.error(f"Erreur lors du traitement de l'image: {str(e)}")
        return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def admin_required():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    if not user.is_admin:
        return {'message': 'Accès non autorisé'}, 403
    return None

@api.route('/')
class VehicleList(Resource):
    @api.doc('list_vehicles')
    @api.marshal_list_with(vehicle_model)
    def get(self):
        """Liste tous les véhicules"""
        try:
            vehicles = Vehicle.query.all()
            if not vehicles:
                return [], 200
            return [vehicle.to_dict() for vehicle in vehicles]
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la récupération des véhicules: {str(e)}")
            api.abort(500, f"Erreur lors de la récupération des véhicules: {str(e)}")

    @api.doc('create_vehicle')
    @api.expect(vehicle_model)
    @api.marshal_with(vehicle_model, code=201)
    @jwt_required()
    def post(self):
        """Crée un nouveau véhicule"""
        try:
            if error := admin_required():
                return error

            data = request.get_json()
            if not data:
                return {'message': 'Aucune donnée fournie'}, 400

            errors = vehicle_schema.validate(data)
            if errors:
                return {'message': 'Données invalides', 'errors': errors}, 400

            # Vérification des conflits de nom
            existing_vehicle = Vehicle.query.filter_by(
                marque=data['marque'],
                modele=data['modele'],
                annee=data['annee']
            ).first()
            
            if existing_vehicle:
                return {'message': 'Un véhicule identique existe déjà'}, 400

            vehicle = Vehicle(
                marque=data['marque'],
                modele=data['modele'],
                annee=data['annee'],
                description=data.get('description'),
                prix_journalier=data['prix_journalier'],
                statut=data.get('statut', 'disponible'),
            )
            db.session.add(vehicle)
            db.session.flush()

            for image_url in data.get('images', []):
                db.session.add(VehicleImage(vehicle_id=vehicle.id, filename=image_url))

            db.session.commit()
            return vehicle.to_dict(), 201
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur lors de la création du véhicule: {str(e)}")
            api.abort(400, f"Erreur lors de la création du véhicule: {str(e)}")

@api.route('/filters')
class VehicleFilters(Resource):
    @api.doc('get_vehicle_filters')
    @api.response(200, 'Filtres récupérés avec succès')
    def get(self):
        """Récupérer les filtres disponibles pour les véhicules"""
        try:
            # Récupérer les marques distinctes
            brands = db.session.query(Vehicle.marque).distinct().all()
            brands = [brand[0] for brand in brands if brand[0]]

            # Récupérer les années distinctes
            years = db.session.query(Vehicle.annee).distinct().all()
            years = [year[0] for year in years if year[0]]

            return {
                'brands': brands,
                'years': years
            }, 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la récupération des filtres: {str(e)}")
            return {'message': 'Une erreur est survenue lors de la récupération des filtres'}, 500

@api.route('/<int:id>')
@api.param('id', 'Identifiant du véhicule')
@api.response(404, 'Véhicule non trouvé')
class VehicleResource(Resource):
    @api.doc('get_vehicle')
    @api.marshal_with(vehicle_model)
    def get(self, id):
        """Récupère un véhicule par son ID"""
        try:
            vehicle = Vehicle.query.get_or_404(id)
            return vehicle.to_dict()
        except Exception as e:
            api.abort(404, f"Véhicule non trouvé: {str(e)}")

    @api.doc('update_vehicle')
    @api.expect(vehicle_model)
    @api.marshal_with(vehicle_model)
    @jwt_required()
    def put(self, id):
        """Met à jour un véhicule"""
        try:
            if error := admin_required():
                return error

            vehicle = Vehicle.query.get_or_404(id)
            data = request.get_json()
            
            vehicle.marque = data.get('marque', vehicle.marque)
            vehicle.modele = data.get('modele', vehicle.modele)
            vehicle.annee = data.get('annee', vehicle.annee)
            vehicle.description = data.get('description', vehicle.description)
            vehicle.prix_journalier = data.get('prix_journalier', vehicle.prix_journalier)
            vehicle.statut = data.get('statut', vehicle.statut)

            if 'images' in data:
                VehicleImage.query.filter_by(vehicle_id=vehicle.id).delete()
                for image_url in data['images']:
                    db.session.add(VehicleImage(vehicle_id=vehicle.id, filename=image_url))

            db.session.commit()
            return vehicle.to_dict()
        except Exception as e:
            db.session.rollback()
            api.abort(400, f"Erreur lors de la mise à jour du véhicule: {str(e)}")

    @api.doc('delete_vehicle')
    @api.response(204, 'Véhicule supprimé')
    @jwt_required()
    def delete(self, id):
        """Supprime un véhicule"""
        try:
            if error := admin_required():
                return error

            vehicle = Vehicle.query.get_or_404(id)
            
            # Suppression des images
            for image in vehicle.images:
                image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            db.session.delete(vehicle)
            db.session.commit()
            return '', 204
        except Exception as e:
            db.session.rollback()
            api.abort(400, f"Erreur lors de la suppression du véhicule: {str(e)}")

@api.route('/<int:id>/upload')
@api.param('id', 'Identifiant du véhicule')
class VehicleImageUpload(Resource):
    @api.doc('upload_vehicle_image', security='Bearer Auth')
    @api.response(201, 'Image téléchargée avec succès')
    @api.response(400, 'Erreur lors du téléchargement')
    @api.response(401, 'Non authentifié')
    @api.response(403, 'Accès non autorisé')
    @jwt_required()
    def post(self, id):
        """Télécharge une image pour un véhicule"""
        try:
            if error := admin_required():
                return error

            vehicle = Vehicle.query.get_or_404(id)
            
            if 'image' not in request.files:
                current_app.logger.error('Aucune image fournie dans la requête')
                return {'message': 'Aucune image fournie'}, 400
                
            file = request.files['image']
            if not file:
                current_app.logger.error('Fichier vide')
                return {'message': 'Fichier vide'}, 400

            # Validation de l'image
            is_valid, error_message = validate_image(file)
            if not is_valid:
                return {'message': error_message}, 400

            # Traitement de l'image
            processed_image = process_image(file, file.filename)
            if not processed_image:
                return {'message': 'Erreur lors du traitement de l\'image'}, 400

            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            # Sauvegarde de l'image optimisée
            with open(filepath, 'wb') as f:
                f.write(processed_image.getvalue())
            
            # Ajout de l'image à la liste des images du véhicule
            if vehicle.images is None:
                vehicle.images = []
            vehicle.images.append(filename)
            
            db.session.commit()
            return {'message': 'Image téléchargée avec succès', 'filename': filename}, 201
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Erreur lors du téléchargement: {str(e)}')
            return {'message': f'Erreur lors du téléchargement de l\'image: {str(e)}'}, 500 
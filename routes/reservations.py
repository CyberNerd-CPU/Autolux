from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restx import Resource, fields, Namespace
from flask_login import login_required, current_user
from models import db, User, Vehicle, Reservation
from schemas import ReservationSchema
from datetime import datetime, timedelta
from marshmallow import Schema, fields as ma_fields, validate
from functools import wraps

reservations_bp = Blueprint('reservations', __name__)
api = Namespace('reservations', description='Opérations sur les réservations')
reservation_schema = ReservationSchema()

# Modèles Swagger
reservation_model = api.model('Reservation', {
    'id': fields.Integer(readonly=True),
    'user_id': fields.Integer(readonly=True),
    'vehicle_id': fields.Integer(required=True, description='ID du véhicule'),
    'date_debut': fields.DateTime(required=True, description='Date de début de réservation'),
    'date_fin': fields.DateTime(required=True, description='Date de fin de réservation'),
    'statut': fields.String(readonly=True, description='Statut de la réservation (en_attente, confirmee, annulee)'),
    'created_at': fields.DateTime(readonly=True)
})

# Schéma de validation
class ReservationCreateSchema(Schema):
    vehicle_id = ma_fields.Integer(required=True)
    date_debut = ma_fields.DateTime(required=True)
    date_fin = ma_fields.DateTime(required=True)

reservation_create_schema = ReservationCreateSchema()

def validate_dates(date_debut, date_fin):
    if date_debut >= date_fin:
        return False, "La date de fin doit être postérieure à la date de début"
    if date_debut < datetime.now():
        return False, "La date de début doit être dans le futur"
    if (date_fin - date_debut) > timedelta(days=30):
        return False, "La durée maximale de réservation est de 30 jours"
    return True, None

def calculate_price(vehicle, date_debut, date_fin):
    days = (date_fin - date_debut).days
    return vehicle.prix_journalier * days

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return {'message': 'Accès non autorisé'}, 403
            
        return fn(*args, **kwargs)
    return wrapper

@api.route('/')
class ReservationList(Resource):
    @api.doc('create_reservation', security='Bearer Auth')
    @api.expect(reservation_model)
    @api.response(201, 'Réservation créée avec succès')
    @api.response(400, 'Données invalides')
    @api.response(401, 'Non authentifié')
    @jwt_required()
    def post(self):
        """Créer une nouvelle réservation"""
        try:
            user_id = get_jwt_identity()
            data = request.get_json()
            
            # Validation des données
            errors = reservation_create_schema.validate(data)
            if errors:
                return {'message': 'Données invalides', 'errors': errors}, 400
            
            # Vérifier si le véhicule est disponible
            vehicle = Vehicle.query.get_or_404(data['vehicle_id'])
            if vehicle.statut != 'disponible':
                return {'message': 'Véhicule non disponible'}, 400
                
            # Conversion et validation des dates
            date_debut = datetime.fromisoformat(data['date_debut'].replace('Z', '+00:00'))
            date_fin = datetime.fromisoformat(data['date_fin'].replace('Z', '+00:00'))
            
            is_valid, error_message = validate_dates(date_debut, date_fin)
            if not is_valid:
                return {'message': error_message}, 400
                
            # Vérifier les conflits de réservation
            existing_reservation = Reservation.query.filter(
                Reservation.vehicle_id == data['vehicle_id'],
                Reservation.statut != 'annulee',
                ((Reservation.date_debut <= date_debut) & (Reservation.date_fin >= date_debut)) |
                ((Reservation.date_debut <= date_fin) & (Reservation.date_fin >= date_fin))
            ).first()
            
            if existing_reservation:
                return {'message': 'Véhicule déjà réservé pour ces dates'}, 400
            
            # Calcul du prix total
            prix_total = calculate_price(vehicle, date_debut, date_fin)
            
            reservation = Reservation(
                user_id=user_id,
                vehicle_id=data['vehicle_id'],
                date_debut=date_debut,
                date_fin=date_fin,
                statut='en_attente'
            )
            
            db.session.add(reservation)
            db.session.commit()
            
            return reservation_schema.dump(reservation), 201
            
        except Exception as e:
            db.session.rollback()
            return {'message': f'Erreur lors de la création de la réservation: {str(e)}'}, 500

    @api.doc('list_user_reservations', security='Bearer Auth')
    @api.marshal_list_with(reservation_model)
    @api.response(401, 'Non authentifié')
    @jwt_required()
    def get(self):
        """Liste les réservations de l'utilisateur connecté"""
        try:
            user_id = get_jwt_identity()
            reservations = Reservation.query.filter_by(user_id=user_id).all()
            return reservation_schema.dump(reservations, many=True)
        except Exception as e:
            return {'message': f'Erreur lors de la récupération des réservations: {str(e)}'}, 500

@api.route('/admin')
class AdminReservationList(Resource):
    @api.doc('list_all_reservations', security='Bearer Auth')
    @api.marshal_list_with(reservation_model)
    @api.response(401, 'Non authentifié')
    @api.response(403, 'Accès non autorisé')
    @jwt_required()
    @admin_required
    def get(self):
        """Liste toutes les réservations (admin uniquement)"""
        try:
            reservations = Reservation.query.all()
            return reservation_schema.dump(reservations, many=True)
        except Exception as e:
            return {'message': f'Erreur lors de la récupération des réservations: {str(e)}'}, 500

@api.route('/<int:id>/status')
@api.param('id', 'Identifiant de la réservation')
class ReservationStatus(Resource):
    @api.doc('update_reservation_status', security='Bearer Auth')
    @api.response(200, 'Statut mis à jour avec succès')
    @api.response(401, 'Non authentifié')
    @api.response(403, 'Accès non autorisé')
    @api.response(404, 'Réservation non trouvée')
    @jwt_required()
    @admin_required
    def put(self, id):
        """Met à jour le statut d'une réservation (admin uniquement)"""
        try:
            reservation = Reservation.query.get_or_404(id)
            data = request.get_json()
            
            if 'statut' not in data:
                return {'message': 'Statut non fourni'}, 400
                
            if data['statut'] not in ['en_attente', 'confirmee', 'annulee']:
                return {'message': 'Statut invalide'}, 400
                
            reservation.statut = data['statut']
            
            # Mise à jour du statut du véhicule si nécessaire
            vehicle = Vehicle.query.get(reservation.vehicle_id)
            if data['statut'] == 'confirmee':
                vehicle.statut = 'reserve'
            elif data['statut'] == 'annulee' and vehicle.statut == 'reserve':
                vehicle.statut = 'disponible'
                
            db.session.commit()
            return reservation_schema.dump(reservation)
            
        except Exception as e:
            db.session.rollback()
            return {'message': f'Erreur lors de la mise à jour du statut: {str(e)}'}, 500

# Routes web
@reservations_bp.route('/')
@login_required
def list():
    """Liste les réservations de l'utilisateur connecté"""
    reservations = Reservation.query.filter_by(user_id=current_user.id).all()
    return render_template('reservations/list.html', reservations=reservations)

@reservations_bp.route('/create/<int:vehicle_id>', methods=['GET', 'POST'])
@login_required
def create(vehicle_id):
    """Crée une nouvelle réservation"""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    
    if request.method == 'POST':
        date_debut = datetime.strptime(request.form.get('date_debut'), '%Y-%m-%d')
        date_fin = datetime.strptime(request.form.get('date_fin'), '%Y-%m-%d')
        
        is_valid, error_message = validate_dates(date_debut, date_fin)
        if not is_valid:
            flash(error_message, 'error')
            return render_template('reservations/create.html', vehicle=vehicle, now=datetime.now())
        
        # Vérifier les conflits de réservation
        existing_reservation = Reservation.query.filter(
            Reservation.vehicle_id == vehicle_id,
            Reservation.statut != 'annulee',
            ((Reservation.date_debut <= date_debut) & (Reservation.date_fin >= date_debut)) |
            ((Reservation.date_debut <= date_fin) & (Reservation.date_fin >= date_fin))
        ).first()
        
        if existing_reservation:
            flash('Véhicule déjà réservé pour ces dates', 'error')
            return render_template('reservations/create.html', vehicle=vehicle, now=datetime.now())
        
        # Calcul du prix total
        prix_total = calculate_price(vehicle, date_debut, date_fin)
        
        reservation = Reservation(
            user_id=current_user.id,
            vehicle_id=vehicle_id,
            date_debut=date_debut,
            date_fin=date_fin,
            statut='en_attente'
        )
        
        db.session.add(reservation)
        db.session.commit()
        
        flash('Réservation créée avec succès', 'success')
        return redirect(url_for('reservations.list'))
    
    return render_template('reservations/create.html', vehicle=vehicle, now=datetime.now())

@reservations_bp.route('/<int:id>')
@login_required
def detail(id):
    """Affiche les détails d'une réservation"""
    reservation = Reservation.query.get_or_404(id)
    
    # Vérifier que l'utilisateur est autorisé à voir cette réservation
    if reservation.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    return render_template('reservations/detail.html', reservation=reservation)

@reservations_bp.route('/<int:id>/cancel')
@login_required
def cancel(id):
    """Annule une réservation"""
    reservation = Reservation.query.get_or_404(id)
    
    # Vérifier que l'utilisateur est autorisé à annuler cette réservation
    if reservation.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    if reservation.statut != 'en_attente':
        flash('Cette réservation ne peut pas être annulée', 'error')
        return redirect(url_for('reservations.detail', id=id))
    
    reservation.statut = 'annulee'
    
    # Mettre à jour le statut du véhicule si nécessaire
    vehicle = Vehicle.query.get(reservation.vehicle_id)
    if vehicle.statut == 'reserve':
        vehicle.statut = 'disponible'
    
    db.session.commit()
    
    flash('Réservation annulée avec succès', 'success')
    return redirect(url_for('reservations.list'))

reservations_bp.add_url_rule('/', view_func=ReservationList.as_view('reservation_list'))
reservations_bp.add_url_rule('/admin', view_func=AdminReservationList.as_view('admin_reservation_list'))
reservations_bp.add_url_rule('/<int:id>/status', view_func=ReservationStatus.as_view('reservation_status')) 
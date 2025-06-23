from flask import Blueprint, request, jsonify, current_app, render_template, abort, redirect, url_for, flash
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_login import login_required, current_user
from models import db, Vehicle, User, Reservation, VehicleImage
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from marshmallow import Schema, fields as ma_fields, validate
import uuid
import mimetypes
import io
from PIL import Image
from functools import wraps
from config import Config

# Tentative d'import de python-magic avec fallback
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    print("Warning: python-magic not available. Using alternative file validation.")

# Création du blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Accès non autorisé', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    # Statistiques
    total_users = User.query.count()
    total_vehicles = Vehicle.query.count()
    total_reservations = Reservation.query.count()
    
    # Revenus des 30 derniers jours
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_reservations = Reservation.query.filter(
        Reservation.date_debut >= thirty_days_ago,
        Reservation.statut == 'confirmee'
    ).all()
    
    total_revenue = sum(
        reservation.calculate_total_price()
        for reservation in recent_reservations
    )
    
    # Dernières réservations
    latest_reservations = Reservation.query.order_by(
        Reservation.created_at.desc()
    ).limit(5).all()
    
    # Véhicules les plus réservés
    popular_vehicles = db.session.query(
        Vehicle,
        db.func.count(Reservation.id).label('reservation_count')
    ).join(Reservation).group_by(Vehicle.id).order_by(
        db.desc('reservation_count')
    ).limit(5).all()
    
    return render_template('admin/dashboard.html',
        total_users=total_users,
        total_vehicles=total_vehicles,
        total_reservations=total_reservations,
        total_revenue=total_revenue,
        latest_reservations=latest_reservations,
        popular_vehicles=popular_vehicles,
        now=datetime.now()
    )

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, now=datetime.now())

@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        user.nom = request.form.get('nom')
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        
        if request.form.get('password'):
            user.set_password(request.form.get('password'))
            
        db.session.commit()
        flash('Utilisateur mis à jour avec succès', 'success')
        return redirect(url_for('admin.users'))
        
    return render_template('admin/edit_user.html', user=user, now=datetime.now())

@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte', 'danger')
        return redirect(url_for('admin.users'))
        
    db.session.delete(user)
    db.session.commit()
    flash('Utilisateur supprimé avec succès', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/vehicles')
@login_required
@admin_required
def vehicles():
    vehicles = Vehicle.query.order_by(Vehicle.date_ajout.desc()).all()
    return render_template('admin/vehicles.html', vehicles=vehicles, now=datetime.now())

@admin_bp.route('/vehicles/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_vehicle():
    if request.method == 'POST':
        try:
            vehicle = Vehicle(
                marque=request.form.get('marque'),
                modele=request.form.get('modele'),
                annee=int(request.form.get('annee')),
                description=request.form.get('description'),
                prix_journalier=float(request.form.get('prix_journalier')),
                statut=request.form.get('statut')
            )
            
            # Gestion des images
            images = request.files.getlist('images')
            
            for image in images:
                if image and image.filename:
                    # Générer un nom de fichier unique et sécurisé
                    original_filename = secure_filename(image.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
                    image_path = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
                    
                    # Sauvegarder l'image
                    image.save(image_path)
                    
                    # Créer une nouvelle instance de VehicleImage
                    vehicle_image = VehicleImage(
                        vehicle=vehicle,
                        filename=unique_filename
                    )
                    db.session.add(vehicle_image)
            
            db.session.add(vehicle)
            db.session.commit()
            
            flash('Véhicule ajouté avec succès', 'success')
            return redirect(url_for('admin.vehicles'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur lors de l'ajout du véhicule: {str(e)}")
            flash('Une erreur est survenue lors de l\'ajout du véhicule', 'error')
            return redirect(url_for('admin.new_vehicle'))
        
    return render_template('admin/new_vehicle.html', now=datetime.now())

@admin_bp.route('/vehicles/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_vehicle(id):
    vehicle = Vehicle.query.get_or_404(id)
    if request.method == 'POST':
        try:
            vehicle.marque = request.form.get('marque')
            vehicle.modele = request.form.get('modele')
            vehicle.annee = int(request.form.get('annee'))
            vehicle.description = request.form.get('description')
            vehicle.prix_journalier = float(request.form.get('prix_journalier'))
            vehicle.statut = request.form.get('statut')
            
            # Gestion des nouvelles images
            images = request.files.getlist('images')
            if images and images[0].filename:
                # Supprimer les anciennes images
                for old_image in vehicle.images:
                    try:
                        image_path = os.path.join(Config.UPLOAD_FOLDER, old_image.filename)
                        if os.path.exists(image_path):
                            os.remove(image_path)
                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de la suppression de l'image {old_image.filename}: {str(e)}")
                
                # Supprimer les entrées de la base de données
                VehicleImage.query.filter_by(vehicle_id=vehicle.id).delete()
                
                # Sauvegarder les nouvelles images
                for image in images:
                    if image and image.filename:
                        # Générer un nom de fichier unique et sécurisé
                        original_filename = secure_filename(image.filename)
                        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
                        image_path = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
                        
                        # Sauvegarder l'image
                        image.save(image_path)
                        
                        # Créer une nouvelle instance de VehicleImage
                        vehicle_image = VehicleImage(
                            vehicle=vehicle,
                            filename=unique_filename
                        )
                        db.session.add(vehicle_image)
            
            db.session.commit()
            flash('Véhicule mis à jour avec succès', 'success')
            return redirect(url_for('admin.vehicles'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur lors de la mise à jour du véhicule: {str(e)}")
            flash('Une erreur est survenue lors de la mise à jour du véhicule', 'error')
            return redirect(url_for('admin.edit_vehicle', id=id))
        
    return render_template('admin/edit_vehicle.html', vehicle=vehicle, now=datetime.now())

@admin_bp.route('/vehicles/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_vehicle(id):
    vehicle = Vehicle.query.get_or_404(id)
    db.session.delete(vehicle)
    db.session.commit()
    flash('Véhicule supprimé avec succès', 'success')
    return redirect(url_for('admin.vehicles'))

@admin_bp.route('/reservations')
@login_required
@admin_required
def reservations():
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    return render_template('admin/reservations.html', reservations=reservations)

@admin_bp.route('/reservations/<int:id>/status', methods=['POST'])
@login_required
@admin_required
def update_reservation_status(id):
    reservation = Reservation.query.get_or_404(id)
    new_status = request.form.get('status')
    
    if new_status not in ['en_attente', 'confirmee', 'annulee']:
        flash('Statut invalide', 'danger')
        return redirect(url_for('admin.reservations'))
        
    reservation.statut = new_status
    
    # Mise à jour du statut du véhicule
    vehicle = Vehicle.query.get(reservation.vehicle_id)
    if new_status == 'confirmee':
        vehicle.statut = 'reserve'
    elif new_status == 'annulee' and vehicle.statut == 'reserve':
        vehicle.statut = 'disponible'
        
    db.session.commit()
    flash('Statut de la réservation mis à jour avec succès', 'success')
    return redirect(url_for('admin.reservations'))

@admin_bp.route('/reservations/<int:id>')
@login_required
@admin_required
def view_reservation(id):
    reservation = Reservation.query.get_or_404(id)
    return render_template('admin/view_reservation.html', reservation=reservation, now=datetime.now())

# Création du namespace pour la documentation Swagger
api = Namespace('admin', description='Opérations administratives')

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return jsonify({'message': 'Accès non autorisé'}), 403
            
        return fn(*args, **kwargs)
    return wrapper

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def get_users():
    """Récupère la liste de tous les utilisateurs"""
    try:
        users = User.query.all()
        return jsonify([{
            'id': user.id,
            'email': user.email,
            'nom': user.nom,
            'prenom': user.prenom,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat() if user.created_at else None
        } for user in users]), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/promote', methods=['PUT'])
@jwt_required()
@admin_required
def promote_user(user_id):
    """Promouvoir un utilisateur au rang d'administrateur"""
    try:
        user = User.query.get_or_404(user_id)
        user.is_admin = True
        db.session.commit()
        return jsonify({'message': 'Utilisateur promu avec succès'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400

@admin_bp.route('/users/<int:user_id>/demote', methods=['PUT'])
@jwt_required()
@admin_required
def demote_user(user_id):
    """Rétrograder un administrateur au rang d'utilisateur"""
    try:
        user = User.query.get_or_404(user_id)
        user.is_admin = False
        db.session.commit()
        return jsonify({'message': 'Utilisateur rétrogradé avec succès'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400 
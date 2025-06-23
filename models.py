from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import CheckConstraint, event
from config import Config
import os
from flask_login import UserMixin
from flask import url_for

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)
    login_attempts = db.Column(db.Integer, default=0)
    last_login_attempt = db.Column(db.DateTime)
    
    # Relations
    reservations = db.relationship('Reservation', backref='reservation_user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.nom}>'
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    def can_login(self):
        if self.login_attempts >= Config.MAX_LOGIN_ATTEMPTS:
            if self.last_login_attempt:
                time_diff = (datetime.utcnow() - self.last_login_attempt).total_seconds()
                if time_diff < Config.LOGIN_ATTEMPT_WINDOW:
                    return False
                self.login_attempts = 0
        return True
    
    def record_login_attempt(self, success):
        if success:
            self.login_attempts = 0
        else:
            self.login_attempts += 1
        self.last_login_attempt = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class VehicleImage(db.Model):
    __tablename__ = 'vehicle_images'
    
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<VehicleImage {self.filename}>'
    
    @property
    def url(self):
        """Retourne l'URL de l'image"""
        return url_for('uploaded_file', filename=self.filename, _external=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'vehicle_id': self.vehicle_id,
            'filename': self.filename,
            'url': self.url,
            'created_at': self.created_at.isoformat()
        }

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    marque = db.Column(db.String(50), nullable=False)
    modele = db.Column(db.String(50), nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    prix_journalier = db.Column(db.Float, nullable=False)
    statut = db.Column(db.String(20), default='disponible')
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    images = db.relationship('VehicleImage', backref='vehicle', lazy=True, cascade='all, delete-orphan')
    reservations = db.relationship('Reservation', backref='reservation_vehicle', lazy=True, cascade='all, delete-orphan')
    
    # Contraintes
    __table_args__ = (
        db.CheckConstraint('prix_journalier >= 0', name='check_prix_positif'),
        db.CheckConstraint('annee >= 1900', name='check_annee_min'),
        db.CheckConstraint("statut IN ('disponible', 'reserve', 'vendu')", name='check_statut_valide'),
    )
    
    def __repr__(self):
        return f'<Vehicle {self.marque} {self.modele}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'marque': self.marque,
            'modele': self.modele,
            'annee': self.annee,
            'description': self.description,
            'prix_journalier': self.prix_journalier,
            'statut': self.statut,
            'images': [image.to_dict() for image in self.images],
            'date_ajout': self.date_ajout.isoformat() if self.date_ajout else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def delete_images(self):
        """Supprime les fichiers images associés au véhicule"""
        for image in self.images:
            try:
                image_path = os.path.join(Config.UPLOAD_FOLDER, image.filename)
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                print(f"Erreur lors de la suppression de l'image {image.filename}: {str(e)}")

@event.listens_for(Vehicle, 'after_delete')
def delete_vehicle_images(mapper, connection, target):
    """Supprime les images associées au véhicule après sa suppression"""
    target.delete_images()

class Reservation(db.Model):
    __tablename__ = 'reservations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    date_debut = db.Column(db.DateTime, nullable=False)
    date_fin = db.Column(db.DateTime, nullable=False)
    statut = db.Column(db.String(20), default='en_attente')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Contraintes
    __table_args__ = (
        db.CheckConstraint("statut IN ('en_attente', 'confirmee', 'annulee')", name='check_statut_reservation'),
        db.CheckConstraint('date_fin > date_debut', name='check_dates_reservation'),
    )
    
    def __repr__(self):
        return f'<Reservation {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'vehicle_id': self.vehicle_id,
            'date_debut': self.date_debut.isoformat() if self.date_debut else None,
            'date_fin': self.date_fin.isoformat() if self.date_fin else None,
            'statut': self.statut,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def validate_dates(self):
        """Valide les dates de réservation"""
        if not self.date_debut or not self.date_fin:
            return False, "Les dates de début et de fin sont requises"
        
        if self.date_debut >= self.date_fin:
            return False, "La date de fin doit être postérieure à la date de début"
        
        if self.date_debut < datetime.utcnow():
            return False, "La date de début ne peut pas être dans le passé"
        
        # Limite la réservation à 30 jours maximum
        if (self.date_fin - self.date_debut).days > 30:
            return False, "La réservation ne peut pas dépasser 30 jours"
        
        return True, None

    def check_availability(self):
        """Vérifie si le véhicule est disponible pour la période demandée"""
        # Vérifie d'abord si le véhicule est disponible
        vehicle = Vehicle.query.get(self.vehicle_id)
        if not vehicle or vehicle.statut != 'disponible':
            return False, "Le véhicule n'est pas disponible"
        
        # Vérifie les conflits de réservation
        overlapping = Reservation.query.filter(
            Reservation.vehicle_id == self.vehicle_id,
            Reservation.statut != 'annulee',
            Reservation.date_debut <= self.date_fin,
            Reservation.date_fin >= self.date_debut
        ).first()
        
        if overlapping:
            return False, "Le véhicule est déjà réservé pour cette période"
        
        return True, None

    def calculate_total_price(self):
        """Calcule le prix total de la réservation"""
        vehicle = Vehicle.query.get(self.vehicle_id)
        if not vehicle:
            return 0
        
        days = (self.date_fin - self.date_debut).days
        return days * vehicle.prix_journalier 
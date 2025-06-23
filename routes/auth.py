from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_restx import Resource, fields, Namespace
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from schemas import UserSchema, UserRegisterSchema
from datetime import datetime, timedelta
from config import Config
from marshmallow import ValidationError
from functools import wraps
import re
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, RegistrationForm, ProfileForm

auth_bp = Blueprint('auth', __name__)
api = Namespace('auth', description='Opérations d\'authentification')
user_schema = UserSchema()
user_register_schema = UserRegisterSchema()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password):
    if len(password) < Config.PASSWORD_MIN_LENGTH:
        return False, f"Le mot de passe doit contenir au moins {Config.PASSWORD_MIN_LENGTH} caractères"
    if not re.search(r'[A-Z]', password):
        return False, "Le mot de passe doit contenir au moins une majuscule"
    if not re.search(r'[a-z]', password):
        return False, "Le mot de passe doit contenir au moins une minuscule"
    if not re.search(r'\d', password):
        return False, "Le mot de passe doit contenir au moins un chiffre"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial"
    return True, None

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return {'message': 'Accès non autorisé'}, 403
            
        return fn(*args, **kwargs)
    return wrapper

# Modèles Swagger
user_model = api.model('User', {
    'id': fields.Integer(readonly=True),
    'nom': fields.String(required=True, description='Nom de l\'utilisateur'),
    'email': fields.String(required=True, description='Email de l\'utilisateur'),
    'role': fields.String(readonly=True, description='Rôle de l\'utilisateur'),
    'date_inscription': fields.DateTime(readonly=True)
})

register_model = api.model('Register', {
    'nom': fields.String(required=True, description='Nom de l\'utilisateur'),
    'email': fields.String(required=True, description='Email de l\'utilisateur'),
    'password': fields.String(required=True, description='Mot de passe')
})

login_model = api.model('Login', {
    'email': fields.String(required=True, description='Email de l\'utilisateur'),
    'password': fields.String(required=True, description='Mot de passe')
})

token_model = api.model('Token', {
    'access_token': fields.String(description='Token JWT'),
    'refresh_token': fields.String(description='Refresh Token JWT')
})

@api.route('/register')
class Register(Resource):
    @api.expect(register_model)
    @api.response(201, 'Utilisateur créé avec succès')
    @api.response(400, 'Données invalides')
    def post(self):
        """Créer un nouveau compte utilisateur"""
        try:
            data = request.get_json()
            if not data:
                current_app.logger.error("Aucune donnée fournie dans la requête")
                return {'message': 'Aucune donnée fournie'}, 400

            current_app.logger.info(f"Tentative d'inscription avec les données: {data}")
            
            # Vérification des champs requis
            required_fields = ['nom', 'email', 'password']
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                current_app.logger.error(f"Champs manquants: {missing_fields}")
                return {
                    'message': 'Champs manquants',
                    'missing_fields': missing_fields,
                    'required_fields': required_fields
                }, 400

            # Validation de l'email
            if not validate_email(data['email']):
                return {'message': 'Format d\'email invalide'}, 400

            # Validation du mot de passe
            is_valid, password_error = validate_password(data['password'])
            if not is_valid:
                return {'message': password_error}, 400

            # Validation des données avec le schéma
            try:
                validated_data = user_register_schema.load(data)
            except ValidationError as err:
                current_app.logger.error(f"Erreurs de validation: {err.messages}")
                return {
                    'message': 'Données invalides',
                    'errors': err.messages
                }, 400
            
            # Vérification si l'email existe déjà
            existing_user = User.query.filter_by(email=validated_data['email']).first()
            if existing_user:
                current_app.logger.warning(f"Tentative d'inscription avec un email déjà utilisé: {validated_data['email']}")
                return {'message': 'Email déjà utilisé'}, 400
            
            # Création de l'utilisateur
            user = User(nom=validated_data['nom'], email=validated_data['email'])
            try:
                user.set_password(validated_data['password'])
            except ValueError as e:
                current_app.logger.warning(f"Mot de passe invalide: {str(e)}")
                return {'message': str(e)}, 400
            
            db.session.add(user)
            db.session.commit()
            
            current_app.logger.info(f"Utilisateur créé avec succès: {user.email}")
            
            # Création des tokens avec l'ID de l'utilisateur en tant que chaîne
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            
            return {
                'message': 'Compte créé avec succès',
                'user': user_schema.dump(user),
                'access_token': access_token,
                'refresh_token': refresh_token
            }, 201
            
        except Exception as e:
            current_app.logger.error(f"Erreur inattendue lors de l'inscription: {str(e)}")
            return {'message': 'Une erreur est survenue lors de la création du compte'}, 500

@api.route('/login')
class Login(Resource):
    @api.expect(login_model)
    @api.response(200, 'Connexion réussie', token_model)
    @api.response(401, 'Identifiants invalides')
    @api.response(429, 'Trop de tentatives de connexion')
    def post(self):
        """Se connecter et obtenir un token JWT"""
        try:
            data = request.get_json()
            if not data:
                return {'message': 'Aucune donnée fournie'}, 400

            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return {'message': 'Email et mot de passe requis'}, 400

            # Validation de l'email
            if not validate_email(email):
                return {'message': 'Format d\'email invalide'}, 400

            current_app.logger.info(f"Tentative de connexion pour l'email: {email}")
            
            user = User.query.filter_by(email=email).first()
            
            if not user:
                current_app.logger.warning(f"Tentative de connexion avec un email inexistant: {email}")
                return {'message': 'Email ou mot de passe incorrect'}, 401
                
            if not user.can_login():
                current_app.logger.warning(f"Trop de tentatives de connexion pour l'utilisateur: {email}")
                return {
                    'message': f'Trop de tentatives de connexion. Réessayez dans {Config.LOGIN_ATTEMPT_WINDOW} secondes'
                }, 429
                
            if not user.check_password(password):
                user.record_login_attempt(False)
                db.session.commit()
                current_app.logger.warning(f"Mot de passe incorrect pour l'utilisateur: {email}")
                return {'message': 'Email ou mot de passe incorrect'}, 401
                
            user.record_login_attempt(True)
            db.session.commit()
            
            # Création des tokens avec l'ID de l'utilisateur en tant que chaîne
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            
            current_app.logger.info(f"Connexion réussie pour l'utilisateur: {email}")
            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user_schema.dump(user)
            }, 200
            
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la connexion: {str(e)}")
            return {'message': 'Une erreur est survenue lors de la connexion'}, 500

@api.route('/refresh')
class Refresh(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Token rafraîchi avec succès', token_model)
    @api.response(401, 'Token invalide')
    @jwt_required(refresh=True)
    def post(self):
        """Rafraîchir le token JWT"""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            if not user:
                return {'message': 'Utilisateur non trouvé'}, 401
                
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            
            return {
                'access_token': access_token,
                'refresh_token': refresh_token
            }, 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors du rafraîchissement du token: {str(e)}")
            return {'message': 'Une erreur est survenue lors du rafraîchissement du token'}, 500

@api.route('/profile')
class UserProfile(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Profil récupéré avec succès', user_model)
    @api.response(401, 'Non authentifié')
    @jwt_required()
    def get(self):
        """Récupérer le profil de l'utilisateur connecté"""
        try:
            current_user_id = get_jwt_identity()
            if not current_user_id:
                return {'message': 'Non authentifié'}, 401
                
            user = User.query.get(current_user_id)
            if not user:
                return {'message': 'Utilisateur non trouvé'}, 404
                
            return user_schema.dump(user), 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la récupération du profil: {str(e)}")
            return {'message': 'Une erreur est survenue lors de la récupération du profil'}, 500

@api.route('/admin/users')
class AdminUsers(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Liste des utilisateurs récupérée avec succès')
    @api.response(401, 'Non authentifié')
    @api.response(403, 'Accès non autorisé')
    @jwt_required()
    @admin_required
    def get(self):
        """Récupérer la liste des utilisateurs (Admin uniquement)"""
        try:
            users = User.query.all()
            return user_schema.dump(users, many=True), 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la récupération des utilisateurs: {str(e)}")
            return {'message': 'Une erreur est survenue'}, 500

@api.route('/admin/reservations')
class AdminReservations(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Liste des réservations récupérée avec succès')
    @api.response(401, 'Non authentifié')
    @api.response(403, 'Accès non autorisé')
    @jwt_required()
    @admin_required
    def get(self):
        """Récupérer la liste de toutes les réservations (Admin uniquement)"""
        try:
            from models import Reservation
            from schemas import ReservationSchema
            
            reservations = Reservation.query.all()
            reservation_schema = ReservationSchema(many=True)
            return reservation_schema.dump(reservations), 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la récupération des réservations: {str(e)}")
            return {'message': 'Une erreur est survenue'}, 500

@api.route('/logout')
class Logout(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Déconnexion réussie')
    @jwt_required()
    def post(self):
        """Déconnexion et invalidation du token"""
        try:
            jti = get_jwt()["jti"]
            current_app.logger.info(f"Token invalidé: {jti}")
            return {'message': 'Déconnexion réussie'}, 200
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la déconnexion: {str(e)}")
            return {'message': 'Une erreur est survenue lors de la déconnexion'}, 500

# Routes web
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            return redirect(next_page)
        flash('Email ou mot de passe incorrect', 'danger')
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté avec succès', 'success')
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def auth_user_profile():
    form = ProfileForm()
    if form.validate_on_submit():
        if check_password_hash(current_user.password_hash, form.current_password.data):
            current_user.email = form.email.data
            if form.new_password.data:
                current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('Profil mis à jour avec succès', 'success')
            return redirect(url_for('auth.auth_user_profile'))
        else:
            flash('Mot de passe actuel incorrect', 'danger')
    elif request.method == 'GET':
        form.email.data = current_user.email
    return render_template('auth/profile.html', form=form) 
from flask import Flask, redirect, send_from_directory, request, jsonify, make_response, render_template, url_for
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_restx import Api, Resource, fields
from flask_login import LoginManager, current_user, login_required
from models import db, User, Vehicle
from routes.auth import auth_bp, api as auth_api
from routes.vehicles import vehicles_bp, api as vehicles_api
from routes.reservations import reservations_bp, api as reservations_api
from routes.admin import admin_bp
from config import Config
from datetime import timedelta, datetime
import os
import logging
from flask_migrate import Migrate

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Configuration du logging
    logging.basicConfig(level=logging.DEBUG)
    app.logger.setLevel(logging.DEBUG)
    
    # Configuration de la clé secrète pour Flask-WTF
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_SECRET_KEY'] = Config.WTF_CSRF_SECRET_KEY
    
    # Initialisation des extensions
    db.init_app(app)
    jwt = JWTManager(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    migrate = Migrate(app, db)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Configuration de JWT
    @jwt.user_identity_loader
    def user_identity_lookup(user):
        if isinstance(user, User):
            return user.id
        return user

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return User.query.filter_by(id=identity).one_or_none()
    
    # Configuration CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:5173", "http://localhost:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "supports_credentials": True,
            "expose_headers": ["Content-Type", "Authorization"],
            "max_age": 3600
        }
    })
    
    # Gestion des requêtes OPTIONS
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = make_response()
            response.headers.add("Access-Control-Allow-Origin", request.headers.get("Origin", "http://localhost:5173"))
            response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Requested-With")
            response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
            response.headers.add("Access-Control-Allow-Credentials", "true")
            return response
    
    # Configuration de Swagger
    api = Api(
        app,
        version='1.0',
        title='LuxeAuto API',
        description='API pour la gestion de location de voitures de luxe',
        doc='/docs',
        prefix='/api',
        security='Bearer Auth',
        authorizations={
            'Bearer Auth': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'Authorization',
                'description': 'Type "Bearer" suivi d\'un espace et du token JWT'
            }
        },
        validate=True  # Activer la validation
    )
    
    # Ajout des namespaces
    api.add_namespace(auth_api, path='/auth')
    api.add_namespace(vehicles_api, path='/vehicles')
    api.add_namespace(reservations_api, path='/reservations')
    
    # Enregistrement des blueprints pour les pages web
    app.register_blueprint(auth_bp)
    app.register_blueprint(vehicles_bp, url_prefix='/vehicles')
    app.register_blueprint(reservations_bp, url_prefix='/reservations')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Route pour l'API racine
    @app.route('/api')
    def api_root():
        return jsonify({
            'message': 'Bienvenue sur l\'API LuxeAuto',
            'version': '1.0',
            'documentation': '/docs'
        })
    
    # Route pour servir les fichiers uploadés
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(os.path.join(app.static_folder, 'uploads'), filename)
    
    # Route pour la page d'accueil
    @app.route('/')
    def index():
        # Récupérer les véhicules en vedette (les plus récents)
        featured_vehicles = Vehicle.query.order_by(Vehicle.date_ajout.desc()).limit(3).all()
        return render_template('index.html', featured_vehicles=featured_vehicles, now=datetime.now())
    
    # Route pour la page de contact
    @app.route('/contact', methods=['GET', 'POST'])
    def contact():
        if request.method == 'POST':
            # Traitement du formulaire de contact
            nom = request.form.get('nom')
            email = request.form.get('email')
            sujet = request.form.get('sujet')
            message = request.form.get('message')
            
            # TODO: Implémenter l'envoi d'email
            app.logger.info(f"Nouveau message de contact de {nom} ({email}) : {sujet}")
            
            return render_template('contact.html', success=True)
        return render_template('contact.html')
    
    # Route pour la page À propos
    @app.route('/about')
    def about():
        return render_template('about.html')
    
    # Route pour la page Conditions d'utilisation
    @app.route('/terms')
    def terms():
        return render_template('terms.html', now=datetime.now())
    
    # Route pour le profil utilisateur
    @app.route('/profile')
    @login_required
    def profile():
        return render_template('profile.html')
    
    # Gestion des erreurs
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500
    
    # Création du dossier uploads s'il n'existe pas
    # Sur Vercel, le système de fichiers est en lecture seule (sauf /tmp)
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except OSError:
        app.logger.warning("Impossible de créer UPLOAD_FOLDER (filesystem en lecture seule)")

    # Création des tables et mise à jour de la base de données
    # Enveloppé pour éviter qu'une base indisponible au cold start ne casse tout l'import du module
    try:
        with app.app_context():
            db.create_all()

            # Création d'un admin par défaut si aucun n'existe
            if not User.query.filter_by(role='admin').first():
                admin = User(
                    nom='Admin',
                    email='admin@luxeauto.com',
                    role='admin'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
    except Exception:
        app.logger.exception("Initialisation de la base de données impossible au démarrage")

    @app.errorhandler(NoAuthorizationError)
    def handle_no_auth_error(e):
        return jsonify({"msg": "Token manquant ou invalide"}), 401

    return app

# Instance WSGI au niveau module, requise par le runtime Python de Vercel
app = create_app()

if __name__ == '__main__':
    app.run(debug=True) 
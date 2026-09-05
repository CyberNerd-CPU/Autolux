import os
from datetime import timedelta

class Config:
    # Configuration de base
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'votre-clé-secrète-très-sécurisée'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'votre-clé-csrf-très-sécurisée'
    DEBUG = False
    TESTING = False
    
    # Configuration de la base de données PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:root@localhost:5432/luxeauto'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuration JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or os.urandom(32).hex()
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_ERROR_MESSAGE_KEY = 'message'
    
    # Configuration des uploads
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Sur Vercel, seul /tmp est accessible en écriture (non persistant entre invocations)
    if os.environ.get('VERCEL'):
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'jfif'}
    ALLOWED_MIMETYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/jfif'}
    
    # Configuration CORS
    CORS_ORIGINS = [
        'http://localhost:5173',  # Vue.js dev server
        'http://localhost:3000',  # Alternative port
        'http://127.0.0.1:5173',  # Local IP
        'http://127.0.0.1:3000',  # Local IP alternative
        'https://luxeauto.com',   # Production
        'https://www.luxeauto.com' # Production www
    ]
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH', 'HEAD']
    CORS_ALLOW_HEADERS = [
        'Content-Type',
        'Authorization',
        'X-Requested-With',
        'Accept',
        'Origin',
        'Access-Control-Request-Method',
        'Access-Control-Request-Headers',
        'Access-Control-Allow-Origin',
        'Access-Control-Allow-Credentials'
    ]
    CORS_EXPOSE_HEADERS = [
        'Content-Type',
        'Authorization',
        'Access-Control-Allow-Origin',
        'Access-Control-Allow-Credentials'
    ]
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_MAX_AGE = 3600
    
    # Configuration de sécurité
    PASSWORD_MIN_LENGTH = 8
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_ATTEMPT_WINDOW = 300  # 5 minutes en secondes
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    
    # Configuration de la session
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SESSION_TYPE = 'filesystem'
    
    # Configuration des emails
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:root@localhost:5432/luxeauto'
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:root@localhost:5432/luxeauto'
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

class StagingConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:root@localhost:5432/luxeauto'

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    DEBUG = False
    TESTING = False

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # Security: Require explicit SECRET_KEY in production, warn in development
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ENV') == 'production':
            raise RuntimeError("CRITICAL SECURITY ERROR: The SECRET_KEY environment variable must be set in production!")
        SECRET_KEY = 'dev-insecure-key-set-SECRET_KEY-in-production'

    basedir = os.path.abspath(os.path.dirname(__file__))
    _db_url = os.environ.get('DATABASE_URL')
    if _db_url and _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    if not _db_url and (os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ENV') == 'production'):
        raise RuntimeError("CRITICAL CONFIGURATION ERROR: The DATABASE_URL environment variable must be set in production!")

    SQLALCHEMY_DATABASE_URI = _db_url or ('sqlite:///' + os.path.join(basedir, 'skillxchange.db'))
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # max 50 MB upload


    # Flask-Mail configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'your-email@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'your-app-password'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'your-email@gmail.com'

    # Flask-APScheduler configuration
    SCHEDULER_API_ENABLED = True



from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
import os
from config import Config, is_production, parse_allowed_origins

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
scheduler = APScheduler()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    if not scheduler.running:
        scheduler.init_app(app)
    else:
        app.apscheduler = scheduler
    csrf.init_app(app)
    limiter.init_app(app)

    # Secure WebSocket CORS
    cors_origins = app.config.get('CORS_ALLOWED_ORIGINS')
    if cors_origins is None:
        cors_origins = parse_allowed_origins(
            os.environ.get('ALLOWED_ORIGINS'),
            is_prod=is_production()
        )
    elif is_production():
        if cors_origins == '*' or (isinstance(cors_origins, (list, tuple)) and '*' in cors_origins):
            raise RuntimeError("CRITICAL SECURITY ERROR: Wildcard '*' is not permitted for CORS / Socket.IO in production!")

    socketio.init_app(app, cors_allowed_origins=cors_origins)

    if not app.config.get('TESTING', False):
        if not scheduler.running:
            scheduler.start()
        try:
            from app.utils.notifications import recover_scheduled_reminders
            recover_scheduled_reminders(app)
        except Exception as e:
            app.logger.warning(f"Could not recover scheduled reminders on startup: {e}")


    # Register Blueprints
    from app.routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)
    
    from app.routes.skills import skills as skills_blueprint
    app.register_blueprint(skills_blueprint)
    
    from app.routes.mentorship import mentorship as mentorship_blueprint
    app.register_blueprint(mentorship_blueprint)

    from app.routes.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint)

    from app import socket_events

    # Basic route for testing
    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    return app

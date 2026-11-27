import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
scheduler = BackgroundScheduler()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    scheduler.app = app
    socketio.init_app(app, cors_allowed_origins="*")
    limiter.init_app(app)

    if not app.config.get('TESTING') and not scheduler.running:
        scheduler.start()

    # Register Blueprints
    from app.routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from app.routes.skills import skills as skills_blueprint
    app.register_blueprint(skills_blueprint)

    from app.routes.mentorship import mentorship as mentorship_blueprint
    app.register_blueprint(mentorship_blueprint)

    from app.routes.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint)

    from app import socket_events  # noqa: F401

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'}), 200

    with app.app_context():
        db.create_all()
        if app.config.get('AUTO_SEED', True):
            from seed import seed_if_empty
            seed_if_empty()

    return app

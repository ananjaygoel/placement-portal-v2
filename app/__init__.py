from flask import Flask

from app.config import Config
from app.extensions import db


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from app.admin import admin_bp
    from app.auth import auth_bp
    from app.company import company_bp
    from app.dashboard import dashboard_bp
    from app.views import views_bp

    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(company_bp, url_prefix="/api/company")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(views_bp)

    return app

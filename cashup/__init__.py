from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cashup.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from cashup.routes import main_bp, staff_bp, cashup_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(cashup_bp)
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    return app




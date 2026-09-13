from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()


def _ensure_schema(app):
    """Add columns/tables that create_all won't alter on existing SQLite DBs."""
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if 'cashup' in tables:
            columns = {c['name'] for c in inspector.get_columns('cashup')}
            if 'tip_outs_json' not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE cashup ADD COLUMN tip_outs_json TEXT'))
            if 'credit_sale' not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE cashup ADD COLUMN credit_sale NUMERIC(10, 2) '
                        'DEFAULT 0 NOT NULL'
                    ))


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
    from cashup.routes import main_bp, staff_bp, cashup_bp, settings_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(cashup_bp)
    app.register_blueprint(settings_bp)

    @app.context_processor
    def inject_app_settings():
        from cashup.models import AppSettings
        settings = AppSettings.get_or_create()
        return {
            'app_settings': settings,
            'currency_symbol': settings.currency_symbol,
            'enabled_tip_rules': settings.enabled_tip_rules(),
        }

    @app.template_filter('money')
    def money_filter(value):
        from cashup.models import AppSettings
        settings = AppSettings.get_or_create()
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = 0.0
        symbol = settings.currency_symbol or ''
        if amount < 0:
            return f'-{symbol}{abs(amount):.2f}'
        return f'{symbol}{amount:.2f}'
    
    _ensure_schema(app)
    
    return app

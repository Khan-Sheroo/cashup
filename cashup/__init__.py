from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from pathlib import Path

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

        if 'staff_document' in tables:
            columns = {c['name'] for c in inspector.get_columns('staff_document')}
            if 'folder_id' not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE staff_document ADD COLUMN folder_id INTEGER '
                        'REFERENCES staff_folder(id)'
                    ))

        if 'cost_item' in tables:
            columns = {c['name'] for c in inspector.get_columns('cost_item')}
            if 'pack_size' not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE cost_item ADD COLUMN pack_size NUMERIC(12, 4) '
                        'DEFAULT 1 NOT NULL'
                    ))
            new_item_columns = {
                'category': 'VARCHAR(80)',
                'count_unit': 'VARCHAR(20)',
                'count_factor': 'NUMERIC(12, 4)',
                'par_level': 'NUMERIC(12, 4)',
            }
            for name, col_type in new_item_columns.items():
                if name not in columns:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE cost_item ADD COLUMN {name} {col_type}'))

        if 'recipe' in tables:
            columns = {c['name'] for c in inspector.get_columns('recipe')}
            if 'location_id' not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE recipe ADD COLUMN location_id INTEGER '
                        'REFERENCES location(id)'
                    ))

        for table in ('invoice_line', 'supplier_item_alias'):
            if table in tables:
                columns = {c['name'] for c in inspector.get_columns(table)}
                if 'qty_unit' not in columns:
                    with db.engine.begin() as conn:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN qty_unit VARCHAR(10) "
                            f"DEFAULT 'unit' NOT NULL"
                        ))

        from cashup.models import DEFAULT_LOCATIONS, Location
        if Location.query.count() == 0:
            for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
                db.session.add(Location(name=name, kind=kind, sort_order=order))
            db.session.commit()


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cashup.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    upload_root = Path(app.root_path).parent / 'uploads'
    app.config['UPLOAD_FOLDER'] = str(upload_root)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB total per request
    upload_root.mkdir(parents=True, exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from cashup.routes import main_bp, staff_bp, cashup_bp, settings_bp
    from cashup.recipe_routes import recipes_bp
    from cashup.inventory_routes import inventory_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(cashup_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(inventory_bp)

    @app.template_filter('qty')
    def qty_filter(value, places=2):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return ''
        text_value = f'{amount:,.{places}f}'
        if '.' in text_value:
            text_value = text_value.rstrip('0').rstrip('.')
        return '0' if text_value in ('-0', '') else text_value

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

"""Ensure app_settings table and cashup.tip_outs_json exist."""
from cashup import create_app, db
from cashup.models import AppSettings
from sqlalchemy import inspect, text


def migrate():
    app = create_app()
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if 'cashup' in tables:
            columns = {c['name'] for c in inspector.get_columns('cashup')}
            if 'tip_outs_json' not in columns:
                print('Adding tip_outs_json column to cashup...')
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE cashup ADD COLUMN tip_outs_json TEXT'))
                print('OK: tip_outs_json added')
            else:
                print('OK: tip_outs_json already exists')

        settings = AppSettings.get_or_create()
        print(f'OK: settings ready (currency={settings.currency}, basis={settings.tip_out_basis})')
        print('Migration complete.')


if __name__ == '__main__':
    migrate()

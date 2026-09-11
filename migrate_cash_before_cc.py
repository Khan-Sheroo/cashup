from cashup import create_app, db
from sqlalchemy import text


def migrate_cash_before_cc():
    """Add cash_before_cc column to cashup table."""
    app = create_app()

    with app.app_context():
        try:
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]

            if 'cash_before_cc' not in columns:
                print("Adding cash_before_cc column to cashup table...")
                db.session.execute(
                    text("ALTER TABLE cashup ADD COLUMN cash_before_cc NUMERIC(10, 2) DEFAULT 0 NOT NULL")
                )
                print("OK: Added cash_before_cc")
            else:
                print("OK: cash_before_cc already exists")

            db.session.commit()
            print("OK: cash_before_cc migration complete")

        except Exception as e:
            db.session.rollback()
            print(f"ERROR migrating cash_before_cc: {e}")
            raise


if __name__ == "__main__":
    migrate_cash_before_cc()

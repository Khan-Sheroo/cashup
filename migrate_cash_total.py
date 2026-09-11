from cashup import create_app, db
from sqlalchemy import text


def migrate_cash_total():
    """Rename cash_before_cc to cash_total (cash tender against turnover)."""
    app = create_app()

    with app.app_context():
        try:
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]

            if 'cash_total' in columns:
                print("OK: cash_total already exists")
            elif 'cash_before_cc' in columns:
                print("Renaming cash_before_cc to cash_total...")
                db.session.execute(text("ALTER TABLE cashup RENAME COLUMN cash_before_cc TO cash_total"))
                print("OK: Renamed to cash_total")
            else:
                print("Adding cash_total column to cashup table...")
                db.session.execute(
                    text("ALTER TABLE cashup ADD COLUMN cash_total NUMERIC(10, 2) DEFAULT 0 NOT NULL")
                )
                print("OK: Added cash_total")

            db.session.commit()
            print("OK: cash_total migration complete")

        except Exception as e:
            db.session.rollback()
            print(f"ERROR migrating cash_total: {e}")
            raise


if __name__ == "__main__":
    migrate_cash_total()

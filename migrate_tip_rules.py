from cashup import create_app, db
from sqlalchemy import text


def migrate_tip_rules():
    """Add cc_commission and combined_tips columns for the new tip-out rules."""
    app = create_app()

    with app.app_context():
        try:
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]

            if 'cc_commission' not in columns:
                print("Adding cc_commission column to cashup table...")
                db.session.execute(
                    text("ALTER TABLE cashup ADD COLUMN cc_commission NUMERIC(10, 2) DEFAULT 0 NOT NULL")
                )
                print("OK: Added cc_commission")
            else:
                print("OK: cc_commission already exists")

            if 'combined_tips' not in columns:
                print("Adding combined_tips column to cashup table...")
                db.session.execute(
                    text("ALTER TABLE cashup ADD COLUMN combined_tips NUMERIC(10, 2) DEFAULT 0 NOT NULL")
                )
                print("OK: Added combined_tips")
            else:
                print("OK: combined_tips already exists")

            db.session.commit()
            print("OK: Tip rules migration complete")

        except Exception as e:
            db.session.rollback()
            print(f"ERROR migrating tip rules: {e}")
            raise


if __name__ == "__main__":
    migrate_tip_rules()

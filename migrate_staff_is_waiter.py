from cashup import create_app, db
from sqlalchemy import text


def migrate_staff_is_waiter():
    """Add is_waiter column to staff table."""
    app = create_app()

    with app.app_context():
        try:
            result = db.session.execute(text("PRAGMA table_info(staff)"))
            columns = [row[1] for row in result]

            if 'is_waiter' not in columns:
                print("Adding is_waiter column to staff table...")
                db.session.execute(
                    text("ALTER TABLE staff ADD COLUMN is_waiter BOOLEAN DEFAULT 0 NOT NULL")
                )
                print("OK: Added is_waiter")
            else:
                print("OK: is_waiter already exists")

            db.session.commit()
            print("OK: Staff is_waiter migration complete")

        except Exception as e:
            db.session.rollback()
            print(f"ERROR migrating staff is_waiter: {e}")
            raise


if __name__ == "__main__":
    migrate_staff_is_waiter()

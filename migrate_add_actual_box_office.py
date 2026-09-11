from cashup import create_app, db
from sqlalchemy import text

def add_actual_box_office_column():
    """Add actual_box_office column to existing cashup table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]
            
            if 'actual_box_office' in columns:
                print("[OK] Actual box office column already exists in the database.")
                return
            
            # Add the actual_box_office column
            print("Adding actual_box_office column to cashup table...")
            db.session.execute(text("ALTER TABLE cashup ADD COLUMN actual_box_office NUMERIC(10, 2) DEFAULT 0"))
            db.session.commit()
            print("[OK] Successfully added actual_box_office column!")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error adding actual_box_office column: {e}")
            raise

if __name__ == "__main__":
    add_actual_box_office_column()























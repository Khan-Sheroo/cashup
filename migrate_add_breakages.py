from cashup import create_app, db
from sqlalchemy import text

def add_breakages_column():
    """Add breakages column to existing cashup table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]
            
            if 'breakages' in columns:
                print("✓ Breakages column already exists in the database.")
                return
            
            # Add the breakages column
            print("Adding breakages column to cashup table...")
            db.session.execute(text("ALTER TABLE cashup ADD COLUMN breakages NUMERIC(10, 2) DEFAULT 0"))
            db.session.commit()
            print("✓ Successfully added breakages column!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error adding breakages column: {e}")
            raise

if __name__ == "__main__":
    add_breakages_column()

























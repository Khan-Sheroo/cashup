from cashup import create_app, db
from sqlalchemy import text

def add_box_office_tips_column():
    """Add box_office_tips column to existing cashup table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]
            
            if 'box_office_tips' in columns:
                print("✓ Box office tips column already exists in the database.")
                return
            
            # Add the box_office_tips column
            print("Adding box_office_tips column to cashup table...")
            db.session.execute(text("ALTER TABLE cashup ADD COLUMN box_office_tips NUMERIC(10, 2) DEFAULT 0"))
            db.session.commit()
            print("✓ Successfully added box_office_tips column!")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error adding box_office_tips column: {e}")
            raise

if __name__ == "__main__":
    add_box_office_tips_column()




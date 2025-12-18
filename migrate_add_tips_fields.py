from cashup import create_app, db
from sqlalchemy import text

def add_tips_fields():
    """Add runners_tips, bar_tips, and kitchen_tips columns to existing cashup table"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check if columns already exist
            result = db.session.execute(text("PRAGMA table_info(cashup)"))
            columns = [row[1] for row in result]
            
            fields_to_add = [
                ('runners_tips', 'Runners Tips'),
                ('bar_tips', 'Bar Tips'),
                ('kitchen_tips', 'Kitchen Tips')
            ]
            
            for field_name, display_name in fields_to_add:
                if field_name in columns:
                    print(f"[OK] {display_name} column already exists in the database.")
                else:
                    # Add the column
                    print(f"Adding {display_name.lower()} column to cashup table...")
                    db.session.execute(text(f"ALTER TABLE cashup ADD COLUMN {field_name} NUMERIC(10, 2) DEFAULT 0"))
                    print(f"[OK] Successfully added {display_name.lower()} column!")
            
            db.session.commit()
            print("\n[OK] All tip fields migration completed!")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error adding tip fields: {e}")
            raise

if __name__ == "__main__":
    add_tips_fields()


#!/usr/bin/env python
"""Add submitted field to cashup table"""

from cashup import create_app, db
from cashup.models import CashUp
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        # Add the submitted column if it doesn't exist
        db.session.execute(text("""
            ALTER TABLE cashup 
            ADD COLUMN submitted BOOLEAN DEFAULT 0 NOT NULL
        """))
        db.session.commit()
        print("Added 'submitted' column to cashup table")
        
        # Set all existing cashups as submitted (True)
        db.session.execute(text("""
            UPDATE cashup 
            SET submitted = 1
            WHERE submitted = 0 OR submitted IS NULL
        """))
        db.session.commit()
        print("Set all existing cashups as submitted")
        
    except Exception as e:
        # Column might already exist
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("Column 'submitted' already exists, skipping migration")
        else:
            print(f"Error during migration: {e}")
            db.session.rollback()
            raise


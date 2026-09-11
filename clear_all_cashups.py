#!/usr/bin/env python
"""Clear all cashup data while keeping staff names"""

from cashup import create_app, db
from cashup.models import CashUp, Staff

app = create_app()

with app.app_context():
    # Count before deletion
    total_cashups = CashUp.query.count()
    total_staff = Staff.query.count()
    
    print("=" * 60)
    print("Clearing all cashup data...")
    print("=" * 60)
    print(f"Total cashups to delete: {total_cashups}")
    print(f"Total staff members (will be kept): {total_staff}")
    print()
    
    # Delete all cashups
    deleted_count = CashUp.query.delete()
    db.session.commit()
    
    print(f"Successfully deleted {deleted_count} cashup record(s)")
    print(f"Kept {total_staff} staff member(s)")
    print()
    print("All cashup data has been cleared. Staff names are preserved.")
    print("=" * 60)


#!/usr/bin/env python
"""Clear all staff and related cashup data for a fresh start."""

from cashup import create_app, db
from cashup.models import CashUp, Staff, WaiterTip, DailySummary, CardMachineBatch

app = create_app()

with app.app_context():
    cashup_count = CashUp.query.count()
    tip_count = WaiterTip.query.count()
    staff_count = Staff.query.count()
    summary_count = DailySummary.query.count()
    batch_count = CardMachineBatch.query.count()

    print("=" * 60)
    print("Clearing all staff and related data...")
    print("=" * 60)
    print(f"Cashups: {cashup_count}")
    print(f"Waiter tips: {tip_count}")
    print(f"Staff: {staff_count}")
    print(f"Daily summaries: {summary_count}")
    print(f"Card machine batches: {batch_count}")
    print()

    # Delete in dependency order
    WaiterTip.query.delete()
    CashUp.query.delete()
    CardMachineBatch.query.delete()
    DailySummary.query.delete()
    Staff.query.delete()
    db.session.commit()

    print("OK: All staff and related data cleared.")
    print("Add new users via Staff > Add Staff Member.")
    print("=" * 60)

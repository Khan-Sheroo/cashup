from cashup import create_app, db
from cashup.models import Staff

# Waiters list
WAITERS = [
    "ABONGILE",
    "ALICIA",
    "AMY",
    "ANEZKA",
    "BOBBY",
    "CHE",
    "CLIFF",
    "COLLEN",
    "DANICA DAVIS",
    "EMMA-MEII",
    "GEM-DIOR",
    "GREG",
    "HAILIE",
    "KELLY",
    "KIETH GUMBO",
    "KIOWA",
    "KIRA",
    "KYLE",
    "LIAM",
    "MARK",
    "NORMA",
    "NOXY",
    "PHUMZA",
    "ROBERT",
    "ROBIN",
    "RUTH",
    "SACHA",
    "SANDRA",
    "SKYLA",
    "SONGEZO",
    "TARYN",
    "TAYLOR",
    "TOASTY",
    "VAVALICIOUS",
    "YONELA",
    "YOYO",
    "ZARIN",
]

# Bars list
BARS = [
    "Main Bar",
    "VIP Bar",
    "SAND Bar",
]

def seed_staff():
    """Seed the database with waiters and bars"""
    app = create_app()
    
    with app.app_context():
        # Get all existing staff names to avoid duplicates
        existing_staff = {staff.name for staff in Staff.query.all()}
        
        staff_to_add = []
        skipped = []
        
        # Add waiters
        for name in WAITERS:
            name = name.strip()
            if not name:
                continue
            if name in existing_staff:
                skipped.append(name)
                continue
            staff_to_add.append(Staff(name=name, active=True))
            existing_staff.add(name)  # Track in this session too
        
        # Add bars
        for name in BARS:
            name = name.strip()
            if not name:
                continue
            if name in existing_staff:
                skipped.append(name)
                continue
            staff_to_add.append(Staff(name=name, active=True))
            existing_staff.add(name)
        
        # Add all new staff members
        if staff_to_add:
            db.session.add_all(staff_to_add)
            db.session.commit()
            print(f"✓ Successfully added {len(staff_to_add)} staff members:")
            print(f"  - {len(WAITERS) - len([s for s in skipped if s in WAITERS])} waiters")
            print(f"  - {len(BARS) - len([s for s in skipped if s in BARS])} bars")
        else:
            print("No new staff members to add.")
        
        if skipped:
            print(f"\n⚠ Skipped {len(skipped)} existing staff members:")
            for name in skipped:
                print(f"  - {name}")
        
        # Show total count
        total_staff = Staff.query.count()
        print(f"\n📊 Total staff members in database: {total_staff}")


if __name__ == "__main__":
    seed_staff()




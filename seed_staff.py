from cashup import create_app, db
from cashup.models import Staff

# Staff list with format: NAME | NICKNAME | SURNAME | DEPARTMENT
STAFF_DATA = [
    # BARBACKS
    ("BUTHOLEMKESI", "BUTHO", "MASEKO", "BARBACK"),
    ("TAWANDA", "TAWANDA", "CHAKANETSA", "BARBACK"),
    ("TAKURA", "BLESSING", "JARVAZA", "BARBACK"),
    
    # BARTENDERS
    ("COLLIN (bar)", "COLLIN", "SIBANDA", "BARTENDER"),
    ("EDSON", "EDSON", "CHINGWARU", "BARTENDER"),
    ("JOHN", "JOHN TK", "KOFI", "BARTENDER"),
    ("MARK (bar)", "THABO", "NYATHI", "BARTENDER"),
    ("MUKETIWA", "NICKIE", "JARAVAZA", "BARTENDER"),
    ("ROMEO", "JULIET", "MAHAYA", "BARTENDER"),
    ("HENDRIX", "HENDRIX", "CHINITHENGA", "BARTENDER"),
    ("ZVIHOMBORERO", "ZVIKO", "SHAMUYELOVA", "BARTENDER"),
    ("RAFIEK", "RAFIEK", "JAMES", "BARTENDER"),
    
    # RUNNERS
    ("SETH", "SETH", "ELINAM", "RUNNER"),
    ("YONELA", "YONELA", "NODLIWA", "RUNNER"),
    ("ALEXANDER", "ALEX", "MAKAHADZO", "RUNNER"),
    ("AUBREY", "AUBREY", "GWATI", "RUNNER"),
    ("FARAI", "FARAI", "MUZI", "RUNNER"),
    ("PETER", "MAZWIDZO", "MAZWIDZO", "RUNNER"),
    ("ESETHU", "ESETHU", "GODOLA", "RUNNER"),
    ("BERTHANYASHA", "NYASHA", "MUCHIZA", "RUNNER"),
    ("ZAKIR", "ZAKIR", "ROACH", "RUNNER"),
    ("BILQIS", "BILQIS", "WALLACE", "RUNNER"),
    ("NOTHUKELA", "", "", "RUNNER"),  # No nickname, surname, or department specified - assigned to RUNNER
    
    # TRAINEES
    ("SACHA", "SACHA", "WRIGHT", "TRAINEE"),
    ("ANEZKA", "ANEZKA", "VILJOEN", "TRAINEE WAITRON"),
    ("ASHEEQAH", "", "MANUEL", "TRAINEE WAITRON"),
    
    # WAITRONS
    ("ABONGILE", "AB", "JAWUKA", "WAITRON"),
    ("ALICIA", "ALICIA", "MURUNGENI", "WAITRON"),
    ("AMY", "AMY", "PETERSEN", "WAITRON"),
    ("BOBBY", "BOBBY", "NDIMANDE", "WAITRON"),
    ("CLIFFORD", "CLIFF", "YOUNG", "WAITRON"),
    ("COLLEN thatenda", "COLLEN", "MURONGAZVOMBO", "WAITRON"),
    ("CRAIG", "TOASTY", "VAN DER LITH", "WAITRON"),
    ("KELLY", "KELLY", "MAAWIDZA", "WAITRON"),
    ("KIOWA", "KIOWA", "HOWES", "WAITRON"),
    ("KYLE", "KYLE", "MACRANAS", "WAITRON"),
    ("LIAM", "LIAM", "MONGLE", "WAITRON"),
    ("MARK", "MARK", "Chirenje", "WAITRON"),
    ("NOMXOLISI", "NOXY", "BEBI", "WAITRON"),
    ("NTOMBEVANGELI", "VAVALICIOUS", "MQUDU", "WAITRON"),
    ("ROBIN", "ROBIN", "JEPPE", "WAITRON"),
    ("RUTH", "RUTH", "EKERMANS", "WAITRON"),
    ("SANDRA", "SANDRA", "VILJOEN", "WAITRON"),
    ("SKYLA", "SKYLA", "VAN WYNGAARD", "WAITRON"),
    ("SONGEZO", "BROWN HAZEL", "MALIZEL", "WAITRON"),
    ("GREG", "GREG", "BOYLE", "WAITRON"),
    ("TARYN", "TARYN", "DAVIS", "WAITRON"),
    ("TAYLOR", "TAYLOR", "JOHANSSEN", "WAITRON"),
    ("ROBERT", "ROBERT", "", "WAITRON"),
    ("YOLANDI", "YOYO", "BASSON", "WAITRON"),
    ("ZARIN", "ZARIN", "WOLFF", "WAITRON"),
    ("DANICA", "DANICA", "DAVIS", "WAITRON"),
    ("CHE", "CHE", "VAN WEZEL", "WAITRON"),
    ("KEITH", "KEITH", "GUMBO", "WATRON"),  # Note: WATRON (likely typo for WAITRON)
    ("GEM", "GEM", "MELTZ", "WATRON"),  # Note: WATRON (likely typo for WAITRON)
    ("EMMA-MEI", "EMMA-MEI", "", "WATRON"),  # Note: WATRON (likely typo for WAITRON)
]

def seed_staff():
    """Seed the database with all staff members"""
    app = create_app()
    
    with app.app_context():
        # Get all existing staff names to avoid duplicates
        existing_staff = {staff.name.upper() for staff in Staff.query.all()}
        
        staff_to_add = []
        skipped = []
        
        # Add all staff members
        for name, nickname, surname, department in STAFF_DATA:
            name = name.strip()
            if not name:
                continue
            
            # Check if staff already exists (case-insensitive)
            if name.upper() in existing_staff:
                skipped.append(name)
                continue
            
            staff_to_add.append(Staff(name=name, active=True))
            existing_staff.add(name.upper())
        
        # Add all new staff members
        if staff_to_add:
            db.session.add_all(staff_to_add)
            db.session.commit()
            print(f"Successfully added {len(staff_to_add)} staff members")
            
            # Count by department
            dept_counts = {}
            for name, nickname, surname, department in STAFF_DATA:
                if name.strip() and name.upper() not in [s.upper() for s in skipped]:
                    dept_counts[department] = dept_counts.get(department, 0) + 1
            
            print("\nAdded by department:")
            for dept, count in sorted(dept_counts.items()):
                print(f"  - {dept}: {count}")
        else:
            print("No new staff members to add.")
        
        if skipped:
            print(f"\nSkipped {len(skipped)} existing staff members:")
            for name in skipped[:10]:  # Show first 10
                print(f"  - {name}")
            if len(skipped) > 10:
                print(f"  ... and {len(skipped) - 10} more")
        
        # Show total count
        total_staff = Staff.query.count()
        print(f"\nTotal staff members in database: {total_staff}")
        
        # Show summary by department for all staff
        print("\nAll staff by department:")
        all_staff = Staff.query.all()
        dept_summary = {}
        for staff in all_staff:
            # Try to match staff name to department from STAFF_DATA
            dept = "UNKNOWN"
            for name, nickname, surname, department in STAFF_DATA:
                if staff.name.upper() == name.upper():
                    dept = department
                    break
            if dept not in dept_summary:
                dept_summary[dept] = []
            dept_summary[dept].append(staff.name)
        
        for dept, names in sorted(dept_summary.items()):
            print(f"\n{dept} ({len(names)}):")
            for name in sorted(names):
                print(f"  - {name}")


if __name__ == "__main__":
    seed_staff()

# CashUp

A web-based application for capturing daily staff cash-ups, replacing manual Excel sheets with a structured, validated system.

## Features

- **Staff Management**: Add and manage staff members with active/inactive status
- **Cash-Up Entry**: Excel-style table interface for entering multiple cash-ups at once
- **Automatic Tip Calculation**: Tips are automatically calculated as `Turnover - Credit Card Amount`
- **Real-time Validation**: Frontend and backend validation with error highlighting
- **Cash-Up History**: View and filter historical cash-ups by date and staff member
- **Responsive Design**: Bootstrap 5 styling with mobile-friendly interface

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: Bootstrap 5 (HTML templates)
- **Database**: SQLite with SQLAlchemy ORM
- **JavaScript**: Vanilla JS for calculations and validation

## Installation

1. **Navigate to the project directory**:
   ```bash
   cd C:\Users\shero\cashup
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   ```bash
   venv\Scripts\activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the application**:
   ```bash
   python run.py
   ```

6. **Access the application**:
   Open your browser and navigate to `http://localhost:5000`

## Usage

### Adding Staff Members

1. Navigate to **Staff** in the navigation menu
2. Click **Add Staff Member**
3. Enter the staff member's full name
4. Check/uncheck the "Active" checkbox
5. Click **Add Staff Member**

### Creating Cash-Ups

1. Navigate to **New Cash-Up** in the navigation menu
2. Select the date for the cash-up
3. For each staff member:
   - Select the staff member from the dropdown
   - Enter the turnover amount
   - Enter the credit card total
   - The tip amount will be calculated automatically
4. Click **Add Row** to add more entries
5. Click **Save Cash-Ups** to save all entries

### Viewing Cash-Up History

1. Navigate to **View Cash-Ups** in the navigation menu
2. Use the filters to:
   - Filter by date
   - Filter by staff member
3. View the table with all matching cash-ups
4. Totals are displayed at the bottom of the table

## Validation Rules

- Turnover must be ≥ 0
- Credit card amount must be ≥ 0
- Credit card amount cannot exceed turnover
- Staff member must be selected
- All values must be numeric
- Negative tips are highlighted as errors

## Project Structure

```
cashup/
├── cashup/
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # Database models (Staff, CashUp)
│   ├── routes.py            # Flask routes and views
│   └── templates/
│       ├── base.html        # Base template with navigation
│       ├── staff/
│       │   ├── list.html    # Staff list view
│       │   └── add.html     # Add staff form
│       └── cashup/
│           ├── new.html     # Cash-up entry form
│           └── list.html    # Cash-up history view
├── run.py                   # Application entry point
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Database

The application uses SQLite by default. The database file (`cashup.db`) will be created automatically in the project root when you first run the application.

### Tables

- **staff**: Staff member information
- **cashup**: Cash-up records linked to staff members

## Future Enhancements (Out of Scope)

- Excel import/export
- Role-based permissions
- Daily totals and summaries
- Audit logs
- PDF cash-up reports
- Integration with POS data

## License

This project is for internal use.




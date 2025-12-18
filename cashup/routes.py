from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from cashup import db
from cashup.models import Staff, CashUp
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

# Main blueprint for home page
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Home page - redirect to new cash-up"""
    return redirect(url_for('cashup.new_cashup'))


# Staff management blueprint
staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


@staff_bp.route('/')
def list_staff():
    """List all staff members"""
    staff_list = Staff.query.order_by(Staff.name).all()
    return render_template('staff/list.html', staff_list=staff_list)


@staff_bp.route('/add', methods=['GET', 'POST'])
def add_staff():
    """Add a new staff member"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        active = request.form.get('active') == 'on'
        
        # Validation
        if not name:
            flash('Staff name is required', 'error')
            return render_template('staff/add.html')
        
        # Check for duplicate names
        existing = Staff.query.filter_by(name=name).first()
        if existing:
            flash(f'Staff member "{name}" already exists', 'error')
            return render_template('staff/add.html')
        
        # Create new staff
        staff = Staff(name=name, active=active)
        db.session.add(staff)
        db.session.commit()
        
        flash(f'Staff member "{name}" added successfully', 'success')
        return redirect(url_for('staff.list_staff'))
    
    return render_template('staff/add.html')


@staff_bp.route('/<int:staff_id>/toggle', methods=['POST'])
def toggle_staff_status(staff_id):
    """Toggle staff active/inactive status"""
    staff = Staff.query.get_or_404(staff_id)
    staff.active = not staff.active
    db.session.commit()
    
    status = 'activated' if staff.active else 'deactivated'
    flash(f'Staff member "{staff.name}" {status}', 'success')
    return redirect(url_for('staff.list_staff'))


# Cash-up blueprint
cashup_bp = Blueprint('cashup', __name__, url_prefix='/cashup')


@cashup_bp.route('/new', methods=['GET', 'POST'])
def new_cashup():
    """Capture new cash-ups"""
    if request.method == 'POST':
        # Get form data
        entries = request.form.getlist('staff_id')
        
        if not entries:
            flash('Please add at least one cash-up entry', 'error')
            return redirect(url_for('cashup.new_cashup'))
        
        errors = []
        cashups_to_add = []
        
        # Process each row
        for i, staff_id in enumerate(entries):
            try:
                staff_id = int(staff_id)
                date_str = request.form.get(f'date_{i}', '')
                turnover_str = request.form.get(f'turnover_{i}', '0')
                credit_card_str = request.form.get(f'credit_card_{i}', '0')
                breakages_str = request.form.get(f'breakages_{i}', '0')
                box_office_tips_str = request.form.get(f'box_office_tips_{i}', '0')
                actual_box_office_str = request.form.get(f'actual_box_office_{i}', '0')
                runners_tips_str = request.form.get(f'runners_tips_{i}', '0')
                bar_tips_str = request.form.get(f'bar_tips_{i}', '0')
                kitchen_tips_str = request.form.get(f'kitchen_tips_{i}', '0')
                
                # Validate date
                if not date_str:
                    errors.append(f'Row {i+1}: Date is required')
                    continue
                
                try:
                    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'Row {i+1}: Invalid date format')
                    continue
                
                # Validate and convert numeric values
                try:
                    turnover = Decimal(turnover_str)
                    credit_card = Decimal(credit_card_str)
                    breakages = Decimal(breakages_str)
                    box_office_tips = Decimal(box_office_tips_str)
                    actual_box_office = Decimal(actual_box_office_str)
                    runners_tips = Decimal(runners_tips_str)
                    bar_tips = Decimal(bar_tips_str)
                    kitchen_tips = Decimal(kitchen_tips_str)
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {i+1}: Invalid numeric values')
                    continue
                
                # Business validation
                if turnover < 0:
                    errors.append(f'Row {i+1}: Turnover cannot be negative')
                    continue
                
                if credit_card < 0:
                    errors.append(f'Row {i+1}: Credit card amount cannot be negative')
                    continue
                
                if breakages < 0:
                    errors.append(f'Row {i+1}: Breakages cannot be negative')
                    continue
                
                if box_office_tips < 0:
                    errors.append(f'Row {i+1}: Box office tips cannot be negative')
                    continue
                
                if actual_box_office < 0:
                    errors.append(f'Row {i+1}: Actual box office cannot be negative')
                    continue
                
                if runners_tips < 0:
                    errors.append(f'Row {i+1}: Runners tips cannot be negative')
                    continue
                
                if bar_tips < 0:
                    errors.append(f'Row {i+1}: Bar tips cannot be negative')
                    continue
                
                if kitchen_tips < 0:
                    errors.append(f'Row {i+1}: Kitchen tips cannot be negative')
                    continue
                
                # Verify staff exists
                staff = Staff.query.get(staff_id)
                if not staff:
                    errors.append(f'Row {i+1}: Invalid staff member')
                    continue
                
                # Calculate tip: credit_card - turnover - breakages - runners_tips - bar_tips - kitchen_tips
                tip_amount = credit_card - turnover - breakages - runners_tips - bar_tips - kitchen_tips
                
                # Create cash-up record
                cashup = CashUp(
                    staff_id=staff_id,
                    date=entry_date,
                    turnover=turnover,
                    credit_card_total=credit_card,
                    breakages=breakages,
                    tip_amount=tip_amount,
                    box_office_tips=box_office_tips,
                    actual_box_office=actual_box_office,
                    runners_tips=runners_tips,
                    bar_tips=bar_tips,
                    kitchen_tips=kitchen_tips
                )
                cashups_to_add.append(cashup)
                
            except (ValueError, TypeError) as e:
                errors.append(f'Row {i+1}: Invalid data - {str(e)}')
                continue
        
        # If there are errors, show them and return
        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('cashup.new_cashup'))
        
        # Save all valid cash-ups
        if cashups_to_add:
            for cashup in cashups_to_add:
                db.session.add(cashup)
            db.session.commit()
            flash(f'Successfully saved {len(cashups_to_add)} cash-up(s)', 'success')
            
            # Redirect back with the date from the first entry to show updated totals
            if cashups_to_add:
                entry_date = cashups_to_add[0].date.isoformat()
                return redirect(url_for('cashup.new_cashup', date=entry_date))
        else:
            flash('No valid cash-ups to save', 'error')
        
        return redirect(url_for('cashup.new_cashup'))
    
    # GET request - show form with cash-up history
    active_staff = Staff.query.filter_by(active=True).order_by(Staff.name).all()
    today = date.today().isoformat()
    
    # Get filter parameters for cash-up history
    filter_date = request.args.get('date', today)  # Default to today
    filter_staff_id = request.args.get('staff_id', '')
    
    # Build query for cash-ups
    query = CashUp.query.join(Staff)
    
    # Always filter by date (required - show only one date at a time)
    if filter_date:
        try:
            filter_date_obj = datetime.strptime(filter_date, '%Y-%m-%d').date()
            query = query.filter(CashUp.date == filter_date_obj)
        except ValueError:
            # If invalid date, default to today
            filter_date_obj = date.today()
            filter_date = today
            query = query.filter(CashUp.date == filter_date_obj)
    else:
        # Default to today if no date provided
        filter_date_obj = date.today()
        filter_date = today
        query = query.filter(CashUp.date == filter_date_obj)
    
    if filter_staff_id:
        try:
            query = query.filter(CashUp.staff_id == int(filter_staff_id))
        except ValueError:
            pass
    
    # Order by staff name (since we're showing only one date)
    cashups = query.order_by(Staff.name).all()
    
    # Calculate totals
    total_turnover = sum(float(c.turnover) for c in cashups)
    total_credit_card = sum(float(c.credit_card_total) for c in cashups)
    
    # Total CC for the day (same as total_credit_card, but explicitly named for clarity)
    day_total_cc = total_credit_card
    total_breakages = sum(float(c.breakages) for c in cashups)
    total_tips = sum(float(c.tip_amount) for c in cashups)
    total_box_office_tips = sum(float(c.box_office_tips) for c in cashups)
    total_actual_box_office = sum(float(c.actual_box_office) for c in cashups)
    total_runners_tips = sum(float(c.runners_tips) for c in cashups)
    total_bar_tips = sum(float(c.bar_tips) for c in cashups)
    total_kitchen_tips = sum(float(c.kitchen_tips) for c in cashups)
    
    return render_template('cashup/new.html', 
                         staff_list=active_staff, 
                         today=today,
                         cashups=cashups,
                         filter_date=filter_date,
                         filter_staff_id=filter_staff_id,
                         total_turnover=total_turnover,
                         total_credit_card=total_credit_card,
                         total_breakages=total_breakages,
                         total_tips=total_tips,
                         total_box_office_tips=total_box_office_tips,
                         total_actual_box_office=total_actual_box_office,
                         total_runners_tips=total_runners_tips,
                         total_bar_tips=total_bar_tips,
                         total_kitchen_tips=total_kitchen_tips,
                         day_total_cc=day_total_cc)


@cashup_bp.route('/list')
def list_cashups():
    """Redirect to new cash-up page (history is now shown there)"""
    return redirect(url_for('cashup.new_cashup'))


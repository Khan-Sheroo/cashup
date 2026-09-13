from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from cashup import db
from cashup.models import Staff, CashUp, CardMachineBatch, WaiterTip, AppSettings, DailySummary
from cashup.settings_util import (
    CURRENCIES,
    TIP_OUT_BASIS_CHOICES,
    TIP_OUT_PRESETS,
    calculate_tip_breakdown,
    tip_outs_to_legacy,
    tip_outs_as_float_dict,
    sum_tip_outs_for_rows,
    normalize_tip_rules,
    slugify_key,
)
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
import json

# Card machine terminal IDs
CARD_MACHINE_TERMINALS = [
    '80004223', '80003886', '80004226', '80002783', '80002787'
]

def is_waiter(staff):
    """Check if a staff member is marked as a waiter"""
    if staff is None:
        return False
    return bool(staff.is_waiter)

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
        is_waiter_flag = request.form.get('is_waiter') == 'on'
        
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
        staff = Staff(name=name, active=active, is_waiter=is_waiter_flag)
        db.session.add(staff)
        db.session.commit()
        
        flash(f'Staff member "{name}" added successfully', 'success')
        return redirect(url_for('staff.list_staff'))
    
    return render_template('staff/add.html')


@staff_bp.route('/api/create', methods=['POST'])
def api_create_staff():
    """Create a staff member via JSON (inline from cash-up dropdown)"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    is_waiter_flag = bool(data.get('is_waiter'))
    
    if not name:
        return jsonify({'success': False, 'error': 'Staff name is required'}), 400
    
    existing = Staff.query.filter_by(name=name).first()
    if existing:
        return jsonify({'success': False, 'error': f'Staff member "{name}" already exists'}), 400
    
    staff = Staff(name=name, active=True, is_waiter=is_waiter_flag)
    db.session.add(staff)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'staff': {
            'id': staff.id,
            'name': staff.name,
            'is_waiter': staff.is_waiter
        }
    })


@staff_bp.route('/<int:staff_id>/toggle', methods=['POST'])
def toggle_staff_status(staff_id):
    """Toggle staff active/inactive status"""
    staff = Staff.query.get_or_404(staff_id)
    staff.active = not staff.active
    db.session.commit()
    
    status = 'activated' if staff.active else 'deactivated'
    flash(f'Staff member "{staff.name}" {status}', 'success')
    return redirect(url_for('staff.list_staff'))


@staff_bp.route('/<int:staff_id>/toggle-waiter', methods=['POST'])
def toggle_waiter_status(staff_id):
    """Toggle whether a staff member is a waiter (for tips sheet)"""
    staff = Staff.query.get_or_404(staff_id)
    staff.is_waiter = not staff.is_waiter
    db.session.commit()
    
    status = 'marked as waiter' if staff.is_waiter else 'unmarked as waiter'
    flash(f'Staff member "{staff.name}" {status}', 'success')
    return redirect(url_for('staff.list_staff'))


@staff_bp.route('/<int:staff_id>/delete', methods=['POST'])
def delete_staff(staff_id):
    """Delete a staff member and their related records"""
    staff = Staff.query.get_or_404(staff_id)
    name = staff.name
    
    WaiterTip.query.filter_by(staff_id=staff_id).delete()
    CashUp.query.filter_by(staff_id=staff_id).delete()
    db.session.delete(staff)
    db.session.commit()
    
    flash(f'Staff member "{name}" deleted', 'success')
    return redirect(url_for('staff.list_staff'))


# Cash-up blueprint
cashup_bp = Blueprint('cashup', __name__, url_prefix='/cashup')


def persist_cashup_drafts(form):
    """Save draft cash-ups and card machine batches from form data.
    
    Returns a dict with success, errors, entry_date, row_ids, saved_count.
    """
    entries = form.getlist('staff_id')
    entry_date_str = form.get('entry_date', '')
    
    if not entry_date_str:
        return {'success': False, 'errors': ['Date is required'], 'entry_date': None, 'row_ids': [], 'saved_count': 0}
    
    try:
        entry_date_obj = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
    except ValueError:
        return {'success': False, 'errors': ['Invalid date format'], 'entry_date': None, 'row_ids': [], 'saved_count': 0}
    
    # Save card machine batch totals (including 0 to clear/update)
    for terminal_id in CARD_MACHINE_TERMINALS:
        batch_total_str = form.get(f'card_machine_{terminal_id}', '0')
        try:
            batch_total = Decimal(batch_total_str) if batch_total_str else Decimal('0')
        except (InvalidOperation, ValueError):
            batch_total = Decimal('0')
        
        card_batch = CardMachineBatch.query.filter_by(
            date=entry_date_obj,
            terminal_id=terminal_id
        ).first()
        if card_batch:
            card_batch.batch_total = batch_total
        elif batch_total > 0:
            db.session.add(CardMachineBatch(
                date=entry_date_obj,
                terminal_id=terminal_id,
                batch_total=batch_total
            ))
    
    errors = []
    cashup_ids_to_keep = []
    row_ids = []  # [{index, id}] for form sync after autosave
    saved_count = 0
    
    for i, staff_id_raw in enumerate(entries):
        # Skip blank rows (no staff selected yet)
        if not staff_id_raw or staff_id_raw == '__new__':
            continue
        
        try:
            staff_id = int(staff_id_raw)
        except (ValueError, TypeError):
            errors.append(f'Row {i+1}: Invalid staff member')
            continue
        
        cashup_id_str = form.get(f'cashup_id_{i}', '')
        turnover_str = form.get(f'turnover_{i}', '0') or '0'
        cash_str = form.get(f'cash_{i}', '0') or '0'
        credit_card_str = form.get(f'credit_card_{i}', '0') or '0'
        credit_sale_str = form.get(f'credit_sale_{i}', '0') or '0'
        
        try:
            turnover = Decimal(turnover_str)
            cash_total = Decimal(cash_str)
            credit_card = Decimal(credit_card_str)
            credit_sale = Decimal(credit_sale_str)
        except (InvalidOperation, ValueError):
            errors.append(f'Row {i+1}: Invalid numeric values')
            continue
        
        if turnover < 0:
            errors.append(f'Row {i+1}: Turnover cannot be negative')
            continue
        
        if cash_total < 0:
            errors.append(f'Row {i+1}: Cash cannot be negative')
            continue
        
        if credit_card < 0:
            errors.append(f'Row {i+1}: Credit card amount cannot be negative')
            continue

        if credit_sale < 0:
            errors.append(f'Row {i+1}: Credit sale cannot be negative')
            continue
        
        staff = Staff.query.get(staff_id)
        if not staff:
            errors.append(f'Row {i+1}: Invalid staff member')
            continue
        
        settings = AppSettings.get_or_create()
        tip_amount, tip_outs = calculate_tip_breakdown(
            turnover,
            cash_total,
            credit_card,
            settings.tip_out_basis,
            settings.tip_rules,
            credit_sale=credit_sale,
        )
        cc_commission, combined_tips = tip_outs_to_legacy(tip_outs)
        
        existing_cashup = None
        if cashup_id_str:
            try:
                cashup_id = int(cashup_id_str)
                existing_cashup = CashUp.query.get(cashup_id)
            except (ValueError, TypeError):
                existing_cashup = None
        
        if existing_cashup and not existing_cashup.submitted:
            existing_cashup.staff_id = staff_id
            existing_cashup.date = entry_date_obj
            existing_cashup.turnover = turnover
            existing_cashup.cash_total = cash_total
            existing_cashup.credit_card_total = credit_card
            existing_cashup.credit_sale = credit_sale
            existing_cashup.tip_amount = tip_amount
            existing_cashup.set_tip_outs(tip_outs_as_float_dict(tip_outs))
            cashup_ids_to_keep.append(existing_cashup.id)
            row_ids.append({'index': i, 'id': existing_cashup.id})
            saved_count += 1
        else:
            cashup = CashUp(
                staff_id=staff_id,
                date=entry_date_obj,
                turnover=turnover,
                cash_total=cash_total,
                credit_card_total=credit_card,
                credit_sale=credit_sale,
                tip_amount=tip_amount,
                cc_commission=cc_commission,
                combined_tips=combined_tips,
                submitted=False
            )
            cashup.set_tip_outs(tip_outs_as_float_dict(tip_outs))
            db.session.add(cashup)
            db.session.flush()  # get id before commit
            cashup_ids_to_keep.append(cashup.id)
            row_ids.append({'index': i, 'id': cashup.id})
            saved_count += 1
    
    if errors:
        db.session.rollback()
        return {
            'success': False,
            'errors': errors,
            'entry_date': entry_date_obj.isoformat(),
            'row_ids': [],
            'saved_count': 0
        }
    
    # Delete draft cashups for this date that were removed from the form
    draft_cashups_to_delete = CashUp.query.filter(
        CashUp.date == entry_date_obj,
        CashUp.submitted.is_(False)
    ).all()
    
    for draft in draft_cashups_to_delete:
        if draft.id not in cashup_ids_to_keep:
            db.session.delete(draft)
    
    db.session.commit()
    
    # Keep tips sheet in sync with waiter tip amounts (drafts + updates)
    sync_waiter_tips_for_date(entry_date_obj)
    
    return {
        'success': True,
        'errors': [],
        'entry_date': entry_date_obj.isoformat(),
        'row_ids': row_ids,
        'saved_count': saved_count
    }


def sync_waiter_tips_for_date(entry_date):
    """Upsert WaiterTip rows from cash-ups for waiters on a given date."""
    cashups = CashUp.query.filter_by(date=entry_date).all()
    
    # Sum tip amounts per waiter staff_id (in case of multiple rows)
    tips_by_staff = {}
    for cashup in cashups:
        staff = cashup.staff
        if not is_waiter(staff):
            continue
        tips_by_staff[cashup.staff_id] = tips_by_staff.get(cashup.staff_id, Decimal('0')) + Decimal(cashup.tip_amount)
    
    # Remove tip sheet rows for waiters who no longer have a cash-up that day
    existing_tips = WaiterTip.query.filter_by(date=entry_date).all()
    for tip in existing_tips:
        if tip.staff_id not in tips_by_staff:
            db.session.delete(tip)
    
    for staff_id, tip_amount in tips_by_staff.items():
        waiter_tip = WaiterTip.query.filter_by(staff_id=staff_id, date=entry_date).first()
        if waiter_tip:
            waiter_tip.tip_amount = tip_amount
            waiter_tip.box_office_amount = 0
        else:
            db.session.add(WaiterTip(
                staff_id=staff_id,
                date=entry_date,
                tip_amount=tip_amount,
                box_office_amount=0
            ))
    
    db.session.commit()


@cashup_bp.route('/new', methods=['GET', 'POST'])
def new_cashup():
    """Capture new cash-ups"""
    if request.method == 'POST':
        result = persist_cashup_drafts(request.form)
        
        if not result['success']:
            for error in result['errors']:
                flash(error, 'error')
            redirect_date = result.get('entry_date')
            if redirect_date:
                return redirect(url_for('cashup.new_cashup', date=redirect_date))
            return redirect(url_for('cashup.new_cashup'))
        
        if result['saved_count'] > 0:
            flash(f"Successfully saved {result['saved_count']} cash-up(s) as draft", 'success')
        else:
            flash('Card machine totals saved. Add staff rows to save cash-ups.', 'success')
        
        return redirect(url_for('cashup.new_cashup', date=result['entry_date']))
    
    # GET request - show form with cash-up history
    active_staff = Staff.query.filter_by(active=True).order_by(Staff.name).all()
    # Default to yesterday since cashups are done after midnight (for the previous day)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    
    # Get filter parameters for cash-up history
    filter_date = request.args.get('date', yesterday)  # Default to yesterday (since cashups are done after midnight)
    filter_staff_id = request.args.get('staff_id', '')
    
    # Build query for submitted cash-ups (history)
    submitted_query = CashUp.query.join(Staff).filter(CashUp.submitted.is_(True))
    
    # Build query for draft cash-ups (current)
    draft_query = CashUp.query.join(Staff).filter(CashUp.submitted.is_(False))
    
    # Always filter by date (required - show only one date at a time)
    if filter_date:
        try:
            filter_date_obj = datetime.strptime(filter_date, '%Y-%m-%d').date()
            submitted_query = submitted_query.filter(CashUp.date == filter_date_obj)
            draft_query = draft_query.filter(CashUp.date == filter_date_obj)
        except ValueError:
            # If invalid date, default to today
            filter_date_obj = date.today()
            filter_date = today
            submitted_query = submitted_query.filter(CashUp.date == filter_date_obj)
            draft_query = draft_query.filter(CashUp.date == filter_date_obj)
    else:
        # Default to today if no date provided
        filter_date_obj = date.today()
        filter_date = today
        submitted_query = submitted_query.filter(CashUp.date == filter_date_obj)
        draft_query = draft_query.filter(CashUp.date == filter_date_obj)
    
    if filter_staff_id:
        try:
            staff_id_int = int(filter_staff_id)
            submitted_query = submitted_query.filter(CashUp.staff_id == staff_id_int)
            draft_query = draft_query.filter(CashUp.staff_id == staff_id_int)
        except ValueError:
            pass
    
    # Order by staff name (since we're showing only one date)
    submitted_cashups = submitted_query.order_by(Staff.name).all()
    draft_cashups = draft_query.order_by(Staff.name).all()
    
    # Use submitted cashups for history display
    cashups = submitted_cashups
    settings = AppSettings.get_or_create()
    tip_rules = settings.enabled_tip_rules()
    
    # Calculate totals for submitted cashups (history)
    total_turnover = sum(float(c.turnover) for c in cashups)
    total_cash = sum(float(c.cash_total) for c in cashups)
    total_credit_card = sum(float(c.credit_card_total) for c in cashups)
    total_credit_sale = sum(float(c.credit_sale or 0) for c in cashups)
    total_tips = sum(float(c.tip_amount) for c in cashups)
    total_tip_outs = sum_tip_outs_for_rows(cashups, tip_rules)
    
    # Calculate totals for draft cashups
    draft_total_turnover = sum(float(c.turnover) for c in draft_cashups)
    draft_total_cash = sum(float(c.cash_total) for c in draft_cashups)
    draft_total_credit_card = sum(float(c.credit_card_total) for c in draft_cashups)
    draft_total_credit_sale = sum(float(c.credit_sale or 0) for c in draft_cashups)
    draft_total_tips = sum(float(c.tip_amount) for c in draft_cashups)
    draft_tip_outs = sum_tip_outs_for_rows(draft_cashups, tip_rules)
    
    # Total CC for the day (includes both submitted and draft cashups)
    day_total_cc = total_credit_card + draft_total_credit_card
    
    # Total Turnover for the day (includes both submitted and draft cashups)
    day_total_turnover = total_turnover + draft_total_turnover
    day_total_cash = total_cash + draft_total_cash
    day_total_credit_sale = total_credit_sale + draft_total_credit_sale
    day_total_net_turnover = day_total_turnover - day_total_credit_sale
    
    # Day tip-out totals
    day_tip_outs = {
        rule['key']: total_tip_outs.get(rule['key'], 0) + draft_tip_outs.get(rule['key'], 0)
        for rule in tip_rules
    }
    
    # Get saved card machine batch totals for this date
    card_batches = CardMachineBatch.query.filter_by(date=filter_date_obj).all()
    card_batch_dict = {batch.terminal_id: float(batch.batch_total) for batch in card_batches}
    total_batches_calculated = sum(card_batch_dict.values())
    
    tip_settings_json = json.dumps({
        'tip_out_basis': settings.tip_out_basis,
        'tip_rules': tip_rules,
        'currency_symbol': settings.currency_symbol,
    })
    
    return render_template('cashup/new.html', 
                         staff_list=active_staff, 
                         today=today,
                         yesterday=yesterday,
                         cashups=cashups,
                         draft_cashups=draft_cashups,
                         filter_date=filter_date,
                         filter_staff_id=filter_staff_id,
                         total_turnover=total_turnover,
                         total_cash=total_cash,
                         total_credit_card=total_credit_card,
                         total_credit_sale=total_credit_sale,
                         total_tips=total_tips,
                         total_tip_outs=total_tip_outs,
                         draft_total_turnover=draft_total_turnover,
                         draft_total_cash=draft_total_cash,
                         draft_total_credit_card=draft_total_credit_card,
                         draft_total_credit_sale=draft_total_credit_sale,
                         draft_total_tips=draft_total_tips,
                         draft_tip_outs=draft_tip_outs,
                         day_total_cc=day_total_cc,
                         day_total_turnover=day_total_turnover,
                         day_total_cash=day_total_cash,
                         day_total_credit_sale=day_total_credit_sale,
                         day_total_net_turnover=day_total_net_turnover,
                         day_tip_outs=day_tip_outs,
                         tip_rules=tip_rules,
                         tip_settings_json=tip_settings_json,
                         card_machine_terminals=CARD_MACHINE_TERMINALS,
                         card_batch_dict=card_batch_dict,
                         total_batches_calculated=total_batches_calculated,
                         has_drafts=len(draft_cashups) > 0)


@cashup_bp.route('/autosave', methods=['POST'])
def autosave_cashup():
    """Auto-save draft cash-ups without leaving the page"""
    result = persist_cashup_drafts(request.form)
    status = 200 if result['success'] else 400
    return jsonify(result), status


@cashup_bp.route('/print')
def print_cashup():
    """Printable / PDF cash-up sheet for a selected date"""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    date_str = request.args.get('date', yesterday)
    
    try:
        sheet_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        sheet_date = date.today() - timedelta(days=1)
    
    # Prefer submitted rows so drafts don't duplicate after submit.
    # If nothing is submitted yet, print the current drafts.
    submitted_rows = CashUp.query.join(Staff).filter(
        CashUp.date == sheet_date,
        CashUp.submitted.is_(True)
    ).order_by(Staff.name).all()
    if submitted_rows:
        rows = submitted_rows
        sheet_status = 'Submitted'
    else:
        rows = CashUp.query.join(Staff).filter(
            CashUp.date == sheet_date,
            CashUp.submitted.is_(False)
        ).order_by(Staff.name).all()
        sheet_status = 'Draft'
    
    settings = AppSettings.get_or_create()
    tip_rules = settings.enabled_tip_rules()
    
    day_total_turnover = sum(float(c.turnover) for c in rows)
    day_total_cash = sum(float(c.cash_total) for c in rows)
    day_total_cc = sum(float(c.credit_card_total) for c in rows)
    day_total_credit_sale = sum(float(c.credit_sale or 0) for c in rows)
    day_total_net_turnover = day_total_turnover - day_total_credit_sale
    day_total_tips = sum(float(c.tip_amount) for c in rows)
    day_tip_outs = sum_tip_outs_for_rows(rows, tip_rules)
    
    card_batches = CardMachineBatch.query.filter_by(date=sheet_date).all()
    card_batch_dict = {batch.terminal_id: float(batch.batch_total) for batch in card_batches}
    total_batches = sum(card_batch_dict.values())
    
    return render_template(
        'cashup/print.html',
        sheet_date=sheet_date,
        rows=rows,
        sheet_status=sheet_status,
        day_total_turnover=day_total_turnover,
        day_total_cash=day_total_cash,
        day_total_cc=day_total_cc,
        day_total_credit_sale=day_total_credit_sale,
        day_total_net_turnover=day_total_net_turnover,
        day_total_tips=day_total_tips,
        day_tip_outs=day_tip_outs,
        tip_rules=tip_rules,
        card_machine_terminals=CARD_MACHINE_TERMINALS,
        card_batch_dict=card_batch_dict,
        total_batches=total_batches
    )


@cashup_bp.route('/waiter-slips')
def waiter_slips():
    """Blank A6 waiter cash-up slips — 4 per A4 sheet for handwritten fill-in."""
    return render_template('cashup/waiter_slips.html')


@cashup_bp.route('/submit', methods=['POST'])
def submit_cashup():
    """Save current form as drafts, then finalize them (overwrite any prior submission)."""
    date_str = (
        request.form.get('entry_date')
        or request.form.get('submit_date')
        or request.form.get('date')
    )

    if not date_str:
        flash('Date is required', 'error')
        return redirect(url_for('cashup.new_cashup'))

    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError as e:
        flash(f'Invalid date format: {str(e)}', 'error')
        return redirect(url_for('cashup.new_cashup'))

    # Persist latest form values as drafts first (when full sheet is posted)
    if request.form.getlist('staff_id'):
        result = persist_cashup_drafts(request.form)
        if not result['success']:
            for error in result['errors']:
                flash(error, 'error')
            return redirect(url_for('cashup.new_cashup', date=date_str))
        date_str = result.get('entry_date') or date_str
        try:
            entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    draft_cashups = CashUp.query.filter(
        CashUp.date == entry_date,
        CashUp.submitted.is_(False)
    ).all()

    if not draft_cashups:
        flash('No draft cashups found for this date', 'error')
        return redirect(url_for('cashup.new_cashup', date=date_str))

    try:
        # Overwrite any previously submitted rows for this date so print has no duplicates
        prior_submitted = CashUp.query.filter(
            CashUp.date == entry_date,
            CashUp.submitted.is_(True)
        ).all()
        for row in prior_submitted:
            db.session.delete(row)

        for cashup in draft_cashups:
            cashup.submitted = True

        db.session.commit()
        sync_waiter_tips_for_date(entry_date)
        waiter_count = WaiterTip.query.filter_by(date=entry_date).count()
        flash(f'Successfully submitted {len(draft_cashups)} cash-up(s) to history', 'success')
        if waiter_count > 0:
            flash(f'Updated tips sheet for {waiter_count} waiter(s)', 'success')
    except Exception as commit_error:
        db.session.rollback()
        flash(f'Error committing changes: {str(commit_error)}', 'error')
        return redirect(url_for('cashup.new_cashup', date=date_str))

    return redirect(url_for('cashup.new_cashup', date=date_str))


@cashup_bp.route('/list')
def list_cashups():
    """Redirect to new cash-up page (history is now shown there)"""
    return redirect(url_for('cashup.new_cashup'))


@cashup_bp.route('/clear-all', methods=['POST'])
def clear_all_cashups():
    """Clear all cash-up figures for testing. Keeps staff and settings."""
    cashup_count = CashUp.query.count()
    tip_count = WaiterTip.query.count()
    batch_count = CardMachineBatch.query.count()
    summary_count = DailySummary.query.count()

    WaiterTip.query.delete()
    CardMachineBatch.query.delete()
    DailySummary.query.delete()
    CashUp.query.delete()
    db.session.commit()

    flash(
        f'Cleared test data: {cashup_count} cash-up(s), {tip_count} tip row(s), '
        f'{batch_count} batch(es), {summary_count} daily summar(ies). Staff kept.',
        'success'
    )
    return redirect(url_for('cashup.new_cashup'))


@cashup_bp.route('/tips', methods=['GET'])
def tips_sheet():
    """Weekly tips sheet showing waiter tips"""
    # Get week start date (default to current week Monday)
    week_start_str = request.args.get('week_start', '')
    
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        except ValueError:
            week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        # Default to Monday of current week
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    
    # Calculate week end (Sunday)
    week_end = week_start + timedelta(days=6)
    
    # Get all waiters marked as waiters
    waiters = Staff.query.filter_by(active=True, is_waiter=True).order_by(Staff.name).all()
    
    # Live tip amounts from cash-ups (draft + submitted) so tips sheet stays current
    cashups = CashUp.query.join(Staff).filter(
        Staff.is_waiter.is_(True),
        CashUp.date >= week_start,
        CashUp.date <= week_end
    ).all()
    
    # Organize by waiter and date
    tips_by_waiter = {}
    for waiter in waiters:
        tips_by_waiter[waiter.id] = {
            'name': waiter.name,
            'tips': {}
        }
    
    for cashup in cashups:
        if cashup.staff_id not in tips_by_waiter:
            continue
        day_tips = tips_by_waiter[cashup.staff_id]['tips']
        current = day_tips.get(cashup.date, {'tip_amount': 0.0})['tip_amount']
        day_tips[cashup.date] = {
            'tip_amount': current + float(cashup.tip_amount)
        }
    
    # Calculate totals for each waiter
    for waiter_id, data in tips_by_waiter.items():
        total_tips = sum(t['tip_amount'] for t in data['tips'].values())
        data['total_tips'] = total_tips
    
    # Generate list of dates in the week
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    
    # Calculate week totals
    week_total_tips = sum(data['total_tips'] for data in tips_by_waiter.values())
    
    # Previous and next week
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    
    return render_template('cashup/tips.html',
                         week_start=week_start,
                         week_end=week_end,
                         week_dates=week_dates,
                         tips_by_waiter=tips_by_waiter,
                         week_total_tips=week_total_tips,
                         prev_week=prev_week,
                         next_week=next_week)


# Settings blueprint
settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/', methods=['GET', 'POST'])
def settings_page():
    """Application settings: currency and tip-out rules."""
    settings = AppSettings.get_or_create()

    if request.method == 'POST':
        currency = (request.form.get('currency') or 'ZAR').upper()
        if currency not in CURRENCIES:
            currency = 'ZAR'

        tip_out_basis = request.form.get('tip_out_basis') or 'tips'
        if tip_out_basis not in ('tips', 'turnover'):
            tip_out_basis = 'tips'

        keys = request.form.getlist('rule_key')
        labels = request.form.getlist('rule_label')
        percents = request.form.getlist('rule_percent')
        enabled_values = set(request.form.getlist('rule_enabled'))

        rebuilt = []
        used_keys = set()
        for i, label in enumerate(labels):
            label = (label or '').strip()
            if not label:
                continue
            raw_key = keys[i] if i < len(keys) else ''
            key = slugify_key(raw_key or label, used_keys)
            used_keys.add(key)
            try:
                percent = float(percents[i]) if i < len(percents) else 0
            except (TypeError, ValueError):
                percent = 0
            rebuilt.append({
                'key': key,
                'label': label,
                'percent': percent,
                'enabled': (key in enabled_values) or (str(i) in enabled_values),
            })

        settings.currency = currency
        settings.tip_out_basis = tip_out_basis
        settings.tip_rules = normalize_tip_rules(rebuilt)
        db.session.commit()
        flash('Settings saved', 'success')
        return redirect(url_for('settings.settings_page'))

    return render_template(
        'settings/settings.html',
        settings=settings,
        currencies=CURRENCIES,
        tip_out_basis_choices=TIP_OUT_BASIS_CHOICES,
        tip_out_presets=TIP_OUT_PRESETS,
    )



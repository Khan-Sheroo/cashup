"""Recipe cost calculator: items masterlist and recipes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from cashup import db
from cashup.category_rules import guess_category
from decimal import Decimal

from cashup.models import BATCH_YIELD_UNITS, CostItem, InvoiceLine, Location, Recipe, RecipeLine, SalesLine
from cashup.production import YIELD_UNIT_VALUES, sync_output_item
from cashup.recipe_util import COMMON_UNITS, DEFAULT_CATEGORIES, is_valid_unit, to_decimal

recipes_bp = Blueprint('recipes', __name__, url_prefix='/recipes')


def _parse_sale_price(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    value = to_decimal(raw)
    if value is None or value < 0:
        return False
    return value


def _replace_recipe_lines(recipe, item_ids, quantities):
    """Rebuild recipe lines from parallel form lists."""
    recipe.lines.clear()
    db.session.flush()

    order = 0
    for i, raw_item_id in enumerate(item_ids):
        try:
            item_id = int(raw_item_id)
        except (TypeError, ValueError):
            continue
        item = CostItem.query.get(item_id)
        if not item:
            continue
        qty = to_decimal(quantities[i] if i < len(quantities) else None, None)
        if qty is None or qty <= 0:
            continue
        recipe.lines.append(RecipeLine(
            item_id=item.id,
            quantity=qty,
            sort_order=order,
        ))
        order += 1


def _recipe_list_rows():
    """Build recipe rows with cost, net sale, margin, and profit."""
    recipes = Recipe.query.order_by(Recipe.name).all()
    rows = []
    for recipe in recipes:
        cost = recipe.serving_cost()
        rows.append({
            'recipe': recipe,
            'cost': cost,
            'net_sale': recipe.net_sale(),
            'margin': recipe.margin_percent(),
            'profit': recipe.gross_profit_amount(),
        })
    return rows


def _parse_location_id(raw):
    try:
        location_id = int(raw)
    except (TypeError, ValueError):
        return None
    return location_id if Location.query.get(location_id) else None


def _render_recipe_form(recipe, items):
    if recipe is not None and recipe.output_item_id:
        items = [i for i in items if i.id != recipe.output_item_id]
    return render_template(
        'recipes/edit.html',
        recipe=recipe,
        items=items,
        common_units=COMMON_UNITS,
        locations=Location.ordered(),
        batch_yield_units=BATCH_YIELD_UNITS,
    )


def _read_batch_form():
    """(is_batch, yield_qty, yield_unit, portion_qty, error) from the recipe form."""
    form = request.form
    if form.get('is_batch') != 'on':
        return False, None, None, None, None
    yield_qty = to_decimal(form.get('yield_qty'), None)
    yield_unit = form.get('yield_unit') or 'portion'
    portion_qty = to_decimal(form.get('portion_qty'), None) or Decimal('1')
    if yield_qty is None or yield_qty <= 0:
        return True, None, None, None, 'Enter the batch yield (how much one batch makes)'
    if yield_unit not in YIELD_UNIT_VALUES:
        return True, None, None, None, 'Choose a valid yield unit'
    if portion_qty <= 0 or portion_qty > yield_qty:
        return True, None, None, None, 'Portion size must be more than zero and no bigger than the batch'
    return True, yield_qty, yield_unit, portion_qty, None


def _apply_batch_settings(recipe, batch_values, was_batch):
    is_batch, yield_qty, yield_unit, portion_qty, _error = batch_values
    recipe.is_batch = is_batch
    if not is_batch:
        return
    recipe.yield_qty, recipe.yield_unit, recipe.portion_qty = yield_qty, yield_unit, portion_qty
    if not was_batch and request.form.get('scale_to_batch') == 'on':
        factor = yield_qty / portion_qty
        for line in recipe.lines:
            line.quantity = (Decimal(line.quantity) * factor).quantize(Decimal('0.0001'))
    db.session.flush()
    sync_output_item(recipe)
    recipe.lines[:] = [l for l in recipe.lines if l.item_id != recipe.output_item_id]


@recipes_bp.route('/')
def list_recipes():
    """List all recipes with cost and margin."""
    return render_template('recipes/list.html', rows=_recipe_list_rows())


@recipes_bp.route('/import-workbook', methods=['POST'])
def import_workbook_route():
    """Import items and recipes from the Recipe Costing .xlsm workbook."""
    from cashup.inventory_routes import _backup_database
    from cashup.recipe_workbook_import import import_workbook

    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Choose the costing workbook (.xlsm / .xlsx)', 'error')
        return redirect(url_for('recipes.list_recipes'))
    _backup_database()
    try:
        report = import_workbook(upload, source_name=upload.filename)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f'Could not import workbook: {exc}', 'error')
        return redirect(url_for('recipes.list_recipes'))
    flash(f'Imported {len(report.recipes_created)} new and {len(report.recipes_updated)} updated recipes; '
          f'{len(report.items_created)} new items ({len(set(report.items_reused))} existing items reused); '
          f'{len(report.pos_linked)} sales mix names linked to recipes.', 'success')
    if report.warnings:
        flash('Check: ' + ' · '.join(report.warnings[:12]), 'warning')
    return redirect(url_for('recipes.list_recipes'))


@recipes_bp.route('/print')
def print_recipes():
    """Printable / PDF recipe list — no edit or delete controls."""
    mode = (request.args.get('mode') or '').strip().lower()
    if mode not in ('print', 'pdf'):
        mode = ''
    return render_template(
        'recipes/print.html',
        rows=_recipe_list_rows(),
        auto_mode=mode,
    )


@recipes_bp.route('/new', methods=['GET', 'POST'])
def new_recipe():
    """Create a recipe from cost items."""
    items = CostItem.query.filter_by(active=True).order_by(CostItem.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        notes = request.form.get('notes', '').strip() or None
        sale = _parse_sale_price(request.form.get('sale_price'))

        if not name:
            flash('Recipe name is required', 'error')
            return _render_recipe_form(None, items)
        if sale is False:
            flash('Sale price must be a valid number', 'error')
            return _render_recipe_form(None, items)
        if Recipe.query.filter_by(name=name).first():
            flash(f'Recipe "{name}" already exists', 'error')
            return _render_recipe_form(None, items)
        batch_values = _read_batch_form()
        if batch_values[4]:
            flash(batch_values[4], 'error')
            return _render_recipe_form(None, items)

        recipe = Recipe(
            name=name, sale_price=sale, notes=notes,
            location_id=_parse_location_id(request.form.get('location_id')),
        )
        db.session.add(recipe)
        db.session.flush()
        _replace_recipe_lines(
            recipe,
            request.form.getlist('line_item_id'),
            request.form.getlist('line_quantity'),
        )
        _apply_batch_settings(recipe, batch_values, was_batch=True)
        db.session.commit()
        flash(f'Recipe "{name}" created', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    return _render_recipe_form(None, items)


@recipes_bp.route('/<int:recipe_id>', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    """Edit recipe lines, sale price, and view margin."""
    recipe = Recipe.query.get_or_404(recipe_id)
    items = CostItem.query.filter_by(active=True).order_by(CostItem.name).all()
    # Keep inactive items that are already on the recipe selectable
    used_ids = {line.item_id for line in recipe.lines}
    for item in CostItem.query.filter(CostItem.id.in_(used_ids)).all() if used_ids else []:
        if item not in items:
            items.append(item)
    items.sort(key=lambda i: i.name.lower())

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        notes = request.form.get('notes', '').strip() or None
        sale = _parse_sale_price(request.form.get('sale_price'))

        if not name:
            flash('Recipe name is required', 'error')
            return _render_recipe_form(recipe, items)
        if sale is False:
            flash('Sale price must be a valid number', 'error')
            return _render_recipe_form(recipe, items)
        duplicate = Recipe.query.filter(
            Recipe.name == name,
            Recipe.id != recipe.id,
        ).first()
        if duplicate:
            flash(f'Recipe "{name}" already exists', 'error')
            return _render_recipe_form(recipe, items)
        batch_values = _read_batch_form()
        if batch_values[4]:
            flash(batch_values[4], 'error')
            return _render_recipe_form(recipe, items)

        was_batch = recipe.is_batch
        recipe.name = name
        recipe.sale_price = sale
        recipe.notes = notes
        recipe.location_id = _parse_location_id(request.form.get('location_id'))
        _replace_recipe_lines(
            recipe,
            request.form.getlist('line_item_id'),
            request.form.getlist('line_quantity'),
        )
        _apply_batch_settings(recipe, batch_values, was_batch)
        db.session.commit()
        flash(f'Recipe "{name}" saved', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    return _render_recipe_form(recipe, items)


@recipes_bp.route('/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    name = recipe.name
    from cashup.models import ProductionLine
    if ProductionLine.query.filter_by(recipe_id=recipe.id).first():
        flash(f'"{name}" has production history — delete those production sheets first', 'error')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))
    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{name}" deleted', 'success')
    return redirect(url_for('recipes.list_recipes'))


def used_categories() -> list[str]:
    return sorted({
        c for (c,) in db.session.query(CostItem.category).filter(CostItem.category.isnot(None)).distinct()
        if c
    }, key=str.lower)


def category_suggestions() -> list[str]:
    """Categories in use first, then the defaults not yet used."""
    used = used_categories()
    used_lower = {c.lower() for c in used}
    return used + [c for c in DEFAULT_CATEGORIES if c.lower() not in used_lower]


@recipes_bp.route('/items')
def list_items():
    """Master list of cost items, grouped by category."""
    selected = request.args.get('category', '')
    items = CostItem.query.all()
    counts: dict[str, int] = {}
    for item in items:
        key = item.category or ''
        counts[key] = counts.get(key, 0) + 1
    if selected == '__none__':
        items = [i for i in items if not i.category]
    elif selected:
        items = [i for i in items if (i.category or '') == selected]
    items.sort(key=lambda i: ((i.category or '\uffff').lower(), i.name.lower()))
    category_counts = sorted(((c, n) for c, n in counts.items() if c), key=lambda x: x[0].lower())
    return render_template(
        'recipes/items.html',
        items=items,
        common_units=COMMON_UNITS,
        category_counts=category_counts,
        uncategorised_count=counts.get('', 0),
        selected_category=selected,
        category_suggestions=category_suggestions(),
    )


def _safe_next(default_endpoint):
    target = request.form.get('next') or ''
    if target.startswith('/') and not target.startswith('//'):
        return target
    return url_for(default_endpoint)


@recipes_bp.route('/items/categorize', methods=['POST'])
def categorize_items():
    """Assign (or clear) the category on several items at once."""
    ids = []
    for raw in request.form.getlist('item_ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    category = (request.form.get('category') or '').strip()[:80] or None
    if not ids:
        flash('Tick at least one item first', 'error')
        return redirect(_safe_next('recipes.list_items'))
    if category:
        existing = next((c for c in used_categories() if c.lower() == category.lower()), None)
        category = existing or category
    items = CostItem.query.filter(CostItem.id.in_(ids)).all()
    for item in items:
        item.category = category
    db.session.commit()
    flash(f'{len(items)} item{"s" if len(items) != 1 else ""} moved to '
          f'{category or "Uncategorised"}', 'success')
    return redirect(_safe_next('recipes.list_items'))


def _matching_category(category):
    """Reuse the spelling of a category already in use (e.g. 'spirits' -> 'Spirits')."""
    if not category:
        return None
    return next((c for c in used_categories() if c.lower() == category.lower()), category)


@recipes_bp.route('/items/auto-categorize', methods=['POST'])
def auto_categorize_items():
    """Fill in categories for uncategorised / 'From Sales Mix' items using the name rules."""
    candidates = CostItem.query.filter(
        db.or_(CostItem.category.is_(None), CostItem.category == '',
               CostItem.category == 'From Sales Mix')
    ).all()
    sold_ids = {i for (i,) in db.session.query(SalesLine.item_id).filter(SalesLine.item_id.isnot(None))}
    bought_ids = {i for (i,) in db.session.query(InvoiceLine.item_id).filter(InvoiceLine.item_id.isnot(None))}
    moved: dict[str, int] = {}
    for item in candidates:
        menu_item = item.category == 'From Sales Mix' or (item.id in sold_ids and item.id not in bought_ids)
        category = _matching_category(guess_category(item.name, menu_item=menu_item))
        if category and category != item.category:
            item.category = category
            moved[category] = moved.get(category, 0) + 1
    db.session.commit()
    if moved:
        summary = ', '.join(f'{c} ({n})' for c, n in sorted(moved.items()))
        flash(f'Categorised {sum(moved.values())} item(s): {summary}', 'success')
    else:
        flash('No uncategorised items matched a category rule', 'info')
    return redirect(_safe_next('recipes.list_items'))


@recipes_bp.route('/categories/rename', methods=['POST'])
def rename_category():
    """Rename a category everywhere, or merge it into another one."""
    old = (request.form.get('old') or '').strip()
    new = (request.form.get('new') or '').strip()[:80]
    if not old or not new:
        flash('Enter the new category name', 'error')
        return redirect(url_for('recipes.list_items'))
    existing = next((c for c in used_categories() if c.lower() == new.lower() and c != old), None)
    target = existing or new
    count = CostItem.query.filter(CostItem.category == old).update(
        {CostItem.category: target}, synchronize_session=False)
    db.session.commit()
    verb = 'merged into' if existing else 'renamed to'
    flash(f'Category "{old}" {verb} "{target}" ({count} items)', 'success')
    return redirect(url_for('recipes.list_items'))


def _render_item_form(item):
    return render_template(
        'recipes/item_form.html',
        item=item,
        common_units=COMMON_UNITS,
        categories=category_suggestions(),
    )


def _read_item_form(item_id=None):
    """Validate the item form. Returns (values dict, error message or None)."""
    form = request.form
    values = {
        'name': form.get('name', '').strip(),
        'unit': form.get('unit', '').strip(),
        'pack_size': to_decimal(form.get('pack_size'), None),
        'cost_price': to_decimal(form.get('cost_price'), None),
        'active': form.get('active') == 'on',
        'category': form.get('category', '').strip() or None,
        'count_unit': form.get('count_unit', '').strip() or None,
        'count_factor': to_decimal(form.get('count_factor'), None),
        'par_level': to_decimal(form.get('par_level'), None),
    }
    if not values['name']:
        return values, 'Item name is required'
    if not is_valid_unit(values['unit']):
        return values, 'Select a valid unit of measure'
    if values['pack_size'] is None or values['pack_size'] <= 0:
        return values, 'Pack size must be greater than zero'
    if values['cost_price'] is None or values['cost_price'] < 0:
        return values, 'Cost price must be a valid number'
    if values['count_factor'] is not None and values['count_factor'] <= 0:
        return values, 'Recipe units per count unit must be greater than zero'
    if values['par_level'] is not None and values['par_level'] < 0:
        return values, 'Par level cannot be negative'
    duplicate = CostItem.query.filter(CostItem.name == values['name'])
    if item_id is not None:
        duplicate = duplicate.filter(CostItem.id != item_id)
    if duplicate.first():
        return values, f'Item "{values["name"]}" already exists'
    return values, None


@recipes_bp.route('/items/add', methods=['GET', 'POST'])
def add_item():
    """Add a cost item with pack size, unit, and pack cost."""
    if request.method == 'POST':
        values, error = _read_item_form()
        if error:
            flash(error, 'error')
            return _render_item_form(None)
        guessed = not values['category'] and _matching_category(guess_category(values['name']))
        if guessed:
            values['category'] = guessed
        item = CostItem(**values)
        db.session.add(item)
        db.session.commit()
        flash(f'Item "{item.name}" added' + (f' to category "{guessed}"' if guessed else ''),
              'success')
        return redirect(url_for('recipes.list_items'))

    return _render_item_form(None)


@recipes_bp.route('/items/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    """Edit a cost item."""
    item = CostItem.query.get_or_404(item_id)

    if request.method == 'POST':
        values, error = _read_item_form(item.id)
        if error:
            flash(error, 'error')
            return _render_item_form(item)
        for key, value in values.items():
            setattr(item, key, value)
        db.session.commit()
        flash(f'Item "{item.name}" saved', 'success')
        return redirect(url_for('recipes.list_items'))

    return _render_item_form(item)


@recipes_bp.route('/items/<int:item_id>/toggle', methods=['POST'])
def toggle_item(item_id):
    item = CostItem.query.get_or_404(item_id)
    item.active = not item.active
    db.session.commit()
    status = 'activated' if item.active else 'deactivated'
    flash(f'Item "{item.name}" {status}', 'success')
    return redirect(url_for('recipes.list_items'))


@recipes_bp.route('/items/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    item = CostItem.query.get_or_404(item_id)
    if item.recipe_lines:
        recipes = sorted({line.recipe.name for line in item.recipe_lines if line.recipe})
        flash(
            f'Cannot delete "{item.name}" — used in: {", ".join(recipes)}',
            'error',
        )
        return redirect(url_for('recipes.list_items'))
    if item.movements.first() is not None:
        flash(f'Cannot delete "{item.name}" — it has stock history. Deactivate it instead.', 'error')
        return redirect(url_for('recipes.list_items'))
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{name}" deleted', 'success')
    return redirect(url_for('recipes.list_items'))

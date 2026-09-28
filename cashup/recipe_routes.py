"""Recipe cost calculator: items masterlist and recipes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from cashup import db
from cashup.models import CostItem, Location, Recipe, RecipeLine
from cashup.recipe_util import COMMON_UNITS, is_valid_unit, to_decimal

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
        cost = recipe.total_cost()
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
    return render_template(
        'recipes/edit.html',
        recipe=recipe,
        items=items,
        common_units=COMMON_UNITS,
        locations=Location.ordered(),
    )


@recipes_bp.route('/')
def list_recipes():
    """List all recipes with cost and margin."""
    return render_template('recipes/list.html', rows=_recipe_list_rows())


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

        recipe.name = name
        recipe.sale_price = sale
        recipe.notes = notes
        recipe.location_id = _parse_location_id(request.form.get('location_id'))
        _replace_recipe_lines(
            recipe,
            request.form.getlist('line_item_id'),
            request.form.getlist('line_quantity'),
        )
        db.session.commit()
        flash(f'Recipe "{name}" saved', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    return _render_recipe_form(recipe, items)


@recipes_bp.route('/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    name = recipe.name
    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{name}" deleted', 'success')
    return redirect(url_for('recipes.list_recipes'))


@recipes_bp.route('/items')
def list_items():
    """Master list of cost items."""
    items = CostItem.query.all()
    items.sort(key=lambda i: ((i.category or 'zzz').lower(), i.name.lower()))
    return render_template('recipes/items.html', items=items, common_units=COMMON_UNITS)


def _render_item_form(item):
    categories = sorted({
        c for (c,) in db.session.query(CostItem.category).filter(CostItem.category.isnot(None)).distinct()
        if c
    }, key=str.lower)
    return render_template(
        'recipes/item_form.html',
        item=item,
        common_units=COMMON_UNITS,
        categories=categories,
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
        item = CostItem(**values)
        db.session.add(item)
        db.session.commit()
        flash(f'Item "{item.name}" added', 'success')
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

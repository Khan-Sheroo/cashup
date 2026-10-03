"""Manufactured (batch) recipes: the made stock item and production postings."""
from __future__ import annotations

from decimal import Decimal

from cashup import db
from cashup.models import BATCH_YIELD_UNITS, CostItem, ProductionLine, ProductionRun, Recipe, StockMovement

ZERO = Decimal('0')
MANUFACTURED_CATEGORY = 'Manufactured'
# yield unit -> (made item unit, count unit, count factor)
OUTPUT_UNITS = {
    'portion': ('portion', 'portion', Decimal('1')),
    'each': ('each', 'each', Decimal('1')),
    'g': ('g', 'kg', Decimal('1000')),
    'kg': ('g', 'kg', Decimal('1000')),
    'ml': ('ml', 'L', Decimal('1000')),
    'L': ('ml', 'L', Decimal('1000')),
}
YIELD_UNIT_VALUES = {value for value, _label in BATCH_YIELD_UNITS}


def output_item_name(recipe: Recipe) -> str:
    return f'{recipe.name} (made)'[:200]


def sync_output_item(recipe: Recipe) -> CostItem | None:
    """Create or update the stock item a batch recipe produces (cost = batch cost / yield)."""
    if not recipe.is_batch or not recipe.yield_qty:
        return recipe.output_item
    unit, count_unit, count_factor = OUTPUT_UNITS.get(recipe.yield_unit or 'portion', OUTPUT_UNITS['portion'])
    item = recipe.output_item
    if item is None:
        item = CostItem.query.filter(db.func.lower(CostItem.name) == output_item_name(recipe).lower()).first()
    if item is None:
        item = CostItem(name=output_item_name(recipe), category=MANUFACTURED_CATEGORY, active=True,
                        unit=unit, pack_size=Decimal('1'), cost_price=ZERO)
        db.session.add(item)
    elif item.movements.count() and item.unit != unit:
        # Keep the unit stock was recorded in; only the costing changes below.
        unit = item.unit
    item.name = output_item_name(recipe)
    item.unit = unit
    item.count_unit = count_unit if item.count_unit in (None, '', 'portion', 'each', 'kg', 'L') else item.count_unit
    item.count_factor = count_factor
    db.session.flush()
    recipe.output_item = item
    recipe.output_item_id = item.id
    made = recipe.yield_to_item_units()
    item.pack_size = made if made > 0 else Decimal('1')
    item.cost_price = recipe.total_cost()
    db.session.flush()
    return item


def batch_usage(recipe: Recipe, batches) -> dict[int, Decimal]:
    batches = Decimal(batches)
    usage: dict[int, Decimal] = {}
    for line in recipe.lines:
        if line.item_id == recipe.output_item_id:
            continue
        usage[line.item_id] = usage.get(line.item_id, ZERO) + Decimal(line.quantity) * batches
    return usage


def post_production(run: ProductionRun) -> None:
    """Post stock movements for a production sheet: ingredients out, made items in."""
    StockMovement.query.filter_by(production_run_id=run.id).delete()
    for line in run.lines:
        recipe = Recipe.query.get(line.recipe_id)
        item = sync_output_item(recipe)
        batches = Decimal(line.batches)
        line.batch_cost = recipe.total_cost()
        line.output_qty = recipe.yield_to_item_units() * batches
        for item_id, qty in batch_usage(recipe, batches).items():
            ingredient = CostItem.query.get(item_id)
            db.session.add(StockMovement(
                item_id=item_id, location_id=run.location_id, movement_date=run.run_date,
                kind='production_use', quantity=-qty, unit_cost=ingredient.cost_per_unit(),
                note=f'{recipe.name} × {batches.normalize():f}', production_run_id=run.id,
            ))
        per_unit = (Decimal(line.batch_cost) / recipe.yield_to_item_units()
                    if recipe.yield_to_item_units() else ZERO)
        db.session.add(StockMovement(
            item_id=item.id, location_id=run.location_id, movement_date=run.run_date,
            kind='production_in', quantity=line.output_qty, unit_cost=per_unit,
            note=f'{batches.normalize():f} batch(es) of {recipe.name}', production_run_id=run.id,
        ))
    db.session.flush()


def delete_production(run: ProductionRun) -> None:
    StockMovement.query.filter_by(production_run_id=run.id).delete()
    db.session.delete(run)


__all__ = ['sync_output_item', 'post_production', 'delete_production', 'batch_usage',
           'YIELD_UNIT_VALUES', 'ProductionLine']

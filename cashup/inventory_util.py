"""Stock ledger queries: on-hand, sales explosion, and stock take variance."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from cashup import db
from cashup.models import CostItem, StockMovement, StockTake

ZERO = Decimal('0')


def _dec(value) -> Decimal:
    return Decimal(value) if value is not None else ZERO


def on_hand_map(location_id: int | None = None, as_of: date | None = None,
                exclude_stock_take_id: int | None = None) -> dict[int, Decimal]:
    """Sum of movements per item (recipe units)."""
    query = db.session.query(StockMovement.item_id, func.sum(StockMovement.quantity))
    if location_id is not None:
        query = query.filter(StockMovement.location_id == location_id)
    if as_of is not None:
        query = query.filter(StockMovement.movement_date <= as_of)
    if exclude_stock_take_id is not None:
        query = query.filter(
            (StockMovement.stock_take_id.is_(None))
            | (StockMovement.stock_take_id != exclude_stock_take_id)
        )
    return {item_id: _dec(total) for item_id, total in query.group_by(StockMovement.item_id)}


def on_hand(item_id: int, location_id: int | None = None, as_of: date | None = None) -> Decimal:
    return on_hand_map(location_id, as_of).get(item_id, ZERO)


def last_movement_dates(location_id: int | None = None) -> dict[int, date]:
    query = db.session.query(StockMovement.item_id, func.max(StockMovement.movement_date))
    if location_id is not None:
        query = query.filter(StockMovement.location_id == location_id)
    return dict(query.group_by(StockMovement.item_id).all())


def explode_recipe(recipe, sold_qty) -> dict[int, Decimal]:
    """Ingredient usage (recipe units) for sold_qty portions of a recipe.

    Manufactured recipes were already costed out of stock at production, so a sale pulls
    portions of the made item instead of the raw ingredients.
    """
    usage: dict[int, Decimal] = defaultdict(lambda: ZERO)
    qty = _dec(sold_qty)
    if getattr(recipe, 'is_manufactured', False):
        usage[recipe.output_item_id] += recipe.portion_item_units() * qty
        return dict(usage)
    for line in recipe.lines:
        usage[line.item_id] += _dec(line.quantity) * qty
    return dict(usage)


def previous_stock_take(stock_take: StockTake) -> StockTake | None:
    return (
        StockTake.query
        .filter(
            StockTake.location_id == stock_take.location_id,
            StockTake.status == 'confirmed',
            StockTake.id != stock_take.id,
            StockTake.count_date < stock_take.count_date,
        )
        .order_by(StockTake.count_date.desc(), StockTake.id.desc())
        .first()
    )


def period_summary(stock_take: StockTake) -> dict:
    """Variance rows for a stock take versus the ledger since the previous count.

    Opening   = stock at the previous confirmed count date (or zero)
    Expected  = Opening + every movement in the period (excluding this count's adjustment)
    Variance  = Counted - Expected   (positive = over, negative = under)
    """
    location_id = stock_take.location_id
    end = stock_take.count_date
    prev = previous_stock_take(stock_take)
    start = prev.count_date if prev else None

    opening = on_hand_map(location_id, start) if start else {}

    query = db.session.query(
        StockMovement.item_id, StockMovement.kind, func.sum(StockMovement.quantity)
    ).filter(
        StockMovement.location_id == location_id,
        StockMovement.movement_date <= end,
        (StockMovement.stock_take_id.is_(None)) | (StockMovement.stock_take_id != stock_take.id),
    )
    if start:
        query = query.filter(StockMovement.movement_date > start)
    by_kind: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for item_id, kind, total in query.group_by(StockMovement.item_id, StockMovement.kind):
        by_kind[item_id][kind] += _dec(total)

    counted = {line.item_id: line for line in stock_take.lines}
    item_ids = set(opening) | set(by_kind) | set(counted)
    items = {i.id: i for i in CostItem.query.filter(CostItem.id.in_(item_ids)).all()} if item_ids else {}

    rows = []
    totals = {'over_value': ZERO, 'under_value': ZERO, 'net_value': ZERO,
              'expected_value': ZERO, 'counted_value': ZERO, 'usage_value': ZERO}
    for item_id in item_ids:
        item = items.get(item_id)
        if item is None:
            continue
        kinds = by_kind.get(item_id, {})
        open_qty = opening.get(item_id, ZERO)
        purchases = kinds.get('purchase', ZERO) + kinds.get('opening', ZERO)
        transfers_in = kinds.get('transfer_in', ZERO)
        transfers_out = kinds.get('transfer_out', ZERO)
        adjustments = (kinds.get('manual', ZERO) + kinds.get('waste', ZERO)
                       + kinds.get('stocktake_adjust', ZERO))
        sales = kinds.get('sale', ZERO)
        production = kinds.get('production_in', ZERO) + kinds.get('production_use', ZERO)
        expected = open_qty + sum(kinds.values(), ZERO)

        line = counted.get(item_id)
        if stock_take.status == 'confirmed' and line is not None and line.expected_base is not None:
            expected = _dec(line.expected_base)
        unit_cost = (_dec(line.unit_cost) if line is not None and line.unit_cost is not None
                     else item.cost_per_unit())
        counted_base = item.to_base_units(line.counted) if line is not None else None
        variance = counted_base - expected if counted_base is not None else None
        variance_value = variance * unit_cost if variance is not None else None

        if (line is None and expected == 0 and not kinds):
            continue

        row = {
            'item': item,
            'factor': item.effective_count_factor(),
            'opening': open_qty,
            'purchases': purchases,
            'transfers_in': transfers_in,
            'transfers_out': transfers_out,
            'adjustments': adjustments,
            'sales': sales,
            'production': production,
            'expected': expected,
            'counted': counted_base,
            'variance': variance,
            'variance_value': variance_value,
            'variance_pct': (variance / expected * 100) if variance is not None and expected else None,
            'unit_cost': unit_cost,
        }
        rows.append(row)

        totals['expected_value'] += expected * unit_cost
        totals['usage_value'] += -sales * unit_cost
        if counted_base is not None:
            totals['counted_value'] += counted_base * unit_cost
        if variance_value is not None:
            totals['net_value'] += variance_value
            if variance_value > 0:
                totals['over_value'] += variance_value
            elif variance_value < 0:
                totals['under_value'] += variance_value

    rows.sort(key=lambda r: ((r['item'].category or 'zzz').lower(), r['item'].name.lower()))
    return {'rows': rows, 'totals': totals, 'previous': prev, 'start': start, 'end': end}

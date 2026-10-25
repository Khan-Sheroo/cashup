#!/usr/bin/env python
"""Store every spirit / liqueur as a 750 ml bottle so shot recipes are measured in ml.

Recipe quantities, stock movements, stock-take snapshots, invoice lines and remembered
supplier matches are rescaled to ml, so on-hand stock and recipe costs keep their meaning
(e.g. 0.0375 L -> 37.5 ml). The cost price stays the price of one bottle.

Bottles whose name states another size (e.g. "1L", "100CL", "700ml") keep that size, and
bitters keep their own bottle size. Run with --dry-run to preview without saving.
"""
import re
import shutil
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from cashup import create_app, db
from cashup.category_rules import guess_category
from cashup.models import (
    CostItem, InvoiceLine, RecipeLine, StockMovement, StockTakeLine, SupplierItemAlias,
)
from cashup.recipe_routes import _matching_category
from cashup.recipe_util import SPIRIT_BOTTLE_ML, SPIRIT_CATEGORIES, is_spirit_category

ML_PER_UNIT = {'ml': Decimal('1'), 'L': Decimal('1000')}
NAME_SIZE = re.compile(r'(\d+(?:\.\d+)?)\s*(ml|cl|l|lt|ltr)\b', re.IGNORECASE)
NAME_SIZE_ML = {'ml': Decimal('1'), 'cl': Decimal('10'), 'l': Decimal('1000'),
                'lt': Decimal('1000'), 'ltr': Decimal('1000')}
KEEP_OWN_SIZE = re.compile(r'\bbitters?\b|angostura', re.IGNORECASE)


def bottle_ml(item) -> Decimal:
    match = NAME_SIZE.search(item.name)
    if match:
        return Decimal(match.group(1)) * NAME_SIZE_ML[match.group(2).lower()]
    if KEEP_OWN_SIZE.search(item.name) and item.unit in ML_PER_UNIT:
        return Decimal(item.pack_size) * ML_PER_UNIT[item.unit]
    return SPIRIT_BOTTLE_ML


def spirit_items():
    items = []
    for item in CostItem.query.order_by(CostItem.name).all():
        if not item.category or item.category == 'From Sales Mix':
            guessed = _matching_category(guess_category(item.name))
            if is_spirit_category(guessed):
                item.category = guessed
        if is_spirit_category(item.category):
            items.append(item)
    return items


def scale(value, factor):
    return None if value is None else Decimal(value) * factor


def convert(item):
    size = bottle_ml(item)
    # ml in one old recipe unit; an 'each' was one bottle
    factor = ML_PER_UNIT.get(item.unit, size)
    before = f'{Decimal(item.pack_size).normalize():f} {item.unit}'

    for line in RecipeLine.query.filter_by(item_id=item.id):
        line.quantity = scale(line.quantity, factor)
    for move in StockMovement.query.filter_by(item_id=item.id):
        move.quantity = scale(move.quantity, factor)
        if move.unit_cost is not None:
            move.unit_cost = Decimal(move.unit_cost) / factor
    for line in StockTakeLine.query.filter_by(item_id=item.id):
        line.expected_base = scale(line.expected_base, factor)
        if line.unit_cost is not None:
            line.unit_cost = Decimal(line.unit_cost) / factor
    for line in InvoiceLine.query.filter_by(item_id=item.id):
        line.units_per_line = scale(line.units_per_line, factor)
    for alias in SupplierItemAlias.query.filter_by(item_id=item.id):
        alias.units_per_line = scale(alias.units_per_line, factor)

    item.unit = 'ml'
    item.pack_size = size
    item.count_unit = 'Bot'
    item.count_factor = size
    return before


def main():
    dry_run = '--dry-run' in sys.argv
    app = create_app()
    with app.app_context():
        if not dry_run:
            db_path = Path(db.engine.url.database)
            if not db_path.is_absolute():
                db_path = Path(app.instance_path) / db_path
            backup = db_path.parent / 'backups' / f'cashup-before-spirits-750ml-{datetime.now():%Y%m%d-%H%M%S}.db'
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(db_path, backup)
            print(f'Backup: {backup}')

        items = spirit_items()
        print(f'{len(items)} items in {", ".join(SPIRIT_CATEGORIES)}:')
        for item in items:
            before = convert(item)
            print(f'  {item.name:<40} {item.category:<9} {before:>9} -> '
                  f'{item.pack_size.normalize():f} ml  (R{Decimal(item.cost_price):.2f}/bottle)')

        if dry_run:
            db.session.rollback()
            print('Dry run: nothing saved.')
        else:
            db.session.commit()
            print('Saved.')


if __name__ == '__main__':
    main()

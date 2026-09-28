"""Helpers for recipe costing and gross margin."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


# Unit value → display label for item forms
COMMON_UNITS = (
    ('each', 'Each'),
    ('portion', 'Portion'),
    ('g', 'Gram (g)'),
    ('kg', 'Kilogram (kg)'),
    ('ml', 'Millilitre (ml)'),
    ('L', 'Litre (L)'),
    ('tsp', 'Teaspoon (tsp)'),
    ('tbsp', 'Tablespoon (tbsp)'),
    ('cup', 'Cup'),
    ('oz', 'Ounce (oz)'),
    ('lb', 'Pound (lb)'),
)

UNIT_VALUES = {value for value, _label in COMMON_UNITS}


def is_valid_unit(unit: str | None) -> bool:
    return (unit or '') in UNIT_VALUES


# Units an invoice quantity can be expressed in ('unit' = per item/pack as sold)
INVOICE_QTY_UNITS = (
    ('unit', 'Unit'),
    ('kg', 'kg'),
    ('g', 'g'),
    ('L', 'L'),
    ('ml', 'ml'),
)
INVOICE_QTY_UNIT_VALUES = {value for value, _label in INVOICE_QTY_UNITS}

# Amount of the dimension's base unit (g or ml) in one of each unit
UNIT_DIMENSIONS = {
    'g': ('mass', Decimal('1')),
    'kg': ('mass', Decimal('1000')),
    'oz': ('mass', Decimal('28.3495')),
    'lb': ('mass', Decimal('453.592')),
    'ml': ('volume', Decimal('1')),
    'L': ('volume', Decimal('1000')),
    'tsp': ('volume', Decimal('5')),
    'tbsp': ('volume', Decimal('15')),
    'cup': ('volume', Decimal('250')),
}


def unit_conversion(from_unit: str | None, to_unit: str | None) -> Decimal | None:
    """How many to_unit are in one from_unit, or None if not convertible (e.g. kg -> each)."""
    src = UNIT_DIMENSIONS.get(from_unit or '')
    dst = UNIT_DIMENSIONS.get(to_unit or '')
    if not src or not dst or src[0] != dst[0]:
        return None
    return src[1] / dst[1]


TWOPLACES = Decimal('0.01')


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == '':
        return default

    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return default



def money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal('0.00')
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def unit_cost(pack_cost: Decimal | None, pack_size: Decimal | None) -> Decimal:
    size = pack_size if pack_size is not None else Decimal('1')
    if size <= 0:
        size = Decimal('1')
    cost = pack_cost if pack_cost is not None else Decimal('0')
    return (cost / size).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def line_cost(quantity: Decimal | None, cost_per_unit: Decimal | None) -> Decimal:
    qty = quantity if quantity is not None else Decimal('0')
    per_unit = cost_per_unit if cost_per_unit is not None else Decimal('0')
    return money(qty * per_unit)


def recipe_total_cost(lines: list[dict]) -> Decimal:
    total = Decimal('0')
    for line in lines:
        if line.get('line_cost') is not None:
            total += money(line['line_cost'])
        else:
            total += line_cost(
                to_decimal(line.get('quantity'), Decimal('0')),
                to_decimal(line.get('cost_per_unit'), Decimal('0')),
            )
    return money(total)


# Sale price is treated as inclusive of VAT and service charge.
VAT_RATE = Decimal('0.15')
SERVICE_CHARGE_RATE = Decimal('0.10')
# Inclusive divisor: net × 1.15 × 1.10 = sale  ⇒  net = sale / 1.265
INCLUSIVE_TAX_DIVISOR = (Decimal('1') + VAT_RATE) * (Decimal('1') + SERVICE_CHARGE_RATE)


def net_sale_price(sale_price: Decimal | None) -> Decimal | None:
    """Strip 15% VAT and 10% service from an inclusive sale price."""
    sale = money(sale_price) if sale_price is not None else Decimal('0')
    if sale <= 0:
        return None
    return money(sale / INCLUSIVE_TAX_DIVISOR)


def gross_profit(sale_price: Decimal | None, cost: Decimal | None) -> Decimal | None:
    """Net sale (after VAT + service) − cost. None if no sale price."""
    net = net_sale_price(sale_price)
    if net is None:
        return None
    cost_amount = money(cost) if cost is not None else Decimal('0')
    return money(net - cost_amount)


def gross_margin_percent(sale_price: Decimal | None, cost: Decimal | None) -> Decimal | None:
    """Gross margin % on net sale after VAT + service. None if no sale price."""
    net = net_sale_price(sale_price)
    if net is None or net <= 0:
        return None
    cost_amount = money(cost) if cost is not None else Decimal('0')
    return money(((net - cost_amount) / net) * Decimal('100'))


"""App settings helpers: currency, tip-out basis, and tip-out rules."""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

CURRENCIES = {
    'USD': {'symbol': '$', 'name': 'US Dollars'},
    'EUR': {'symbol': '€', 'name': 'Euros'},
    'GBP': {'symbol': '£', 'name': 'Pounds'},
    'ZAR': {'symbol': 'R', 'name': 'Rands'},
    'SCR': {'symbol': 'SCR ', 'name': 'SCR'},
}

TIP_OUT_BASIS_CHOICES = (
    ('tips', 'Tip out from tips'),
    ('turnover', 'Tip out from turnover'),
)

DEFAULT_TIP_RULES = [
    {'key': 'cc_commission', 'label': 'CC Commission', 'percent': 5.0, 'enabled': True},
    {'key': 'pool', 'label': 'Pool Tips', 'percent': 15.0, 'enabled': True},
]

TIP_OUT_PRESETS = [
    {'key': 'runners', 'label': 'Runners', 'percent': 5.0},
    {'key': 'kitchen', 'label': 'Kitchen', 'percent': 5.0},
    {'key': 'bar', 'label': 'Bar', 'percent': 5.0},
]


def slugify_key(label: str, existing_keys: set[str] | None = None) -> str:
    """Build a stable tip-rule key from a label."""
    base = re.sub(r'[^a-z0-9]+', '_', (label or '').strip().lower()).strip('_') or 'tip_out'
    if existing_keys is None:
        return base
    key = base
    n = 2
    while key in existing_keys:
        key = f'{base}_{n}'
        n += 1
    return key


def normalize_tip_rules(raw_rules: Any) -> list[dict]:
    """Validate and normalize tip-rule dicts."""
    if not isinstance(raw_rules, list):
        return [dict(r) for r in DEFAULT_TIP_RULES]

    existing: set[str] = set()
    rules: list[dict] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        label = str(item.get('label') or '').strip()
        if not label:
            continue
        try:
            percent = float(item.get('percent', 0))
        except (TypeError, ValueError):
            percent = 0.0
        if percent < 0:
            percent = 0.0
        enabled = bool(item.get('enabled', True))
        key = str(item.get('key') or '').strip()
        if not key:
            key = slugify_key(label, existing)
        else:
            key = slugify_key(key, existing)
        existing.add(key)
        rules.append({
            'key': key,
            'label': label,
            'percent': round(percent, 2),
            'enabled': enabled,
        })
    return rules or [dict(r) for r in DEFAULT_TIP_RULES]


def parse_tip_rules_json(raw: str | None) -> list[dict]:
    if not raw:
        return [dict(r) for r in DEFAULT_TIP_RULES]
    try:
        return normalize_tip_rules(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return [dict(r) for r in DEFAULT_TIP_RULES]


def enabled_tip_rules(rules: list[dict]) -> list[dict]:
    return [r for r in rules if r.get('enabled')]


def currency_symbol(code: str) -> str:
    return CURRENCIES.get(code, CURRENCIES['ZAR'])['symbol']


def calculate_tip_breakdown(
    turnover: Decimal,
    cash_total: Decimal,
    credit_card: Decimal,
    tip_out_basis: str,
    tip_rules: list[dict],
    credit_sale: Decimal | None = None,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Return (tip_amount, tip_outs_by_key) using current settings.

    Credit sale is subtracted from turnover before tip / tip-out calc.
    """
    credit_sale = Decimal(credit_sale or 0)
    effective_turnover = turnover - credit_sale
    gross_tip = cash_total + credit_card - effective_turnover

    if tip_out_basis == 'turnover':
        basis = effective_turnover if effective_turnover > 0 else Decimal('0')
    else:
        basis = gross_tip if gross_tip > 0 else Decimal('0')

    tip_outs: dict[str, Decimal] = {}
    total_outs = Decimal('0')
    for rule in enabled_tip_rules(tip_rules):
        key = rule['key']
        if basis > 0:
            pct = Decimal(str(rule['percent'])) / Decimal('100')
            amount = (basis * pct).quantize(Decimal('0.01'))
        else:
            amount = Decimal('0')
        tip_outs[key] = amount
        total_outs += amount

    tip_amount = gross_tip - total_outs
    return tip_amount, tip_outs


def tip_outs_to_legacy(tip_outs: dict[str, Decimal]) -> tuple[Decimal, Decimal]:
    """Map dynamic tip-outs onto cc_commission + combined_tips columns."""
    cc = Decimal(str(tip_outs.get('cc_commission', 0)))
    combined = Decimal('0')
    for key, value in tip_outs.items():
        if key == 'cc_commission':
            continue
        combined += Decimal(str(value))
    return cc, combined


def tip_outs_as_float_dict(tip_outs: dict[str, Decimal]) -> dict[str, float]:
    return {k: float(v) for k, v in tip_outs.items()}


def sum_tip_outs_for_rows(rows, rules: list[dict]) -> dict[str, float]:
    """Sum tip-out amounts per rule key across cash-up rows."""
    totals = {r['key']: 0.0 for r in enabled_tip_rules(rules)}
    for row in rows:
        outs = row.get_tip_outs() if hasattr(row, 'get_tip_outs') else {}
        for key in totals:
            totals[key] += float(outs.get(key, 0) or 0)
    return totals

"""Parsers for POS sales mix PDFs, supplier PO/invoice PDFs, and stock take sheets."""
from __future__ import annotations

import csv
import difflib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

NUM = r'-?[\d,]+(?:\.\d+)?'


def normalize_name(value: str | None) -> str:
    """Lowercase alphanumeric key used for alias and fuzzy matching."""
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()


def to_dec(value, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(',', '')
    if not text:
        return default
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def suggest_match(name: str, candidates: dict[str, int], cutoff: float = 0.6) -> int | None:
    """Best id from {normalized_name: id} for a raw name, or None."""
    key = normalize_name(name)
    if not key or not candidates:
        return None
    if key in candidates:
        return candidates[key]
    close = difflib.get_close_matches(key, list(candidates), n=1, cutoff=cutoff)
    return candidates[close[0]] if close else None


def _pdf_lines(file_storage, x_tolerance: float = 1.5) -> list[str]:
    import pdfplumber

    data = file_storage.read() if hasattr(file_storage, 'read') else file_storage
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=x_tolerance) or ''
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def _parse_date(text: str) -> date | None:
    text = (text or '').strip()
    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# POS "Item Sales" report
# ---------------------------------------------------------------------------

SALES_ROW = re.compile(
    rf'^(?P<name>.+?)\s+(?P<qty>{NUM})\s+(?P<qty_pct>{NUM})\s+(?P<gross>{NUM})\s+'
    rf'(?P<gross_pct>{NUM})\s+(?P<discount>{NUM})\s+(?P<collected>{NUM})\s+'
    rf'(?P<vat>{NUM})\s+(?P<net>{NUM})$'
)
SALES_PERIOD = re.compile(
    r'Start date:\s*(?P<start>[\d./-]+).*?End date:\s*(?P<end>[\d./-]+)', re.IGNORECASE
)


def parse_item_sales_pdf(file_storage) -> dict:
    """Return {'start': date, 'end': date, 'rows': [{name, quantity, gross, discount, net}]}."""
    lines = _pdf_lines(file_storage, x_tolerance=3)
    start = end = None
    rows = []
    for line in lines:
        period = SALES_PERIOD.search(line)
        if period:
            start = start or _parse_date(period.group('start'))
            end = end or _parse_date(period.group('end'))
            continue
        match = SALES_ROW.match(line)
        if not match:
            continue
        name = match.group('name').strip()
        if not re.search(r'[A-Za-z]', name):
            continue  # totals line
        qty = to_dec(match.group('qty'), Decimal('0'))
        if qty == 0:
            continue
        rows.append({
            'name': name,
            'quantity': qty,
            'gross': to_dec(match.group('gross')),
            'discount': to_dec(match.group('discount')),
            'net': to_dec(match.group('net')),
        })
    return {'start': start, 'end': end, 'rows': rows}


def parse_sales_csv(file_storage) -> dict:
    """CSV fallback: needs an item/name column and a quantity column."""
    headers, records = read_csv(file_storage)
    name_col = _find_col(headers, ('item', 'name', 'description', 'product'))
    qty_col = _find_col(headers, ('quantity', 'qty', 'sold', 'count'))
    net_col = _find_col(headers, ('net',))
    gross_col = _find_col(headers, ('gross',))
    if name_col is None or qty_col is None:
        raise ValueError('CSV needs an Item/Name column and a Quantity column')
    rows = []
    for rec in records:
        name = (rec[name_col] if name_col < len(rec) else '').strip()
        qty = to_dec(rec[qty_col] if qty_col < len(rec) else None, Decimal('0'))
        if not name or not qty:
            continue
        rows.append({
            'name': name,
            'quantity': qty,
            'gross': to_dec(rec[gross_col]) if gross_col is not None and gross_col < len(rec) else None,
            'discount': None,
            'net': to_dec(rec[net_col]) if net_col is not None and net_col < len(rec) else None,
        })
    return {'start': None, 'end': None, 'rows': rows}


# ---------------------------------------------------------------------------
# Supplier purchase order / invoice
# ---------------------------------------------------------------------------

INVOICE_ROW = re.compile(
    rf'^(?P<desc>.+?)\s+(?P<qty>{NUM})\s+(?P<price>{NUM})\s+(?P<disc>{NUM})%\s+'
    rf'(?P<tax>Tax\s*Exempt|Zero\s*Rated|{NUM}%|No\s*Tax)\s+(?P<amount>{NUM})$',
    re.IGNORECASE,
)
SIMPLE_INVOICE_ROW = re.compile(
    rf'^(?P<desc>.*[A-Za-z].*?)\s+(?P<qty>{NUM})\s+(?P<price>{NUM})\s+(?P<amount>{NUM})$'
)
REFERENCE = re.compile(r'\b((?:PO|INV|IN|SI|TI)[-/ ]?\d[\w/-]*)\b', re.IGNORECASE)
DATE_TEXT = re.compile(r'\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4})\b')
TOTAL_LINE = re.compile(rf'^TOTAL\b[^\d]*?(?P<total>{NUM})\s*$', re.IGNORECASE)
HEADER_WORDS = ('purchase order', 'invoice', 'delivery date', 'tel', 'tin', 'vat', 'seychelles',
                'registered office', 'description', 'attention', 'address', 'telephone')


def parse_purchase_order_pdf(file_storage) -> dict:
    """Return {'supplier', 'reference', 'date', 'total', 'rows': [...]}."""
    lines = _pdf_lines(file_storage, x_tolerance=1.5)
    rows = []
    reference = None
    doc_date = None
    total = None
    supplier = None

    for idx, line in enumerate(lines):
        match = INVOICE_ROW.match(line)
        if match:
            rows.append({
                'description': match.group('desc').strip(),
                'quantity': to_dec(match.group('qty'), Decimal('0')),
                'unit_price': to_dec(match.group('price'), Decimal('0')),
                'tax': re.sub(r'\s+', ' ', match.group('tax')).strip(),
                'amount': to_dec(match.group('amount'), Decimal('0')),
            })
            continue
        if reference is None:
            ref = REFERENCE.search(line)
            if ref:
                reference = ref.group(1)
        if doc_date is None:
            found = DATE_TEXT.search(line)
            if found:
                doc_date = _parse_date(found.group(1))
        total_match = TOTAL_LINE.match(line)
        if total_match and 'tax' not in line.lower():
            total = to_dec(total_match.group('total'))
        if supplier is None and line.lower().startswith('delivery date') and idx + 1 < len(lines):
            candidate = lines[idx + 1]
            if not any(word in candidate.lower() for word in HEADER_WORDS):
                supplier = candidate

    if not rows:
        for line in lines:
            match = SIMPLE_INVOICE_ROW.match(line)
            if match and not line.lower().startswith(('subtotal', 'total')):
                rows.append({
                    'description': match.group('desc').strip(),
                    'quantity': to_dec(match.group('qty'), Decimal('0')),
                    'unit_price': to_dec(match.group('price'), Decimal('0')),
                    'tax': '',
                    'amount': to_dec(match.group('amount'), Decimal('0')),
                })

    return {'supplier': supplier, 'reference': reference, 'date': doc_date,
            'total': total, 'rows': rows}


def parse_invoice_csv(file_storage) -> dict:
    headers, records = read_csv(file_storage)
    desc_col = _find_col(headers, ('description', 'item', 'product', 'name'))
    qty_col = _find_col(headers, ('quantity', 'qty'))
    price_col = _find_col(headers, ('unit price', 'price', 'rate', 'cost'))
    amount_col = _find_col(headers, ('amount', 'total', 'line total'))
    if desc_col is None or qty_col is None:
        raise ValueError('CSV needs a Description column and a Quantity column')
    rows = []
    for rec in records:
        def cell(col):
            return rec[col] if col is not None and col < len(rec) else None
        desc = (cell(desc_col) or '').strip()
        qty = to_dec(cell(qty_col), Decimal('0'))
        if not desc or not qty:
            continue
        price = to_dec(cell(price_col), Decimal('0'))
        amount = to_dec(cell(amount_col), None)
        rows.append({
            'description': desc,
            'quantity': qty,
            'unit_price': price,
            'tax': '',
            'amount': amount if amount is not None else qty * price,
        })
    return {'supplier': None, 'reference': None, 'date': None, 'total': None, 'rows': rows}


# ---------------------------------------------------------------------------
# Stock take sheets (xlsx or csv)
# ---------------------------------------------------------------------------

def parse_stock_take_file(file_storage) -> list[dict]:
    """Return [{'item_id': int|None, 'description': str, 'count': Decimal}] for counted rows."""
    filename = (getattr(file_storage, 'filename', '') or '').lower()
    if filename.endswith(('.xlsx', '.xlsm')):
        table = _xlsx_rows(file_storage)
    else:
        headers, records = read_csv(file_storage)
        table = [headers] + records

    header_idx = None
    for idx, row in enumerate(table[:30]):
        cells = [normalize_name(str(c)) if c is not None else '' for c in row]
        if 'description' in cells and any(c in ('physical count', 'count', 'counted') for c in cells):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError('Could not find a header row with "Description" and "Physical Count"')

    header = [normalize_name(str(c)) if c is not None else '' for c in table[header_idx]]
    desc_col = header.index('description')
    count_col = next(i for i, c in enumerate(header) if c in ('physical count', 'count', 'counted'))
    id_col = header.index('item id') if 'item id' in header else None

    results = []
    for row in table[header_idx + 1:]:
        def cell(col):
            return row[col] if col is not None and col < len(row) else None
        desc = str(cell(desc_col) or '').strip()
        count = to_dec(cell(count_col))
        if not desc:
            continue
        if count is None:
            # Category headings and uncounted rows have no count
            continue
        item_id = None
        raw_id = cell(id_col)
        if raw_id not in (None, ''):
            try:
                item_id = int(float(raw_id))
            except (TypeError, ValueError):
                item_id = None
        results.append({'item_id': item_id, 'description': desc, 'count': count})
    return results


def _xlsx_rows(file_storage) -> list[list]:
    import openpyxl

    data = file_storage.read()
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def read_csv(file_storage) -> tuple[list[str], list[list[str]]]:
    raw = file_storage.read()
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        return [], []
    return [c.strip() for c in rows[0]], rows[1:]


def _find_col(headers: list[str], names: tuple[str, ...]) -> int | None:
    keys = [normalize_name(h) for h in headers]
    for name in names:
        if name in keys:
            return keys.index(name)
    for name in names:
        for idx, key in enumerate(keys):
            if name in key:
                return idx
    return None

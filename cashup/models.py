from cashup import db
from cashup.recipe_util import (
    gross_margin_percent,
    gross_profit,
    line_cost as calc_line_cost,
    net_sale_price,
    recipe_total_cost,
    unit_cost as calc_unit_cost,
)
from cashup.settings_util import (
    CURRENCIES,
    DEFAULT_TIP_RULES,
    currency_symbol,
    normalize_tip_rules,
    parse_tip_rules_json,
)
from datetime import datetime
from decimal import Decimal
import json


class Staff(db.Model):
    """Staff member model"""
    __tablename__ = 'staff'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    is_waiter = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    cashups = db.relationship('CashUp', backref='staff', lazy=True, cascade='all, delete-orphan')
    documents = db.relationship('StaffDocument', backref='staff', lazy=True, cascade='all, delete-orphan')
    folders = db.relationship('StaffFolder', backref='staff', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Staff {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'active': self.active,
            'is_waiter': self.is_waiter,
            'created_at': self.created_at.isoformat()
        }


class StaffFolder(db.Model):
    """Named folder for organizing a staff member's documents."""
    __tablename__ = 'staff_folder'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    documents = db.relationship('StaffDocument', backref='folder', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('staff_id', 'name', name='uq_staff_folder_name'),
    )

    def to_dict(self, document_count=None):
        data = {
            'id': self.id,
            'staff_id': self.staff_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if document_count is not None:
            data['document_count'] = document_count
        return data

    def __repr__(self):
        return f'<StaffFolder {self.id} staff={self.staff_id} {self.name}>'


class StaffDocument(db.Model):
    """Uploaded document or image belonging to a staff member."""
    __tablename__ = 'staff_document'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('staff_folder.id'), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    label = db.Column(db.String(200), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_image(self) -> bool:
        ct = (self.content_type or '').lower()
        if ct.startswith('image/'):
            return True
        name = (self.original_filename or '').lower()
        return name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))

    def is_pdf(self) -> bool:
        ct = (self.content_type or '').lower()
        if ct == 'application/pdf':
            return True
        name = (self.original_filename or '').lower()
        return name.endswith('.pdf')

    def can_preview(self) -> bool:
        return self.is_image() or self.is_pdf()

    def to_dict(self):
        return {
            'id': self.id,
            'staff_id': self.staff_id,
            'folder_id': self.folder_id,
            'folder_name': self.folder.name if self.folder else '',
            'original_filename': self.original_filename,
            'content_type': self.content_type,
            'label': self.label or '',
            'file_size': self.file_size,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'is_image': self.is_image(),
            'is_pdf': self.is_pdf(),
            'can_preview': self.can_preview(),
        }

    def __repr__(self):
        return f'<StaffDocument {self.id} staff={self.staff_id} {self.original_filename}>'


class CashUp(db.Model):
    """Cash-up record model"""
    __tablename__ = 'cashup'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    turnover = db.Column(db.Numeric(10, 2), nullable=False)
    cash_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    credit_card_total = db.Column(db.Numeric(10, 2), nullable=False)
    credit_sale = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tip_amount = db.Column(db.Numeric(10, 2), nullable=False)
    cc_commission = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    combined_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tip_outs_json = db.Column(db.Text, nullable=True)
    submitted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def get_tip_outs(self) -> dict:
        """Return tip-out amounts by rule key (legacy fallback supported)."""
        if self.tip_outs_json:
            try:
                data = json.loads(self.tip_outs_json)
                if isinstance(data, dict):
                    return {str(k): float(v or 0) for k, v in data.items()}
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return {
            'cc_commission': float(self.cc_commission or 0),
            'pool': float(self.combined_tips or 0),
        }

    def set_tip_outs(self, tip_outs: dict) -> None:
        """Persist tip-out breakdown and keep legacy columns in sync."""
        cleaned = {str(k): float(v or 0) for k, v in (tip_outs or {}).items()}
        self.tip_outs_json = json.dumps(cleaned)
        self.cc_commission = cleaned.get('cc_commission', 0)
        self.combined_tips = sum(v for k, v in cleaned.items() if k != 'cc_commission')


class DailySummary(db.Model):
    """Daily summary data for cashup totals"""
    __tablename__ = 'daily_summary'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    box_office_total_received = db.Column(db.Numeric(10, 2), nullable=True)
    runners_count = db.Column(db.Integer, nullable=True)
    barmen_count = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<DailySummary {self.date} - Box Office: {self.box_office_total_received}>'


class WaiterTip(db.Model):
    """Waiter tips per date"""
    __tablename__ = 'waiter_tip'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    tip_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    # Legacy column retained for existing databases; no longer used
    box_office_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    staff = db.relationship('Staff', backref='waiter_tips')
    
    # Unique constraint: one tip record per waiter per date
    __table_args__ = (db.UniqueConstraint('staff_id', 'date', name='uq_staff_date'),)
    
    def __repr__(self):
        return f'<WaiterTip {self.staff_id} - {self.date} - Tip: {self.tip_amount}>'


class CardMachineBatch(db.Model):
    """Card machine terminal batch totals"""
    __tablename__ = 'card_machine_batch'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    terminal_id = db.Column(db.String(20), nullable=False)
    batch_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Unique constraint: one batch per terminal per date
    __table_args__ = (db.UniqueConstraint('date', 'terminal_id', name='uq_date_terminal'),)
    
    def __repr__(self):
        return f'<CardMachineBatch {self.terminal_id} - {self.date} - Total: {self.batch_total}>'


class AppSettings(db.Model):
    """Singleton application settings (currency + tip-out rules)."""
    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(3), nullable=False, default='ZAR')
    tip_out_basis = db.Column(db.String(20), nullable=False, default='tips')
    tip_rules_json = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.tip_rules_json:
            self.tip_rules_json = json.dumps(DEFAULT_TIP_RULES)

    @property
    def tip_rules(self) -> list[dict]:
        return parse_tip_rules_json(self.tip_rules_json)

    @tip_rules.setter
    def tip_rules(self, value):
        self.tip_rules_json = json.dumps(normalize_tip_rules(value))

    @property
    def currency_symbol(self) -> str:
        return currency_symbol(self.currency)

    @property
    def currency_name(self) -> str:
        return CURRENCIES.get(self.currency, CURRENCIES['ZAR'])['name']

    def enabled_tip_rules(self) -> list[dict]:
        return [r for r in self.tip_rules if r.get('enabled')]

    def to_public_dict(self) -> dict:
        return {
            'currency': self.currency,
            'currency_symbol': self.currency_symbol,
            'tip_out_basis': self.tip_out_basis,
            'tip_rules': self.tip_rules,
            'enabled_tip_rules': self.enabled_tip_rules(),
        }

    @classmethod
    def get_or_create(cls):
        settings = cls.query.first()
        if settings is None:
            settings = cls(
                currency='ZAR',
                tip_out_basis='tips',
                tip_rules_json=json.dumps(DEFAULT_TIP_RULES),
            )
            db.session.add(settings)
            db.session.commit()
        elif not settings.tip_rules_json:
            settings.tip_rules_json = json.dumps(DEFAULT_TIP_RULES)
            db.session.commit()
        return settings


class CostItem(db.Model):
    """Purchased item / ingredient used in recipe costing.

    cost_price is the price paid for pack_size of unit
    (e.g. 750 ml bottle for R300 → recipes measure in ml).
    """
    __tablename__ = 'cost_item'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(40), nullable=False, default='each')
    pack_size = db.Column(db.Numeric(12, 4), nullable=False, default=1)
    cost_price = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    category = db.Column(db.String(80), nullable=True)
    # Stock is counted in count_unit (e.g. Bot, Glass); count_factor = recipe units per count unit
    count_unit = db.Column(db.String(20), nullable=True)
    count_factor = db.Column(db.Numeric(12, 4), nullable=True)
    par_level = db.Column(db.Numeric(12, 4), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    recipe_lines = db.relationship('RecipeLine', backref='item', lazy=True)

    def __repr__(self):
        return f'<CostItem {self.name}>'

    def cost_per_unit(self) -> Decimal:
        return calc_unit_cost(self.cost_price, self.pack_size)

    def effective_count_factor(self) -> Decimal:
        factor = self.count_factor if self.count_factor is not None else self.pack_size
        factor = Decimal(factor or 1)
        return factor if factor > 0 else Decimal('1')

    def count_unit_label(self) -> str:
        if self.count_unit:
            return self.count_unit
        size = Decimal(self.pack_size or 1).normalize()
        return f'{size:f} {self.unit}' if size != 1 else self.unit

    def to_count_units(self, base_qty) -> Decimal:
        return Decimal(base_qty or 0) / self.effective_count_factor()

    def to_base_units(self, count_qty) -> Decimal:
        return Decimal(count_qty or 0) * self.effective_count_factor()

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'unit': self.unit,
            'pack_size': float(self.pack_size or 1),
            'cost_price': float(self.cost_price or 0),
            'cost_per_unit': float(self.cost_per_unit()),
            'active': self.active,
        }


class Recipe(db.Model):
    """Recipe built from cost items; cost is derived from line quantities."""
    __tablename__ = 'recipe'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sale_price = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    lines = db.relationship(
        'RecipeLine',
        backref='recipe',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='RecipeLine.sort_order',
    )
    location = db.relationship('Location')

    def __repr__(self):
        return f'<Recipe {self.name}>'

    def total_cost(self) -> Decimal:
        line_data = [
            {
                'quantity': line.quantity,
                'cost_per_unit': line.item.cost_per_unit() if line.item else Decimal('0'),
            }
            for line in self.lines
        ]
        return recipe_total_cost(line_data)

    def net_sale(self) -> Decimal | None:
        """Sale after removing 15% VAT and 10% service charge."""
        return net_sale_price(self.sale_price)

    def gross_profit_amount(self) -> Decimal | None:
        return gross_profit(self.sale_price, self.total_cost())

    def margin_percent(self) -> Decimal | None:
        return gross_margin_percent(self.sale_price, self.total_cost())

    def to_dict(self):
        cost = self.total_cost()
        net = self.net_sale()
        margin = self.margin_percent()
        profit = self.gross_profit_amount()
        return {
            'id': self.id,
            'name': self.name,
            'sale_price': float(self.sale_price) if self.sale_price is not None else None,
            'net_sale': float(net) if net is not None else None,
            'cost_price': float(cost),
            'gross_profit': float(profit) if profit is not None else None,
            'margin_percent': float(margin) if margin is not None else None,
            'notes': self.notes or '',
            'lines': [line.to_dict() for line in self.lines],
        }


class RecipeLine(db.Model):
    """One measured ingredient on a recipe."""
    __tablename__ = 'recipe_line'

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def line_cost(self) -> Decimal:
        per_unit = self.item.cost_per_unit() if self.item else Decimal('0')
        return calc_line_cost(self.quantity, per_unit)

    def to_dict(self):
        return {
            'id': self.id,
            'recipe_id': self.recipe_id,
            'item_id': self.item_id,
            'item_name': self.item.name if self.item else '',
            'unit': self.item.unit if self.item else '',
            'cost_per_unit': float(self.item.cost_per_unit()) if self.item else 0,
            'quantity': float(self.quantity or 0),
            'line_cost': float(self.line_cost()),
            'sort_order': self.sort_order,
        }

    def __repr__(self):
        return f'<RecipeLine recipe={self.recipe_id} item={self.item_id}>'


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

DEFAULT_LOCATIONS = (
    ('Store Room', 'store'),
    ('Bar', 'outlet'),
    ('Kitchen', 'outlet'),
)

MOVEMENT_KINDS = {
    'opening': 'Opening',
    'purchase': 'Purchase',
    'transfer_in': 'Requisition In',
    'transfer_out': 'Requisition Out',
    'manual': 'Manual Adjustment',
    'waste': 'Waste',
    'sale': 'Sales Usage',
    'stocktake_adjust': 'Stock Take Adjustment',
}


class Location(db.Model):
    """Stock-holding location (store room, bar, kitchen)."""
    __tablename__ = 'location'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    kind = db.Column(db.String(20), nullable=False, default='outlet')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)

    @classmethod
    def ordered(cls):
        return cls.query.filter_by(active=True).order_by(cls.sort_order, cls.name).all()

    @classmethod
    def store(cls):
        return cls.query.filter_by(kind='store', active=True).order_by(cls.sort_order).first()

    def __repr__(self):
        return f'<Location {self.name}>'


class StockMovement(db.Model):
    """Signed stock change for one item at one location, in recipe units."""
    __tablename__ = 'stock_movement'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False, index=True)
    movement_date = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('requisition.id'), nullable=True)
    sales_import_id = db.Column(db.Integer, db.ForeignKey('sales_import.id'), nullable=True)
    stock_take_id = db.Column(db.Integer, db.ForeignKey('stock_take.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    item = db.relationship('CostItem', backref=db.backref('movements', lazy='dynamic'))
    location = db.relationship('Location')

    @property
    def kind_label(self) -> str:
        return MOVEMENT_KINDS.get(self.kind, self.kind)


class Supplier(db.Model):
    __tablename__ = 'supplier'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Invoice(db.Model):
    """Supplier invoice / purchase order received into a location."""
    __tablename__ = 'invoice'

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=True)
    reference = db.Column(db.String(80), nullable=True)
    invoice_date = db.Column(db.Date, nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    stored_filename = db.Column(db.String(255), nullable=True)
    stated_total = db.Column(db.Numeric(12, 2), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    supplier = db.relationship('Supplier')
    location = db.relationship('Location')
    lines = db.relationship(
        'InvoiceLine', backref='invoice', lazy=True,
        cascade='all, delete-orphan', order_by='InvoiceLine.sort_order',
    )

    def lines_total(self) -> Decimal:
        return sum((Decimal(l.amount or 0) for l in self.lines), Decimal('0'))


class InvoiceLine(db.Model):
    __tablename__ = 'invoice_line'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    qty_unit = db.Column(db.String(10), nullable=False, default='unit')
    unit_price = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    tax_label = db.Column(db.String(30), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=True)
    # Recipe units received per 1 invoice quantity (e.g. 1 bag = 1000 g)
    units_per_line = db.Column(db.Numeric(12, 4), nullable=True)
    skip = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    item = db.relationship('CostItem')

    def base_quantity(self) -> Decimal:
        return Decimal(self.quantity or 0) * Decimal(self.units_per_line or 0)


class SupplierItemAlias(db.Model):
    """Remembered mapping of a supplier's line description to an item."""
    __tablename__ = 'supplier_item_alias'

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    description_key = db.Column(db.String(255), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=False)
    units_per_line = db.Column(db.Numeric(12, 4), nullable=False, default=1)
    qty_unit = db.Column(db.String(10), nullable=False, default='unit')

    item = db.relationship('CostItem')

    __table_args__ = (
        db.UniqueConstraint('supplier_id', 'description_key', name='uq_supplier_alias'),
    )


class Requisition(db.Model):
    """Transfer of stock between locations (store room -> bar/kitchen)."""
    __tablename__ = 'requisition'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), nullable=True)
    req_date = db.Column(db.Date, nullable=False)
    from_location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    to_location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    from_location = db.relationship('Location', foreign_keys=[from_location_id])
    to_location = db.relationship('Location', foreign_keys=[to_location_id])
    lines = db.relationship(
        'RequisitionLine', backref='requisition', lazy=True,
        cascade='all, delete-orphan', order_by='RequisitionLine.id',
    )


class RequisitionLine(db.Model):
    __tablename__ = 'requisition_line'

    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('requisition.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 4), nullable=False, default=0)  # count units

    item = db.relationship('CostItem')


class SalesImport(db.Model):
    """Uploaded POS sales mix for a period."""
    __tablename__ = 'sales_import'

    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    default_location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    default_location = db.relationship('Location')
    lines = db.relationship(
        'SalesLine', backref='sales_import', lazy=True,
        cascade='all, delete-orphan', order_by='SalesLine.sort_order',
    )


class SalesLine(db.Model):
    __tablename__ = 'sales_line'

    id = db.Column(db.Integer, primary_key=True)
    sales_import_id = db.Column(db.Integer, db.ForeignKey('sales_import.id'), nullable=False)
    pos_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    gross = db.Column(db.Numeric(12, 2), nullable=True)
    discount = db.Column(db.Numeric(12, 2), nullable=True)
    net = db.Column(db.Numeric(12, 2), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)
    # Sold as-is: one pack of the item per sale
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=True)
    ignore = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    recipe = db.relationship('Recipe')
    item = db.relationship('CostItem')

    @property
    def is_mapped(self) -> bool:
        return bool(self.recipe_id or self.item_id or self.ignore)


class PosItemAlias(db.Model):
    """Remembered mapping of a POS item name to a recipe (or ignored)."""
    __tablename__ = 'pos_item_alias'

    id = db.Column(db.Integer, primary_key=True)
    pos_name_key = db.Column(db.String(255), nullable=False, unique=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=True)
    ignore = db.Column(db.Boolean, nullable=False, default=False)

    recipe = db.relationship('Recipe')


class StockTake(db.Model):
    """Physical count at one location on one date."""
    __tablename__ = 'stock_take'

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    count_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')
    note = db.Column(db.String(255), nullable=True)
    unmatched_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    location = db.relationship('Location')
    lines = db.relationship(
        'StockTakeLine', backref='stock_take', lazy=True,
        cascade='all, delete-orphan',
    )

    def unmatched_rows(self) -> list:
        if not self.unmatched_json:
            return []
        try:
            data = json.loads(self.unmatched_json)
            return data if isinstance(data, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []


class StockTakeLine(db.Model):
    __tablename__ = 'stock_take_line'

    id = db.Column(db.Integer, primary_key=True)
    stock_take_id = db.Column(db.Integer, db.ForeignKey('stock_take.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('cost_item.id'), nullable=False)
    counted = db.Column(db.Numeric(14, 4), nullable=False, default=0)  # count units
    expected_base = db.Column(db.Numeric(14, 4), nullable=True)  # snapshot at confirm
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)  # snapshot at confirm

    item = db.relationship('CostItem')

    __table_args__ = (
        db.UniqueConstraint('stock_take_id', 'item_id', name='uq_stock_take_item'),
    )

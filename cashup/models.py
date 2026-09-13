from cashup import db
from cashup.settings_util import (
    CURRENCIES,
    DEFAULT_TIP_RULES,
    currency_symbol,
    normalize_tip_rules,
    parse_tip_rules_json,
)
from datetime import datetime
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

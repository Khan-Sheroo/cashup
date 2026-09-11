from cashup import db
from datetime import datetime


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
    tip_amount = db.Column(db.Numeric(10, 2), nullable=False)
    cc_commission = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    combined_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    submitted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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


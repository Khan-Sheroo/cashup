from cashup import db
from datetime import datetime


class Staff(db.Model):
    """Staff member model"""
    __tablename__ = 'staff'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
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
            'created_at': self.created_at.isoformat()
        }


class CashUp(db.Model):
    """Cash-up record model"""
    __tablename__ = 'cashup'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    turnover = db.Column(db.Numeric(10, 2), nullable=False)
    credit_card_total = db.Column(db.Numeric(10, 2), nullable=False)
    breakages = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tip_amount = db.Column(db.Numeric(10, 2), nullable=False)
    box_office_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    actual_box_office = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    runners_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    bar_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    kitchen_tips = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<CashUp {self.id} - Staff {self.staff_id} - {self.date}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'staff_id': self.staff_id,
            'staff_name': self.staff.name if self.staff else None,
            'date': self.date.isoformat(),
            'turnover': float(self.turnover),
            'credit_card_total': float(self.credit_card_total),
            'breakages': float(self.breakages),
            'tip_amount': float(self.tip_amount),
            'box_office_tips': float(self.box_office_tips),
            'actual_box_office': float(self.actual_box_office),
            'runners_tips': float(self.runners_tips),
            'bar_tips': float(self.bar_tips),
            'kitchen_tips': float(self.kitchen_tips),
            'created_at': self.created_at.isoformat()
        }


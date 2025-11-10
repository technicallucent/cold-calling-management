from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import enum

db = SQLAlchemy()

class UserRole(enum.Enum):
    ADMIN = 'admin'
    AGENT = 'agent'

class InterestLevel(enum.Enum):
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    NOT_INTERESTED = 'not_interested'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    assigned_leads = db.relationship('Lead', backref='assigned_agent', lazy=True, foreign_keys='Lead.assigned_agent_id')
    feedbacks = db.relationship('LeadFeedback', backref='agent', lazy=True)

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    mobile = db.Column(db.String(15), nullable=False)
    pincode = db.Column(db.String(10), nullable=True)
    project_name = db.Column(db.String(200), nullable=False, default='N/A')
    source = db.Column(db.String(100), nullable=True, default='N/A')
    year = db.Column(db.Integer, nullable=True)
    location = db.Column(db.String(100), nullable=True, default='N/A')
    
    # Assignment fields
    assigned_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='new')  # new, in_progress, completed, reassigned
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class LeadFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Feedback fields - updated to Text/String
    project_interested = db.Column(db.String(200), nullable=True)        # name of the project
    location_preferred = db.Column(db.String(200), nullable=True)        # preferred location
    configuration_interested = db.Column(db.String(200), nullable=True)  # desired configuration
    budget_comfortable = db.Column(db.String(100), nullable=True)        # budget info / comfortable range
    possession_timeline = db.Column(db.String(200), nullable=True)
    interest_level = db.Column(db.Enum(InterestLevel), nullable=True)
    additional_notes = db.Column(db.Text, nullable=True)
    recording_path = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    call_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    lead = db.relationship('Lead', backref=db.backref('feedbacks', lazy=True))


class LeadReassignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    from_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    reassigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    lead = db.relationship('Lead', backref='reassignments')
    from_agent = db.relationship('User', foreign_keys=[from_agent_id], backref='reassigned_from')
    to_agent = db.relationship('User', foreign_keys=[to_agent_id], backref='reassigned_to')
class LeadAssignmentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Who assigned this lead (admin/agent)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.Text, nullable=True)  # Optional notes like "bulk assign" or "reassignment"

    # Relationships
    lead = db.relationship('Lead', backref='assignment_history')
    agent = db.relationship('User', foreign_keys=[agent_id], backref='lead_assignments')
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id], backref='assigned_leads_history')    
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

class CallStatus(enum.Enum):
    INITIATED = 'initiated'
    COMPLETED = 'completed'
    BUSY = 'busy'
    NOT_ANSWERED = 'not_answered'
    WRONG_NUMBER = 'wrong_number'
    CALLBACK_SCHEDULED = 'callback_scheduled'
    ENDED_MANUAL = 'ended_manual'

class FeedbackType(enum.Enum):
    INTERESTED = 'interested'
    NOT_INTERESTED = 'not_interested'
    CALLBACK = 'callback'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Additional agent fields
    phone_number = db.Column(db.String(20), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    
    # Relationships
    assigned_leads = db.relationship('Lead', backref='assigned_agent', lazy=True, foreign_keys='Lead.assigned_agent_id')
    feedbacks = db.relationship('LeadFeedback', backref='agent', lazy=True)
    call_logs = db.relationship('CallLog', backref='agent', lazy=True)
    reassignments_from = db.relationship('LeadReassignment', foreign_keys='LeadReassignment.from_agent_id', backref='from_agent', lazy=True)
    reassignments_to = db.relationship('LeadReassignment', foreign_keys='LeadReassignment.to_agent_id', backref='to_agent', lazy=True)

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
    status = db.Column(db.String(50), default='new')  # new, assigned, interested, not_interested, callback, completed, reassigned
    
    # Additional lead fields
    alternate_phone = db.Column(db.String(15), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True, default='India')
    
    # Lead priority and categorization
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    category = db.Column(db.String(100), nullable=True)  # residential, commercial, plot, etc.
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    call_logs = db.relationship('CallLog', backref='lead', lazy=True, cascade='all, delete-orphan')
    feedbacks = db.relationship('LeadFeedback', backref='lead', lazy=True, cascade='all, delete-orphan')
    reassignments = db.relationship('LeadReassignment', backref='lead', lazy=True, cascade='all, delete-orphan')
    assignment_history = db.relationship('LeadAssignmentHistory', backref='lead', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Lead {self.id}: {self.name} - {self.mobile}>'

class LeadFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Feedback type
    feedback_type = db.Column(db.Enum(FeedbackType), nullable=True)
    call_activity_id = db.Column(db.String(100), nullable=True)
    # Feedback fields for interested customers
    project_interested = db.Column(db.String(200), nullable=True)
    location_preferred = db.Column(db.String(200), nullable=True)
    configuration_interested = db.Column(db.String(200), nullable=True)
    budget_comfortable = db.Column(db.String(100), nullable=True)
    possession_timeline = db.Column(db.String(200), nullable=True)
    interest_level = db.Column(db.Enum(InterestLevel), nullable=True)
    
    # Fields for not interested customers
    not_interested_reason = db.Column(db.String(200), nullable=True)
    
    # Fields for callback
    callback_time = db.Column(db.DateTime, nullable=True)
    callback_notes = db.Column(db.Text, nullable=True)
    callback_priority = db.Column(db.String(20), default='medium')  # high, medium, low
    
    # Common fields
    additional_notes = db.Column(db.Text, nullable=True)
    recording_path = db.Column(db.String(500), nullable=True)
    
    # Call information
    call_duration = db.Column(db.Integer, nullable=True)  # Duration in seconds
    call_quality = db.Column(db.String(50), nullable=True)  # good, average, poor
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert feedback to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'agent_id': self.agent_id,
            'feedback_type': self.feedback_type.value if self.feedback_type else None,
            'project_interested': self.project_interested,
            'location_preferred': self.location_preferred,
            'configuration_interested': self.configuration_interested,
            'budget_comfortable': self.budget_comfortable,
            'possession_timeline': self.possession_timeline,
            'interest_level': self.interest_level.value if self.interest_level else None,
            'not_interested_reason': self.not_interested_reason,
            'callback_time': self.callback_time.isoformat() if self.callback_time else None,
            'callback_notes': self.callback_notes,
            'callback_priority': self.callback_priority,
            'additional_notes': self.additional_notes,
            'call_duration': self.call_duration,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    call_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum(CallStatus), nullable=False, default=CallStatus.INITIATED)
    duration_seconds = db.Column(db.Integer, nullable=True)  # Call duration in seconds
    
    # Additional call details
    call_notes = db.Column(db.Text, nullable=True)
    follow_up_required = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.DateTime, nullable=True)
    
    # Call outcome details
    outcome = db.Column(db.String(100), nullable=True)  # interested, not_interested, callback, etc.
    satisfaction_score = db.Column(db.Integer, nullable=True)  # 1-5 scale
    
    # Technical details
    call_recording_path = db.Column(db.String(500), nullable=True)
    call_quality = db.Column(db.String(50), nullable=True)  # clear, poor, dropped, etc.
    
    def to_dict(self):
        """Convert call log to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'agent_id': self.agent_id,
            'call_time': self.call_time.isoformat() if self.call_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'status': self.status.value if self.status else None,
            'duration_seconds': self.duration_seconds,
            'call_notes': self.call_notes,
            'outcome': self.outcome,
            'satisfaction_score': self.satisfaction_score,
            'follow_up_required': self.follow_up_required,
            'follow_up_date': self.follow_up_date.isoformat() if self.follow_up_date else None
        }

class LeadReassignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    from_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    reassigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Additional reassignment details
    status = db.Column(db.String(50), default='pending')  # pending, accepted, rejected
    admin_notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert reassignment to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'from_agent_id': self.from_agent_id,
            'to_agent_id': self.to_agent_id,
            'reason': self.reason,
            'reassigned_at': self.reassigned_at.isoformat() if self.reassigned_at else None,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class LeadAssignmentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.Text, nullable=True)
    
    # Additional assignment details
    assignment_type = db.Column(db.String(50), default='manual')  # manual, auto, reassignment
    previous_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    agent = db.relationship('User', foreign_keys=[agent_id], backref='lead_assignments')
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id], backref='assigned_leads_history')
    previous_agent = db.relationship('User', foreign_keys=[previous_agent_id], backref='previous_assignments')

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationship
    updated_by_user = db.relationship('User', backref='system_settings')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # info, success, warning, error
    is_read = db.Column(db.Boolean, default=False)
    related_entity_type = db.Column(db.String(50), nullable=True)  # lead, call, feedback, etc.
    related_entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref='notifications')
    
class CallActivityLog(db.Model):
    __tablename__ = 'call_activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=True)
    call_log_id = db.Column(db.String(100), nullable=True)  
    message = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), default='info')  # info, success, warning, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    agent = db.relationship('User', backref=db.backref('call_activity_logs', lazy=True))
    lead = db.relationship('Lead', backref=db.backref('call_activity_logs', lazy=True))


    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'lead_id': self.lead_id,
            'call_log_id': self.call_log_id,
            'message': self.message,
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

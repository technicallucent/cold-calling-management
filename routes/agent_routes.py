from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, UserRole, Lead, LeadFeedback, LeadReassignment, InterestLevel
import os
from datetime import datetime

agent_bp = Blueprint('agent', __name__)

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@agent_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    assigned_leads = Lead.query.filter_by(assigned_agent_id=current_user.id).count()
    completed_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='completed').count()
    pending_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='assigned').count()
    
    return render_template('agent/dashboard.html',
                         assigned_leads=assigned_leads,
                         completed_leads=completed_leads,
                         pending_leads=pending_leads)

@agent_bp.route('/my_leads')
@login_required
def my_leads():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    leads = Lead.query.filter_by(assigned_agent_id=current_user.id).all()
    other_agents = User.query.filter(
        User.role == UserRole.AGENT,
        User.id != current_user.id,
        User.is_active == True
    ).all()
    
    return render_template('agent/my_leads.html', leads=leads, other_agents=other_agents)

@agent_bp.route('/add_feedback/<int:lead_id>', methods=['POST'])
@login_required
def add_feedback(lead_id):
    if current_user.role != UserRole.AGENT:
        return jsonify({'error': 'Access denied'}), 403
    
    lead = Lead.query.get(lead_id)
    if not lead or lead.assigned_agent_id != current_user.id:
        flash('Lead not found or not assigned to you', 'error')
        return redirect(url_for('agent.my_leads'))
    
    # Handle file upload
    recording_path = None
    if 'recording' in request.files:
        recording = request.files['recording']
        if recording and recording.filename != '':
            if allowed_file(recording.filename, {'wav', 'mp3'}):
                filename = secure_filename(f"{lead_id}_{datetime.now().timestamp()}.{recording.filename.rsplit('.', 1)[1].lower()}")
                recording_path = os.path.join('uploads/recordings', filename)
                recording.save(recording_path)
    
    # Get form data as text/string
    project_interested = request.form.get('project_interested') or None
    location_preferred = request.form.get('location_preferred') or None
    configuration_interested = request.form.get('configuration_interested') or None
    budget_comfortable = request.form.get('budget_comfortable') or None
    
    interest_level = request.form.get('interest_level')
    if interest_level:
        interest_level = InterestLevel(interest_level)
    
    feedback = LeadFeedback(
        lead_id=lead_id,
        agent_id=current_user.id,
        project_interested=project_interested,
        location_preferred=location_preferred,
        configuration_interested=configuration_interested,
        budget_comfortable=budget_comfortable,
        possession_timeline=request.form.get('possession_timeline'),
        interest_level=interest_level,
        additional_notes=request.form.get('additional_notes'),
        recording_path=recording_path
    )
    
    # Update lead status
    lead.status = 'completed'
    lead.updated_at = datetime.utcnow()
    
    db.session.add(feedback)
    db.session.commit()
    
    flash('Feedback added successfully!', 'success')
    return redirect(url_for('agent.my_leads'))

@agent_bp.route('/reassign_lead', methods=['POST'])
@login_required
def reassign_lead():
    if current_user.role != UserRole.AGENT:
        return jsonify({'error': 'Access denied'}), 403
    
    lead_id = request.form.get('lead_id')
    to_agent_id = request.form.get('to_agent_id')
    reason = request.form.get('reason')
    
    lead = Lead.query.get(lead_id)
    to_agent = User.query.get(to_agent_id)
    
    if lead and to_agent and lead.assigned_agent_id == current_user.id:
        # Create reassignment record
        reassignment = LeadReassignment(
            lead_id=lead_id,
            from_agent_id=current_user.id,
            to_agent_id=to_agent_id,
            reason=reason
        )
        
        # Update lead assignment
        lead.assigned_agent_id = to_agent_id
        lead.status = 'reassigned'
        lead.assigned_date = datetime.utcnow()
        
        db.session.add(reassignment)
        db.session.commit()
        
        flash('Lead reassigned successfully!', 'success')
    else:
        flash('Invalid reassignment request', 'error')
    
    return redirect(url_for('agent.my_leads'))

@agent_bp.route('/feedback_history/<int:lead_id>')
@login_required
def feedback_history(lead_id):
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    lead = Lead.query.get(lead_id)
    if not lead or lead.assigned_agent_id != current_user.id:
        flash('Lead not found or not assigned to you', 'error')
        return redirect(url_for('agent.my_leads'))
    
    feedbacks = LeadFeedback.query.filter_by(lead_id=lead_id).order_by(LeadFeedback.created_at.desc()).all()
    return render_template('agent/feedback_history.html', lead=lead, feedbacks=feedbacks)

@agent_bp.route('/all_feedback')
@login_required
def all_feedback():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Get all feedbacks for leads assigned to current agent
    feedbacks = LeadFeedback.query\
        .join(Lead)\
        .filter(Lead.assigned_agent_id == current_user.id)\
        .order_by(LeadFeedback.created_at.desc())\
        .all()
    
    return render_template('agent/all_feedback.html', feedbacks=feedbacks)

# Add a default route for feedback history without lead_id
@agent_bp.route('/feedback_history')
@login_required
def feedback_history_default():
    return redirect(url_for('agent.all_feedback'))
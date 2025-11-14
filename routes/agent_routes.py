from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, UserRole, Lead, LeadFeedback, LeadReassignment, InterestLevel, CallLog, CallStatus, FeedbackType,CallActivityLog
import os
from datetime import datetime, timedelta
import json

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
    interested_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='interested').count()
    
    # Get today's call statistics
    today = datetime.utcnow().date()
    today_calls = CallLog.query.filter(
        CallLog.agent_id == current_user.id,
        db.func.date(CallLog.call_time) == today
    ).count()
    
    # Get recent call logs
    recent_calls = CallLog.query.filter_by(agent_id=current_user.id)\
        .order_by(CallLog.call_time.desc())\
        .limit(5)\
        .all()
    
    return render_template('agent/dashboard.html',
                         assigned_leads=assigned_leads,
                         completed_leads=completed_leads,
                         pending_leads=pending_leads,
                         interested_leads=interested_leads,
                         today_calls=today_calls,
                         recent_calls=recent_calls)

@agent_bp.route('/call_center')
@login_required
def call_center():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Get leads assigned to current agent with status 'assigned' or 'callback'
    leads = Lead.query.filter_by(
        assigned_agent_id=current_user.id
    ).filter(
        Lead.status.in_(['assigned', 'callback'])
    ).order_by(
        db.case(
            (Lead.status == 'callback', 1),
            (Lead.status == 'assigned', 2),
            else_=3
        ),
        Lead.assigned_date.desc()
    ).all()
    
    if not leads:
        flash('No leads available for calling', 'info')
        return redirect(url_for('agent.my_leads'))
    
    # Get first lead to display
    current_lead = leads[0]
    lead_index = 0
    total_leads = len(leads)
    
    # Get stats for dashboard
    assigned_leads = Lead.query.filter_by(assigned_agent_id=current_user.id).count()
    completed_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='completed').count()
    pending_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='assigned').count()
    today = datetime.utcnow().date()
    today_calls = CallLog.query.filter(
        CallLog.agent_id == current_user.id,
        db.func.date(CallLog.call_time) == today
    ).count()
    
    # Get other agents for reassignment
    other_agents = User.query.filter(
        User.role == UserRole.AGENT,
        User.id != current_user.id,
        User.is_active == True
    ).all()
    
    return render_template('agent/call_center.html',
                         leads=leads,
                         current_lead=current_lead,
                         lead_index=lead_index,
                         total_leads=total_leads,
                         assigned_leads=assigned_leads,
                         completed_leads=completed_leads,
                         pending_leads=pending_leads,
                         today_calls=today_calls,
                         other_agents=other_agents)

@agent_bp.route('/call_lead/<int:lead_id>')
@login_required
def call_lead(lead_id):
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    lead = Lead.query.get_or_404(lead_id)
    if lead.assigned_agent_id != current_user.id:
        flash('Lead not assigned to you', 'error')
        return redirect(url_for('agent.call_center'))
    
    # Get all leads for navigation
    leads = Lead.query.filter_by(
        assigned_agent_id=current_user.id
    ).filter(
        Lead.status.in_(['assigned', 'callback'])
    ).order_by(
        db.case(
            (Lead.status == 'callback', 1),
            (Lead.status == 'assigned', 2),
            else_=3
        ),
        Lead.assigned_date.desc()
    ).all()
    
    current_index = next((i for i, l in enumerate(leads) if l.id == lead_id), 0)
    
    # Create call log entry
    call_log = CallLog(
        lead_id=lead_id,
        agent_id=current_user.id,
        call_time=datetime.utcnow(),
        status=CallStatus.INITIATED
    )
    db.session.add(call_log)
    db.session.commit()
    
    # Get stats
    assigned_leads = Lead.query.filter_by(assigned_agent_id=current_user.id).count()
    completed_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='completed').count()
    pending_leads = Lead.query.filter_by(assigned_agent_id=current_user.id, status='assigned').count()
    today = datetime.utcnow().date()
    today_calls = CallLog.query.filter(
        CallLog.agent_id == current_user.id,
        db.func.date(CallLog.call_time) == today
    ).count()
    
    # Get other agents for reassignment
    other_agents = User.query.filter(
        User.role == UserRole.AGENT,
        User.id != current_user.id,
        User.is_active == True
    ).all()
    
    return render_template('agent/call_center.html',
                         leads=leads,
                         current_lead=lead,
                         lead_index=current_index,
                         total_leads=len(leads),
                         call_log_id=call_log.id,
                         assigned_leads=assigned_leads,
                         completed_leads=completed_leads,
                         pending_leads=pending_leads,
                         today_calls=today_calls,
                         other_agents=other_agents)

@agent_bp.route('/update_call_status', methods=['POST'])
@login_required
def update_call_status():
    if current_user.role != UserRole.AGENT:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    data = request.get_json()
    call_log_id = data.get('call_log_id')
    
    if not call_log_id:
        return jsonify({'success': False, 'error': 'Call log ID required'}), 400
    
    call_log = CallLog.query.get(call_log_id)
    if not call_log or call_log.agent_id != current_user.id:
        return jsonify({'success': False, 'error': 'Invalid call log'}), 400
    
    status = data.get('status')
    duration_seconds = data.get('duration_seconds')
    
    # Map frontend status to CallStatus enum
    status_mapping = {
        'ended_manual': CallStatus.ENDED_MANUAL,
        'completed': CallStatus.COMPLETED,
        'busy': CallStatus.BUSY,
        'not_answered': CallStatus.NOT_ANSWERED,
        'wrong_number': CallStatus.WRONG_NUMBER
    }
    
    if status in status_mapping:
        call_log.status = status_mapping[status]
    
    call_log.end_time = datetime.utcnow()
    if duration_seconds:
        call_log.duration_seconds = duration_seconds
    
    db.session.commit()
    
    return jsonify({'success': True})

@agent_bp.route('/handle_call_action/<int:lead_id>', methods=['POST'])
@login_required
def handle_call_action(lead_id):
    if current_user.role != UserRole.AGENT:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    lead = Lead.query.get_or_404(lead_id)
    if lead.assigned_agent_id != current_user.id:
        return jsonify({'success': False, 'error': 'Lead not assigned to you'}), 400
    
    data = request.get_json()
    action = data.get('action')
    call_log_id = data.get('call_log_id')
    duration_seconds = data.get('duration_seconds')
    
    # Update call log
    if call_log_id:
        call_log = CallLog.query.get(call_log_id)
        if call_log:
            # Map action to CallStatus
            action_mapping = {
                'interested': CallStatus.COMPLETED,
                'not_interested': CallStatus.COMPLETED,
                'busy': CallStatus.BUSY,
                'not_answered': CallStatus.NOT_ANSWERED,
                'wrong_number': CallStatus.WRONG_NUMBER,
                'callback': CallStatus.CALLBACK_SCHEDULED
            }
            
            if action in action_mapping:
                call_log.status = action_mapping[action]
            
            call_log.end_time = datetime.utcnow()
            if duration_seconds:
                call_log.duration_seconds = duration_seconds
    
    response_data = {'success': True}
    
    # Map actions to lead status and form types
    action_mapping = {
        'interested': ('interested', 'interested'),
        'not_interested': ('not_interested', 'not_interested'),
        'busy': ('callback', 'callback'),
        'not_answered': ('callback', 'callback'),
        'wrong_number': ('not_interested', 'not_interested'),
        'callback': ('callback', 'callback')
    }
    
    if action in action_mapping:
        lead_status, form_type = action_mapping[action]
        lead.status = lead_status
        lead.updated_at = datetime.utcnow()
        
        # Only show form for specific actions
        if action in ['interested', 'not_interested', 'callback']:
            response_data['show_form'] = True
            response_data['form_type'] = form_type
        else:
            response_data['show_form'] = False
        
        # For wrong number, pre-fill the reason
        if action == 'wrong_number':
            response_data['preset_reason'] = 'Wrong Number'
    
    db.session.commit()
    
    return jsonify(response_data)

@agent_bp.route('/submit_feedback/<int:lead_id>', methods=['POST'])
@login_required
def submit_feedback(lead_id):
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    lead = Lead.query.get_or_404(lead_id)
    if lead.assigned_agent_id != current_user.id:
        flash('Lead not assigned to you', 'error')
        return redirect(url_for('agent.call_center'))
    
    # Handle file upload
    recording_path = None
    if 'recording' in request.files:
        recording = request.files['recording']
        if recording and recording.filename != '':
            if allowed_file(recording.filename, {'wav', 'mp3', 'm4a'}):
                filename = secure_filename(f"{lead_id}_{int(datetime.now().timestamp())}.{recording.filename.rsplit('.', 1)[1].lower()}")
                upload_dir = 'uploads/recordings'
                os.makedirs(upload_dir, exist_ok=True)
                recording_path = os.path.join(upload_dir, filename)
                recording.save(recording_path)
    
    # Get form data
    feedback_type = request.form.get('feedback_type')
    currentCallActivityId = request.form.get('call_log_id')
    # Create feedback based on type
    feedback = LeadFeedback(
        lead_id=lead_id,
        agent_id=current_user.id,
        feedback_type=FeedbackType(feedback_type) if feedback_type else None,
        additional_notes=request.form.get('additional_notes'),
        recording_path=recording_path,
        call_activity_id=currentCallActivityId,
        created_at=datetime.utcnow(),
    )
    
    # Set fields based on feedback type
    if feedback_type == 'interested':
        feedback.project_interested = request.form.get('project_interested')
        feedback.location_preferred = request.form.get('location_preferred')
        feedback.configuration_interested = request.form.get('configuration_interested')
        feedback.budget_comfortable = request.form.get('budget_comfortable')
        interest_level = request.form.get('interest_level')
        if interest_level:
            feedback.interest_level = InterestLevel(interest_level)
        feedback.possession_timeline = request.form.get('possession_timeline')
        lead.status = 'completed'
        
    elif feedback_type == 'not_interested':
        feedback.not_interested_reason = request.form.get('not_interested_reason')
        lead.status = 'not_interested'
        
    elif feedback_type == 'callback':
        callback_time_str = request.form.get('callback_time')
        if callback_time_str:
            try:
                # Handle timezone information
                if 'Z' in callback_time_str:
                    callback_time_str = callback_time_str.replace('Z', '+00:00')
                feedback.callback_time = datetime.fromisoformat(callback_time_str)
            except ValueError:
                flash('Invalid callback time format', 'error')
                return redirect(url_for('agent.call_center'))
        
        feedback.callback_notes = request.form.get('callback_notes')
        feedback.callback_priority = request.form.get('callback_priority', 'medium')
        lead.status = 'callback'
    
    lead.updated_at = datetime.utcnow()
    db.session.add(feedback)
    db.session.commit()
    
    flash('Feedback submitted successfully!', 'success')
    return redirect(url_for('agent.call_center'))

@agent_bp.route('/call_logs')
@login_required
def call_logs():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    call_logs = CallLog.query.filter_by(agent_id=current_user.id)\
        .order_by(CallLog.call_time.desc())\
        .all()
    
    return render_template('agent/call_logs.html', call_logs=call_logs)

@agent_bp.route('/get_lead_details/<int:lead_id>')
@login_required
def get_lead_details(lead_id):
    if current_user.role != UserRole.AGENT:
        return jsonify({'error': 'Access denied'}), 403
    
    lead = Lead.query.get_or_404(lead_id)
    if lead.assigned_agent_id != current_user.id:
        return jsonify({'error': 'Lead not assigned to you'}), 403
    
    lead_data = {
        'id': lead.id,
        'name': lead.name,
        'mobile': lead.mobile,
        'email': lead.email,
        'project_name': lead.project_name,
        'location': lead.location,
        'status': lead.status,
        'assigned_date': lead.assigned_date.isoformat() if lead.assigned_date else None
    }
    
    return jsonify(lead_data)

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

@agent_bp.route('/reassign_lead', methods=['POST'])
@login_required
def reassign_lead():
    if current_user.role != UserRole.AGENT:
        flash('Access denied!', 'error')
        return redirect(url_for('admin.dashboard'))
    
    lead_id = request.form.get('lead_id')
    to_agent_id = request.form.get('to_agent_id')
    reason = request.form.get('reason')
    
    lead = Lead.query.get(lead_id)
    to_agent = User.query.get(to_agent_id)
    
    if not lead or not to_agent:
        flash('Invalid lead or agent', 'error')
        return redirect(url_for('agent.my_leads'))
    
    if lead.assigned_agent_id != current_user.id:
        flash('Lead not assigned to you', 'error')
        return redirect(url_for('agent.my_leads'))
    
    # Create reassignment record
    reassignment = LeadReassignment(
        lead_id=lead_id,
        from_agent_id=current_user.id,
        to_agent_id=to_agent_id,
        reason=reason,
        reassigned_at=datetime.utcnow()
    )
    
    # Update lead assignment
    lead.assigned_agent_id = to_agent_id
    lead.status = 'reassigned'
    lead.assigned_date = datetime.utcnow()
    lead.updated_at = datetime.utcnow()
    
    db.session.add(reassignment)
    db.session.commit()
    
    flash('Lead reassigned successfully!', 'success')
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

    feedbacks = LeadFeedback.query.filter_by(lead_id=lead_id).all()
    call_logs = CallActivityLog.query.filter_by(lead_id=lead_id).order_by(CallActivityLog.created_at.desc()).all()

    # Group by call_log_id (include all call sessions even if no feedback)
    grouped = {}

    for log in call_logs:
        grouped.setdefault(log.call_log_id, {
            'call_log_id': log.call_log_id,
            'call_logs': [],
            'feedbacks': [],
            'latest_time': log.created_at
        })
        grouped[log.call_log_id]['call_logs'].append(log)
        if log.created_at > grouped[log.call_log_id]['latest_time']:
            grouped[log.call_log_id]['latest_time'] = log.created_at

    for fb in feedbacks:
        if fb.call_activity_id:
            grouped.setdefault(fb.call_activity_id, {
                'call_log_id': fb.call_activity_id,
                'call_logs': [],
                'feedbacks': [],
                'latest_time': fb.created_at
            })
            grouped[fb.call_activity_id]['feedbacks'].append(fb)
            if fb.created_at > grouped[fb.call_activity_id]['latest_time']:
                grouped[fb.call_activity_id]['latest_time'] = fb.created_at

    call_activity_data = sorted(grouped.values(), key=lambda x: x['latest_time'], reverse=True)

    return render_template(
        'agent/feedback_history.html',
        lead=lead,
        call_activity_data=call_activity_data
    )


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

@agent_bp.route('/feedback_history')
@login_required
def feedback_history_default():
    return redirect(url_for('agent.all_feedback'))

# Additional utility routes
@agent_bp.route('/get_next_lead/<int:current_lead_id>')
@login_required
def get_next_lead(current_lead_id):
    if current_user.role != UserRole.AGENT:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get next lead in sequence
    leads = Lead.query.filter_by(
        assigned_agent_id=current_user.id
    ).filter(
        Lead.status.in_(['assigned', 'callback'])
    ).order_by(
        db.case(
            (Lead.status == 'callback', 1),
            (Lead.status == 'assigned', 2),
            else_=3
        ),
        Lead.assigned_date.desc()
    ).all()
    
    current_index = next((i for i, l in enumerate(leads) if l.id == current_lead_id), -1)
    
    if current_index < len(leads) - 1:
        next_lead = leads[current_index + 1]
        return jsonify({
            'next_lead_id': next_lead.id,
            'next_lead_url': url_for('agent.call_lead', lead_id=next_lead.id)
        })
    else:
        return jsonify({'next_lead_id': None, 'message': 'No more leads'})
@agent_bp.route('/add_frontend_log', methods=['POST'])
@login_required
def add_frontend_log():
    data = request.get_json()
    lead_id = data.get('lead_id')
    agent_id = data.get('agent_id')
    call_log_id = data.get('call_log_id')  # ✅ New
    message = data.get('message')
    log_type = data.get('type', 'info')
    timestamp = data.get('timestamp')
    print(call_log_id)
    if not lead_id or not agent_id:
        return jsonify(success=False, message="Missing lead_id or agent_id"), 400

    new_log = CallActivityLog(
        agent_id=agent_id,
        lead_id=lead_id,
        call_log_id=call_log_id,  # ✅ Link to specific call log
        message=message,
        type=log_type
    )

    db.session.add(new_log)
    db.session.commit()

    print(f"[{timestamp}] Lead {lead_id} | Agent {agent_id} | {log_type.upper()} - {message}")

    return jsonify(success=True, log=new_log.to_dict())

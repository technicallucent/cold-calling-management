from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, UserRole, Lead, LeadFeedback, LeadReassignment, LeadAssignmentHistory, CallLog, CallStatus, FeedbackType, InterestLevel,Project,Location,CallActivityLog
import pandas as pd
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, and_

admin_bp = Blueprint('admin', __name__)

# -----------------------------
# Helper Functions
# -----------------------------
def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def admin_required():
    if current_user.role != UserRole.ADMIN:
        flash('Access denied!', 'error')
        return False
    return True

def get_admin_stats():
    """Get comprehensive admin dashboard statistics"""
    total_leads = Lead.query.count()
    total_agents = User.query.filter_by(role=UserRole.AGENT, is_active=True).count()
    new_leads = Lead.query.filter_by(status='new').count()
    assigned_leads = Lead.query.filter_by(status='assigned').count()
    completed_leads = Lead.query.filter_by(status='completed').count()
    interested_leads = Lead.query.filter_by(status='interested').count()
    
    # Today's stats
    today = datetime.utcnow().date()
    today_calls = CallLog.query.filter(func.date(CallLog.call_time) == today).count()
    
    # Recent activity
    recent_feedbacks = LeadFeedback.query.order_by(LeadFeedback.created_at.desc()).limit(5).all()
    recent_reassignments = LeadReassignment.query.order_by(LeadReassignment.reassigned_at.desc()).limit(5).all()
    
    # Agent performance stats
    agent_stats = db.session.query(
        User.username,
        func.count(Lead.id).label('total_leads'),
        func.count(LeadFeedback.id).label('total_feedbacks'),
        func.avg(CallLog.duration_seconds).label('avg_call_duration')
    ).select_from(User)\
     .outerjoin(Lead, User.id == Lead.assigned_agent_id)\
     .outerjoin(LeadFeedback, User.id == LeadFeedback.agent_id)\
     .outerjoin(CallLog, User.id == CallLog.agent_id)\
     .filter(User.role == UserRole.AGENT, User.is_active == True)\
     .group_by(User.id, User.username)\
     .all()
    
    return {
        'total_leads': total_leads,
        'total_agents': total_agents,
        'new_leads': new_leads,
        'assigned_leads': assigned_leads,
        'completed_leads': completed_leads,
        'interested_leads': interested_leads,
        'today_calls': today_calls,
        'recent_feedbacks': recent_feedbacks,
        'recent_reassignments': recent_reassignments,
        'agent_stats': agent_stats
    }

# -----------------------------
# Dashboard
# -----------------------------
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    stats = get_admin_stats()
    
    return render_template('admin/dashboard.html', **stats)

# -----------------------------
# Upload / Add Leads
# -----------------------------
@admin_bp.route('/upload-leads', methods=['GET'])
@login_required
def upload_leads_page():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    return render_template('admin/upload_leads.html')

@admin_bp.route('/add_lead', methods=['POST'])
@login_required
def add_lead():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403

    name = request.form.get('name')
    email = request.form.get('email') or None
    mobile = request.form.get('mobile')
    pincode = request.form.get('pincode') or 'N/A'
    project_name = request.form.get('project_name') or 'N/A'
    source = request.form.get('source') or 'N/A'
    year = request.form.get('year') or None
    location = request.form.get('location') or 'N/A'
    
    if not mobile:
        flash('Mobile number is required', 'error')
        return redirect(url_for('admin.leads_management'))
    
    # Check for duplicate mobile
    existing_lead = Lead.query.filter_by(mobile=mobile).first()
    if existing_lead:
        flash('Lead with this mobile number already exists', 'error')
        return redirect(url_for('admin.leads_management'))
    
    lead = Lead(
        name=name,
        email=email,
        mobile=mobile,
        pincode=pincode,
        project_name=project_name,
        source=source,
        year=year,
        location=location
    )
    
    try:
        db.session.add(lead)
        db.session.commit()
        flash('Lead added successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Error adding lead. Please try again.', 'error')
    
    return redirect(url_for('admin.leads_management'))

@admin_bp.route('/upload_leads', methods=['POST'])
@login_required
def upload_leads():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin.leads_management'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin.leads_management'))
    
    if file and allowed_file(file.filename, {'csv', 'xlsx', 'xls'}):
        filename = secure_filename(file.filename)
        upload_dir = 'uploads/csv_files'
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            
            required_columns = ['name', 'mobile']
            if not all(col in df.columns for col in required_columns):
                flash('CSV must contain "name" and "mobile" columns', 'error')
                return redirect(url_for('admin.leads_management'))
            
            leads_added = 0
            duplicates_skipped = 0
            
            for _, row in df.iterrows():
                if pd.isna(row['mobile']):
                    continue
                
                # Check for duplicate mobile
                mobile_str = str(row['mobile']).strip()
                if Lead.query.filter_by(mobile=mobile_str).first():
                    duplicates_skipped += 1
                    continue
                
                lead = Lead(
                    name=str(row['name']).strip() if not pd.isna(row['name']) else 'N/A',
                    email=str(row['email']).strip() if 'email' in df.columns and not pd.isna(row['email']) else None,
                    mobile=mobile_str,
                    pincode=str(row['pincode']).strip() if 'pincode' in df.columns and not pd.isna(row['pincode']) else 'N/A',
                    project_name=str(row['project_name']).strip() if 'project_name' in df.columns and not pd.isna(row['project_name']) else 'N/A',
                    source=str(row['source']).strip() if 'source' in df.columns and not pd.isna(row['source']) else 'N/A',
                    year=int(row['year']) if 'year' in df.columns and not pd.isna(row['year']) else None,
                    location=str(row['location']).strip() if 'location' in df.columns and not pd.isna(row['location']) else 'N/A'
                )
                db.session.add(lead)
                leads_added += 1
            
            db.session.commit()
            
            if duplicates_skipped > 0:
                flash(f'Successfully added {leads_added} leads. Skipped {duplicates_skipped} duplicates.', 'warning')
            else:
                flash(f'Successfully added {leads_added} leads from file!', 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'error')
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        flash('Invalid file type. Please upload CSV or Excel file.', 'error')
    
    return redirect(url_for('admin.leads_management'))

# -----------------------------
# Leads Management
# -----------------------------
@admin_bp.route('/leads', methods=['GET'])
@login_required
def leads_management():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))

    query = Lead.query

    # Filters
    if request.args.get('name'):
        query = query.filter(Lead.name.ilike(f"%{request.args['name']}%"))
    if request.args.get('mobile'):
        query = query.filter(Lead.mobile.ilike(f"%{request.args['mobile']}%"))
    if request.args.get('project_name'):
        query = query.filter(Lead.project_name.ilike(f"%{request.args['project_name']}%"))
    if request.args.get('pincode'):
        query = query.filter(Lead.pincode.ilike(f"%{request.args['pincode']}%"))
    if request.args.get('status') and request.args.get('status') != 'all':
        query = query.filter(Lead.status == request.args['status'])
    if request.args.get('agent_id') and request.args.get('agent_id') != 'all':
        query = query.filter(Lead.assigned_agent_id == request.args['agent_id'])

    # Sorting
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'desc')
    
    if sort_by == 'name':
        query = query.order_by(Lead.name.asc() if sort_order == 'asc' else Lead.name.desc())
    elif sort_by == 'created_at':
        query = query.order_by(Lead.created_at.asc() if sort_order == 'asc' else Lead.created_at.desc())
    elif sort_by == 'assigned_date':
        query = query.order_by(Lead.assigned_date.asc() if sort_order == 'asc' else Lead.assigned_date.desc())
    else:
        query = query.order_by(Lead.id.asc() if sort_order == 'asc' else Lead.id.desc())

    leads = query.all()
    agents = User.query.filter_by(role=UserRole.AGENT, is_active=True).all()
    
    # Statistics for the page
    total_leads = Lead.query.count()
    new_leads = Lead.query.filter_by(status='new').count()
    assigned_leads = Lead.query.filter_by(status='assigned').count()
    completed_leads = Lead.query.filter_by(status='completed').count()
    projects = Project.query.all()
    return render_template('admin/leads_management.html', 
                         leads=leads, 
                         agents=agents,
                         total_leads=total_leads,
                         new_leads=new_leads,
                         assigned_leads=assigned_leads,
                         completed_leads=completed_leads,    projects=projects)

@admin_bp.route('/assign_lead', methods=['POST'])
@login_required
def assign_lead():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    lead_id = request.form.get('lead_id')
    agent_id = request.form.get('agent_id')
    project_id = request.form.get('project_id')
    assignment_note = request.form.get('assignment_note', 'Manual assignment by admin')

    lead = Lead.query.get(lead_id)
    agent = User.query.get(agent_id)
    project = Project.query.get(project_id)

    if not lead or not agent or not project:
        flash('Lead, agent, or project not found', 'error')
        return redirect(url_for('admin.leads_management'))

    # track reassignment
    if lead.assigned_agent_id and lead.assigned_agent_id != agent.id:
        reassignment = LeadReassignment(
            lead_id=lead.id,
            from_agent_id=lead.assigned_agent_id,
            to_agent_id=agent.id,
            reason=f'Reassigned | {assignment_note}'
        )
        db.session.add(reassignment)

    # assign
    previous_agent_id = lead.assigned_agent_id
    previous_project_id = lead.project_id

    lead.assigned_agent_id = agent.id
    lead.assigned_date = datetime.utcnow()
    lead.status = 'assigned'
    lead.project_id = project.id

    # history
    history = LeadAssignmentHistory(
        lead_id=lead.id,
        agent_id=agent.id,
        assigned_by_id=current_user.id,
        previous_agent_id=previous_agent_id,
        previous_project_id=previous_project_id,
        project_id=project.id,
        note=assignment_note
    )
    db.session.add(history)

    try:
        db.session.commit()
        flash(f'Lead assigned to {agent.username} for project {project.name}', 'success')
    except:
        db.session.rollback()
        flash('Error assigning lead', 'error')

    return redirect(url_for('admin.leads_management'))

@admin_bp.route('/bulk_assign', methods=['POST'])
@login_required
def bulk_assign():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403

    lead_ids = request.form.getlist('lead_ids')
    agent_id = request.form.get('agent_id')
    project_id = request.form.get('project_id')
    assignment_note = request.form.get('bulk_assignment_note', 'Bulk assignment by admin')

    if not lead_ids or not agent_id or not project_id:
        flash('Select leads, agent, and project.', 'error')
        return redirect(url_for('admin.leads_management'))

    agent = User.query.get(agent_id)
    project = Project.query.get(project_id)

    if not agent or not project:
        flash('Agent or project not found.', 'error')
        return redirect(url_for('admin.leads_management'))

    leads = Lead.query.filter(Lead.id.in_(lead_ids)).all()
    assigned_count = 0

    for lead in leads:

        # track reassignment
        if lead.assigned_agent_id and lead.assigned_agent_id != agent.id:
            reassignment = LeadReassignment(
                lead_id=lead.id,
                from_agent_id=lead.assigned_agent_id,
                to_agent_id=agent.id,
                reason=f'Bulk reassignment | {assignment_note}'
            )
            db.session.add(reassignment)

        previous_agent_id = lead.assigned_agent_id
        previous_project_id = lead.project_id

        lead.assigned_agent_id = agent.id
        lead.assigned_date = datetime.utcnow()
        lead.status = "assigned"
        lead.project_id = project.id

        # history
        history = LeadAssignmentHistory(
            lead_id=lead.id,
            agent_id=agent.id,
            assigned_by_id=current_user.id,
            previous_agent_id=previous_agent_id,
            previous_project_id=previous_project_id,
            project_id=project.id,
            note=assignment_note
        )
        db.session.add(history)

        assigned_count += 1

    try:
        db.session.commit()
        flash(f'{assigned_count} leads assigned to {agent.username} for project {project.name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error assigning leads.', 'error')

    return redirect(url_for('admin.leads_management'))

@admin_bp.route('/delete_lead/<int:lead_id>', methods=['POST'])
@login_required
def delete_lead(lead_id):
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    lead = Lead.query.get_or_404(lead_id)
    
    try:
        # Delete related records first
        LeadFeedback.query.filter_by(lead_id=lead_id).delete()
        LeadReassignment.query.filter_by(lead_id=lead_id).delete()
        LeadAssignmentHistory.query.filter_by(lead_id=lead_id).delete()
        CallLog.query.filter_by(lead_id=lead_id).delete()
        
        # Delete the lead
        db.session.delete(lead)
        db.session.commit()
        flash('Lead deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting lead. Please try again.', 'error')
    
    return redirect(url_for('admin.leads_management'))

@admin_bp.route('/update_lead_status', methods=['POST'])
@login_required
def update_lead_status():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    lead_id = request.form.get('lead_id')
    new_status = request.form.get('status')
    
    lead = Lead.query.get(lead_id)
    if lead:
        lead.status = new_status
        lead.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Lead status updated successfully!', 'success')
    else:
        flash('Lead not found', 'error')
    
    return redirect(url_for('admin.leads_management'))

# -----------------------------
# Agent Management
# -----------------------------
@admin_bp.route('/agents')
@login_required
def agents_management():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    # Get all agents
    agents = User.query.filter_by(role=UserRole.AGENT).order_by(User.created_at.desc()).all()

    # Build agent statistics
    agent_stats = []
    today = datetime.utcnow().date()

    for agent in agents:
        assigned_leads = Lead.query.filter_by(assigned_agent_id=agent.id).count()
        completed_leads = Lead.query.filter_by(assigned_agent_id=agent.id, status='completed').count()
        total_feedbacks = LeadFeedback.query.filter_by(agent_id=agent.id).count()
        today_calls = CallLog.query.filter(
            CallLog.agent_id == agent.id,
            func.date(CallLog.call_time) == today
        ).count()

        agent_stats.append({
            'agent': agent,
            'assigned_leads': assigned_leads,
            'completed_leads': completed_leads,
            'total_feedbacks': total_feedbacks,
            'today_calls': today_calls
        })

    return render_template(
        'admin/agents.html',
        agent_stats=agent_stats
    )

@admin_bp.route('/add_agent', methods=['POST'])
@login_required
def add_agent():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    phone_number = request.form.get('phone_number')
    department = request.form.get('department')

    # Check for existing username
    if User.query.filter_by(username=username).first():
        flash('Username already exists', 'error')
        return redirect(url_for('admin.agents_management'))

    # Check for existing email
    if User.query.filter_by(email=email).first():
        flash('Email already exists', 'error')
        return redirect(url_for('admin.agents_management'))

    # Create the agent
    agent = User(
        username=username,
        email=email,
        password=generate_password_hash(password),
        role=UserRole.AGENT,
        phone_number=phone_number,
        department=department
    )
    
    try:
        db.session.add(agent)
        db.session.commit()
        flash('Agent added successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Error: Could not add agent. Please try again.', 'error')

    return redirect(url_for('admin.agents_management'))

@admin_bp.route('/deactivate_agent/<int:agent_id>', methods=['POST'])
@login_required
def deactivate_agent(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get(agent_id)
    if agent and agent.role == UserRole.AGENT:
        agent.is_active = False
        db.session.commit()
        flash('Agent deactivated successfully!', 'success')
    else:
        flash('Agent not found', 'error')
    
    return redirect(url_for('admin.agents_management'))

@admin_bp.route('/activate_agent/<int:agent_id>', methods=['POST'])
@login_required
def activate_agent(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get(agent_id)
    if agent and agent.role == UserRole.AGENT:
        agent.is_active = True
        db.session.commit()
        flash('Agent activated successfully!', 'success')
    else:
        flash('Agent not found', 'error')
    
    return redirect(url_for('admin.agents_management'))

@admin_bp.route('/reset_agent_password/<int:agent_id>', methods=['POST'])
@login_required
def reset_agent_password(agent_id):
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    agent = User.query.get(agent_id)
    if agent and agent.role == UserRole.AGENT:
        new_password = request.form.get('new_password')
        if new_password:
            agent.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Agent password reset successfully!', 'success')
        else:
            flash('New password is required', 'error')
    else:
        flash('Agent not found', 'error')
    
    return redirect(url_for('admin.agents_management'))

# -----------------------------
# Detailed Views
# -----------------------------
@admin_bp.route('/agent/<int:agent_id>')
@login_required
def agent_details(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get_or_404(agent_id)
    
    # Get comprehensive agent statistics
    assigned_leads = Lead.query.filter_by(assigned_agent_id=agent.id).order_by(Lead.assigned_date.desc()).all()
    feedbacks = LeadFeedback.query.filter_by(agent_id=agent.id).order_by(LeadFeedback.created_at.desc()).all()
    call_logs = CallLog.query.filter_by(agent_id=agent.id).order_by(CallLog.call_time.desc()).limit(50).all()
    
    # Performance metrics
    total_calls = CallLog.query.filter_by(agent_id=agent.id).count()
    completed_calls = CallLog.query.filter_by(agent_id=agent.id, status=CallStatus.COMPLETED).count()
    interested_leads = LeadFeedback.query.filter_by(agent_id=agent.id, feedback_type=FeedbackType.INTERESTED).count()
    
    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_calls = CallLog.query.filter(
        CallLog.agent_id == agent.id,
        CallLog.call_time >= week_ago
    ).count()
    
    return render_template(
        'admin/agent_details.html',
        agent=agent,
        assigned_leads=assigned_leads,
        feedbacks=feedbacks,
        call_logs=call_logs,
        total_calls=total_calls,
        completed_calls=completed_calls,
        interested_leads=interested_leads,
        recent_calls=recent_calls
    )

@admin_bp.route('/agent/<int:agent_id>/history')
@login_required
def agent_history(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get_or_404(agent_id)
    
    # Get all agent activities
    assigned_leads = Lead.query.filter_by(assigned_agent_id=agent.id).order_by(Lead.assigned_date.desc()).all()
    feedbacks = LeadFeedback.query.filter_by(agent_id=agent.id).order_by(LeadFeedback.created_at.desc()).all()
    reassignments_from = LeadReassignment.query.filter_by(from_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    reassignments_to = LeadReassignment.query.filter_by(to_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    call_logs = CallLog.query.filter_by(agent_id=agent.id).order_by(CallLog.call_time.desc()).all()
    
    return render_template(
        'admin/agent_history.html',
        agent=agent,
        assigned_leads=assigned_leads,
        feedbacks=feedbacks,
        reassignments_from=reassignments_from,
        reassignments_to=reassignments_to,
        call_logs=call_logs
    )

@admin_bp.route('/lead/<int:lead_id>')
@login_required
def lead_details(lead_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    lead = Lead.query.get_or_404(lead_id)
    
    # Get comprehensive lead history
    
    reassignments = LeadReassignment.query.filter_by(lead_id=lead.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    
    assignment_history = LeadAssignmentHistory.query.filter_by(lead_id=lead.id).order_by(LeadAssignmentHistory.assigned_at.desc()).all()
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
        'admin/lead_details.html',
        lead=lead,
        feedbacks=feedbacks,
        reassignments=reassignments,
        call_logs=call_logs,
        assignment_history=assignment_history,
        call_activity_data=call_activity_data
    )

@admin_bp.route('/reassignments')
@login_required
def reassignments_history():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    reassignments = LeadReassignment.query.order_by(LeadReassignment.reassigned_at.desc()).all()
    
    return render_template('admin/reassignments.html', reassignments=reassignments)

@admin_bp.route('/feedbacks')
@login_required
def feedbacks_history():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    feedbacks = LeadFeedback.query.order_by(LeadFeedback.created_at.desc()).all()
    
    return render_template('admin/feedbacks.html', feedbacks=feedbacks)

@admin_bp.route('/call-logs')
@login_required
def call_logs_history():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    call_logs = CallLog.query.order_by(CallLog.call_time.desc()).all()
    
    return render_template('admin/call_logs.html', call_logs=call_logs)

# -----------------------------
# Reports & Analytics
# -----------------------------
@admin_bp.route('/reports')
@login_required
def reports():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    # Basic statistics
    total_leads = Lead.query.count()
    total_agents = User.query.filter_by(role=UserRole.AGENT, is_active=True).count()
    total_calls = CallLog.query.count()
    
    # Lead status distribution
    status_distribution = db.session.query(
        Lead.status,
        func.count(Lead.id).label('count')
    ).group_by(Lead.status).all()
    
    # Call status distribution
    call_status_distribution = db.session.query(
        CallLog.status,
        func.count(CallLog.id).label('count')
    ).group_by(CallLog.status).all()
    
    # Feedback type distribution
    feedback_distribution = db.session.query(
        LeadFeedback.feedback_type,
        func.count(LeadFeedback.id).label('count')
    ).group_by(LeadFeedback.feedback_type).all()
    
    # Monthly trends (last 6 months)
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    
    monthly_leads = db.session.query(
        func.date_trunc('month', Lead.created_at).label('month'),
        func.count(Lead.id).label('count')
    ).filter(Lead.created_at >= six_months_ago)\
     .group_by(func.date_trunc('month', Lead.created_at))\
     .order_by('month').all()
    
    monthly_calls = db.session.query(
        func.date_trunc('month', CallLog.call_time).label('month'),
        func.count(CallLog.id).label('count')
    ).filter(CallLog.call_time >= six_months_ago)\
     .group_by(func.date_trunc('month', CallLog.call_time))\
     .order_by('month').all()
    
    return render_template(
        'admin/reports.html',
        total_leads=total_leads,
        total_agents=total_agents,
        total_calls=total_calls,
        status_distribution=status_distribution,
        call_status_distribution=call_status_distribution,
        feedback_distribution=feedback_distribution,
        monthly_leads=monthly_leads,
        monthly_calls=monthly_calls
    )

# -----------------------------
# API Endpoints for Data
# -----------------------------
@admin_bp.route('/api/lead_stats')
@login_required
def api_lead_stats():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    stats = {
        'total': Lead.query.count(),
        'new': Lead.query.filter_by(status='new').count(),
        'assigned': Lead.query.filter_by(status='assigned').count(),
        'completed': Lead.query.filter_by(status='completed').count(),
        'interested': Lead.query.filter_by(status='interested').count()
    }
    
    return jsonify(stats)

@admin_bp.route('/api/agent_performance')
@login_required
def api_agent_performance():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    performance_data = db.session.query(
        User.username,
        func.count(Lead.id).label('assigned_leads'),
        func.count(LeadFeedback.id).label('completed_feedbacks'),
        func.avg(CallLog.duration_seconds).label('avg_call_duration')
    ).select_from(User)\
     .outerjoin(Lead, User.id == Lead.assigned_agent_id)\
     .outerjoin(LeadFeedback, User.id == LeadFeedback.agent_id)\
     .outerjoin(CallLog, User.id == CallLog.agent_id)\
     .filter(User.role == UserRole.AGENT, User.is_active == True)\
     .group_by(User.id, User.username)\
     .all()
    
    result = []
    for data in performance_data:
        result.append({
            'agent': data.username,
            'assigned_leads': data.assigned_leads or 0,
            'completed_feedbacks': data.completed_feedbacks or 0,
            'avg_call_duration': round(data.avg_call_duration or 0, 2)
        })
    
    return jsonify(result)
# ---------------------------
# Show all projects
# ---------------------------
@admin_bp.route("/projects")
def list_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("admin/projects_list.html", projects=projects)


# ---------------------------
# Create project (GET + POST)
# ---------------------------


@admin_bp.route("/projects/create", methods=["GET", "POST"])
def create_project():
    if request.method == "POST":
        project_id = request.form.get("project_id")
        name = request.form.get("name")

        new_project = Project(project_id=project_id, name=name)

        try:
            db.session.add(new_project)
            db.session.commit()
            flash("Project created successfully!", "success")
            return redirect(url_for("admin.list_projects"))

        except IntegrityError:
            db.session.rollback()
            flash("Project name or Project ID already exists!", "error")
            return redirect(url_for("admin.create_project"))

    return render_template("admin/project_create.html")

# ---------------------------
# Delete project
# ---------------------------
@admin_bp.route("/projects/delete/<int:id>", methods=["POST"])
def delete_project(id):
    project = Project.query.get_or_404(id)
    db.session.delete(project)
    db.session.commit()
    flash("Project deleted!", "success")
    return redirect(url_for("admin.list_projects"))
@admin_bp.route("/locations")
def list_locations():
    locations = Location.query.order_by(Location.created_at.desc()).all()
    return render_template("admin/locations_list.html", locations=locations)


# -----------------------------
# Create location
# -----------------------------
@admin_bp.route("/locations/create", methods=["GET", "POST"])
def create_location():
    if request.method == "POST":
        name = request.form.get("name")

        if not name:
            flash("Location name is required!", "error")
            return redirect(url_for("admin.create_location"))

        new_location = Location(name=name)

        try:
            db.session.add(new_location)
            db.session.commit()
            flash("Location created successfully!", "success")
            return redirect(url_for("admin.list_locations"))

        except IntegrityError:
            db.session.rollback()
            flash("Location name already exists!", "error")
            return redirect(url_for("admin.create_location"))

    return render_template("admin/location_create.html")


# -----------------------------
# Delete location
# -----------------------------
@admin_bp.route("/locations/delete/<int:id>", methods=["POST"])
def delete_location(id):
    loc = Location.query.get_or_404(id)
    db.session.delete(loc)
    db.session.commit()
    flash("Location deleted!", "success")
    return redirect(url_for("admin.list_locations"))
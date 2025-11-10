from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, UserRole, Lead, LeadFeedback, LeadReassignment,LeadAssignmentHistory
import pandas as pd
import os
from datetime import datetime
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError
admin_bp = Blueprint('admin', __name__)

# -----------------------------
# Helper
# -----------------------------
def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def admin_required():
    if current_user.role != UserRole.ADMIN:
        flash('Access denied!', 'error')
        return redirect(url_for('agent.dashboard'))
    return True

# -----------------------------
# Dashboard
# -----------------------------
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    total_leads = Lead.query.count()
    total_agents = User.query.filter_by(role=UserRole.AGENT, is_active=True).count()
    new_leads = Lead.query.filter_by(status='new').count()
    
    return render_template('admin/dashboard.html', 
                           total_leads=total_leads,
                           total_agents=total_agents,
                           new_leads=new_leads)

# -----------------------------
# Upload / Add Leads Page
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
    
    db.session.add(lead)
    db.session.commit()
    flash('Lead added successfully!', 'success')
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
        filepath = os.path.join('uploads/csv_files', filename)
        file.save(filepath)
        
        try:
            df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
            leads_added = 0
            
            for _, row in df.iterrows():
                if 'mobile' not in df.columns or pd.isna(row['mobile']):
                    continue
                lead = Lead(
                    name=row.get('name', 'N/A'),
                    email=row.get('email') or None,
                    mobile=str(row['mobile']),
                    pincode=row.get('pincode', 'N/A'),
                    project_name=row.get('project_name', 'N/A'),
                    source=row.get('source', 'N/A'),
                    year=row.get('year') or None,
                    location=row.get('location', 'N/A')
                )
                db.session.add(lead)
                leads_added += 1
            
            db.session.commit()
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
    if request.args.get('status'):
        query = query.filter(Lead.status == request.args['status'])

    leads = query.order_by(Lead.id.desc()).all()
    agents = User.query.filter_by(role=UserRole.AGENT, is_active=True).all()
    
    return render_template('admin/leads_management.html', leads=leads, agents=agents)

@admin_bp.route('/assign_lead', methods=['POST'])
@login_required
def assign_lead():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    lead_id = request.form.get('lead_id')
    agent_id = request.form.get('agent_id')
    
    lead = Lead.query.get(lead_id)
    agent = User.query.get(agent_id)
    
    if not lead or not agent:
        flash('Lead or agent not found', 'error')
        return redirect(url_for('admin.leads_management'))

    # Track reassignment if lead already assigned
    if lead.assigned_agent_id and lead.assigned_agent_id != agent.id:
        reassignment = LeadReassignment(
            lead_id=lead.id,
            from_agent_id=lead.assigned_agent_id,
            to_agent_id=agent.id,
            reason='Manual reassignment by admin'
        )
        db.session.add(reassignment)

    # Assign the lead
    lead.assigned_agent_id = agent.id
    lead.assigned_date = datetime.utcnow()
    lead.status = 'assigned'

    # Record assignment history
    history = LeadAssignmentHistory(
        lead_id=lead.id,
        agent_id=agent.id,
        assigned_by_id=current_user.id,
        note='Manual assign' if not lead.assigned_agent_id else 'Reassigned manually'
    )
    db.session.add(history)

    db.session.commit()
    flash('Lead assigned successfully!', 'success')
    return redirect(url_for('admin.leads_management'))

@admin_bp.route('/bulk_assign', methods=['POST'])
@login_required
def bulk_assign():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403

    lead_ids = request.form.getlist('lead_ids')
    agent_id = request.form.get('agent_id')

    if not lead_ids or not agent_id:
        flash('Select at least one lead and an agent.', 'error')
        return redirect(url_for('admin.leads_management'))

    agent = User.query.get(agent_id)
    if not agent:
        flash('Agent not found.', 'error')
        return redirect(url_for('admin.leads_management'))

    leads = Lead.query.filter(Lead.id.in_(lead_ids)).all()
    for lead in leads:
        # Track reassignment if already assigned
        if lead.assigned_agent_id and lead.assigned_agent_id != agent.id:
            reassignment = LeadReassignment(
                lead_id=lead.id,
                from_agent_id=lead.assigned_agent_id,
                to_agent_id=agent.id,
                reason='Bulk reassignment by admin'
            )
            db.session.add(reassignment)

        # Assign lead
        lead.assigned_agent_id = agent.id
        lead.assigned_date = datetime.utcnow()
        lead.status = 'assigned'

        # Record assignment history
        history = LeadAssignmentHistory(
            lead_id=lead.id,
            agent_id=agent.id,
            assigned_by_id=current_user.id,
            note='Bulk assign'
        )
        db.session.add(history)

    db.session.commit()
    flash(f'{len(leads)} leads assigned to {agent.username} successfully!', 'success')
    return redirect(url_for('admin.leads_management'))

# -----------------------------
# Agent Details
# -----------------------------
@admin_bp.route('/agent/<int:agent_id>')
@login_required
def agent_details(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get_or_404(agent_id)
    assigned_leads = Lead.query.filter_by(assigned_agent_id=agent.id).order_by(Lead.assigned_date.desc()).all()
    feedbacks = LeadFeedback.query.filter_by(agent_id=agent.id).order_by(LeadFeedback.call_date.desc()).all()
    reassignments_from = LeadReassignment.query.filter_by(from_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    reassignments_to = LeadReassignment.query.filter_by(to_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    
    return render_template(
        'admin/agent_details.html',
        agent=agent,
        assigned_leads=assigned_leads,
        feedbacks=feedbacks,
        reassignments_from=reassignments_from,
        reassignments_to=reassignments_to
    )
@admin_bp.route('/agent/<int:agent_id>/history')
@login_required
def agent_history(agent_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agent = User.query.get_or_404(agent_id)
    
    # Leads assigned to this agent
    assigned_leads = Lead.query.filter_by(assigned_agent_id=agent.id).order_by(Lead.assigned_date.desc()).all()
    
    # Feedbacks by this agent
    feedbacks = LeadFeedback.query.filter_by(agent_id=agent.id).order_by(LeadFeedback.call_date.desc()).all()
    
    # Reassignments from this agent
    reassignments_from = LeadReassignment.query.filter_by(from_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    
    # Reassignments to this agent
    reassignments_to = LeadReassignment.query.filter_by(to_agent_id=agent.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    
    return render_template(
        'admin/agent_history.html',
        agent=agent,
        assigned_leads=assigned_leads,
        feedbacks=feedbacks,
        reassignments_from=reassignments_from,
        reassignments_to=reassignments_to
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
    
    feedbacks = LeadFeedback.query.order_by(LeadFeedback.call_date.desc()).all()
    
    return render_template('admin/feedbacks.html', feedbacks=feedbacks)

# -----------------------------
# Agents Management
# -----------------------------
@admin_bp.route('/agents')
@login_required
def agents_management():
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    agents = User.query.filter_by(role=UserRole.AGENT).all()
    return render_template('admin/agents.html', agents=agents)


@admin_bp.route('/add_agent', methods=['POST'])
@login_required
def add_agent():
    if not admin_required():
        return jsonify({'error': 'Access denied'}), 403
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')

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
        role=UserRole.AGENT
    )
    
    db.session.add(agent)
    try:
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
@admin_bp.route('/lead/<int:lead_id>')
@login_required
def lead_details(lead_id):
    if not admin_required():
        return redirect(url_for('agent.dashboard'))
    
    lead = Lead.query.get_or_404(lead_id)
    
    # Feedback history for this lead
    feedbacks = LeadFeedback.query.filter_by(lead_id=lead.id).order_by(LeadFeedback.call_date.desc()).all()
    
    # Reassignment history for this lead
    reassignments = LeadReassignment.query.filter_by(lead_id=lead.id).order_by(LeadReassignment.reassigned_at.desc()).all()
    
    return render_template(
        'admin/lead_details.html',
        lead=lead,
        feedbacks=feedbacks,
        reassignments=reassignments
    )

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, UserRole

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == UserRole.ADMIN:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('agent.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            
            if user.role == UserRole.ADMIN:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('agent.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

# Create admin user (run once)
def create_admin_user():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            password=generate_password_hash('admin123'),
            role=UserRole.ADMIN
        )
        db.session.add(admin)
        db.session.commit()
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from models import db, User, UserRole
from config import Config
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    
    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Create upload directories
    os.makedirs('uploads/recordings', exist_ok=True)
    os.makedirs('uploads/csv_files', exist_ok=True)
    
    # Register blueprints
    from routes.auth_routes import auth_bp
    from routes.admin_routes import admin_bp
    from routes.agent_routes import agent_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(agent_bp, url_prefix='/agent')
    
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == UserRole.ADMIN:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('agent.dashboard'))
        return redirect(url_for('auth.login'))
    
    return app
app = create_app()
if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        from routes.auth_routes import create_admin_user
        create_admin_user()
        
    app.run(debug=True)
from app import create_app
from routes.auth_routes import create_admin_user
from models import db

app = create_app()
with app.app_context():
    db.create_all()
    create_admin_user()
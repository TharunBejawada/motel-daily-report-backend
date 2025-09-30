# app/repositories/init_db.py
from app.repositories.session import engine
from app.db.models import Base

def init_db():
    print("📦 Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully!")

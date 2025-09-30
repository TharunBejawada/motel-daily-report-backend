# app/repositories/session.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base  # ✅ This must match where your models.py is

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./motel_reports.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class DBSessionCtx:
    def __enter__(self):
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc:
                self.db.rollback()
            else:
                self.db.commit()
        finally:
            self.db.close()

def get_session():
    return DBSessionCtx()

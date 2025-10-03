# app/api/motels.py
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.repositories.session import get_session
from app.db.models import MotelMaster

router = APIRouter(tags=["motels"])

@router.get("/list")
def list_motels():
    try:
        with get_session() as db:
            rows = db.query(MotelMaster).order_by(MotelMaster.motel_name.asc()).all()
            return [
                {"id": m.id, "motel_name": m.motel_name, "location": m.location}
                for m in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list motels: {e}")

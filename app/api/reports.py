from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.services.report_service import ingest_reports_from_gmail

router = APIRouter(tags=["reports"])

@router.get("/fetch")
def fetch_reports(
    mode: str = Query("recent", enum=["recent", "all"]),
    limit: int = Query(5, ge=1, le=50),
    pages: Optional[int] = Query(None, ge=1, le=50),
    after: Optional[str] = Query(None, description="YYYY/MM/DD"),
    before: Optional[str] = Query(None, description="YYYY/MM/DD"),
):
    try:
        result = ingest_reports_from_gmail(mode=mode, limit=limit, pages=pages, after=after, before=before)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch reports: {e}")

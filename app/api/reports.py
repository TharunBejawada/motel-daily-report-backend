# app/api/reports.py
from fastapi import APIRouter, Query, HTTPException, Response
from typing import Optional, List, Dict, Any

from app.services.report_service import ingest_reports_from_gmail  # your existing fetcher
from app.repositories.session import get_session
from app.db.models import (
    MotelMaster,
    ReportMaster,
    ReportVacantDirtyRoom,
    ReportOutOfOrderRoom,
    ReportCompRoom,
    ReportIncident,
)
from app.services.export_service import (
    get_report_json, export_report_pdf, export_report_docx
)

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

# ---------- NEW: LIST REPORTS ----------
@router.get("")
def list_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    motel_id: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    try:
        with get_session() as db:
            q = db.query(ReportMaster).join(MotelMaster, ReportMaster.motel_id == MotelMaster.id)

            if motel_id:
                q = q.filter(ReportMaster.motel_id == motel_id)
            if department:
                q = q.filter(ReportMaster.department == department)
            if start_date:
                q = q.filter(ReportMaster.report_date >= start_date)
            if end_date:
                q = q.filter(ReportMaster.report_date <= end_date)

            total = q.count()
            rows = (
                q.order_by(ReportMaster.report_date.desc(), ReportMaster.id.desc())
                 .offset((page - 1) * limit)
                 .limit(limit)
                 .all()
            )

            items = []
            for r in rows:
                motel = db.query(MotelMaster).filter(MotelMaster.id == r.motel_id).first()

                items.append({
                    "id": r.id,
                    "motel_id": r.motel_id,
                    "motel_name": motel.motel_name if motel else r.property_name,
                    "location": motel.location if motel else None,
                    "report_date": r.report_date.isoformat() if r.report_date else None,
                    "department": r.department,
                    "auditor": r.auditor,
                    "revenue": r.revenue,
                    "adr": r.adr,
                    "occupancy": r.occupancy,
                    "vacant_clean": r.vacant_clean,
                    "vacant_dirty": r.vacant_dirty,
                    "out_of_order_storage_rooms": r.out_of_order_storage_rooms,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })

            return {"page": page, "limit": limit, "total": total, "items": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {e}")


# ---------- NEW: GET REPORT DETAIL ----------
@router.get("/{report_id}")
def get_report(report_id: int):
    try:
        data = get_report_json(report_id)
        return data
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get report: {e}")

# ---------- NEW: CHILD ARRAYS ----------
@router.get("/{report_id}/comp-rooms")
def get_comp_rooms(report_id: int):
    try:
        with get_session() as db:
            rows = db.query(ReportCompRoom).filter(ReportCompRoom.report_id == report_id).all()
            return [{"id": r.id, "room_number": r.room_number, "notes": r.notes} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get comp rooms: {e}")

@router.get("/{report_id}/vacant-dirty-rooms")
def get_vacant_dirty_rooms(report_id: int):
    try:
        with get_session() as db:
            rows = db.query(ReportVacantDirtyRoom).filter(ReportVacantDirtyRoom.report_id == report_id).all()
            return [{
                "id": r.id, "room_number": r.room_number, "reason": r.reason, "days": r.days, "action": r.action
            } for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vacant/dirty rooms: {e}")

@router.get("/{report_id}/out-of-order-rooms")
def get_out_of_order_rooms(report_id: int):
    try:
        with get_session() as db:
            rows = db.query(ReportOutOfOrderRoom).filter(ReportOutOfOrderRoom.report_id == report_id).all()
            return [{
                "id": r.id, "room_number": r.room_number, "reason": r.reason, "days": r.days, "action": r.action
            } for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get out-of-order rooms: {e}")

@router.get("/{report_id}/incidents")
def get_incidents(report_id: int):
    try:
        with get_session() as db:
            rows = db.query(ReportIncident).filter(ReportIncident.report_id == report_id).all()
            return [{"id": r.id, "description": r.description} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get incidents: {e}")

# ---------- NEW: EXPORT PDF ----------
@router.get("/{report_id}/export/pdf")
def export_pdf(report_id: int):
    try:
        content = export_report_pdf(report_id)
        filename = f"report_{report_id}.pdf"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export PDF: {e}")

# ---------- NEW: EXPORT DOCX ----------
@router.get("/{report_id}/export/docx")
def export_docx(report_id: int):
    try:
        content = export_report_docx(report_id)
        filename = f"report_{report_id}.docx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export DOCX: {e}")

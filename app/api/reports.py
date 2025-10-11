# app/api/reports.py
from fastapi import APIRouter, Query, HTTPException, Response
from typing import Optional, List, Dict, Any
import boto3, json, uuid, os
from datetime import datetime

import base64

from app.services.report_service import ingest_reports_from_gmail  # your existing fetcher
from app.repositories.session import get_session
from app.db.models import (
    MotelMaster,
    ReportMaster,
    ReportVacantDirtyRoom,
    ReportOutOfOrderRoom,
    ReportCompRoom,
    ReportIncident,
    ReportJob,
    JobStatus
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
    if not os.environ.get("AWS_EXECUTION_ENV"):
        # ✅ Local run — directly execute synchronously
        try:
            result = ingest_reports_from_gmail(mode=mode, limit=limit, pages=pages, after=after, before=before)
            return {"ok": True, **result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch reports: {e}")
    """Trigger async Gmail ingestion via Lambda."""
    job_id = str(uuid.uuid4())

    # Record the job in DB
    with get_session() as db:
        job = ReportJob(id=job_id, status=JobStatus.PENDING)
        db.add(job)
        db.commit()

    # Trigger async invocation
    try:
        lambda_client = boto3.client("lambda", region_name=os.environ["AWS_REGION"])
        payload = {
            "action": "fetch_reports",
            "job_id": job_id,
            "params": {"mode": mode, "limit": limit, "after": after, "before": before},
        }
        lambda_client.invoke(
            FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
            InvocationType="Event",  # async
            Payload=json.dumps(payload),
        )
        return {"job_id": job_id, "status": "STARTED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger job: {e}")
    

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

# # ---------- NEW: EXPORT PDF ----------
# @router.get("/{report_id}/export/pdf")
# def export_pdf(report_id: int):
#     try:
#         content = export_report_pdf(report_id)
#         filename = f"report_{report_id}.pdf"
#         return Response(
#             content=content,
#             media_type="application/pdf",
#             headers={"Content-Disposition": f'attachment; filename="{filename}"'}
#         )
#     except ValueError as ve:
#         raise HTTPException(status_code=404, detail=str(ve))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to export PDF: {e}")

# # ---------- NEW: EXPORT DOCX ----------
# @router.get("/{report_id}/export/docx")
# def export_docx(report_id: int):
#     try:
#         content = export_report_docx(report_id)
#         filename = f"report_{report_id}.docx"
#         return Response(
#             content=content,
#             media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
#             headers={"Content-Disposition": f'attachment; filename="{filename}"'}
#         )
#     except ValueError as ve:
#         raise HTTPException(status_code=404, detail=str(ve))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to export DOCX: {e}")

def lambda_file_response(content: bytes, mime_type: str, filename: str):
    """
    Handles binary file responses correctly for both local and AWS Lambda environments.
    """
    # ✅ Detect AWS Lambda environment
    if os.environ.get("AWS_EXECUTION_ENV"):
        # Encode to Base64 for API Gateway
        encoded = base64.b64encode(content).decode("utf-8")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": mime_type,
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
            "isBase64Encoded": True,
            "body": encoded,
        }
    else:
        # Normal FastAPI response for local dev
        return Response(
            content=content,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


# ---------- EXPORT PDF ----------
@router.get("/{report_id}/export/pdf")
def export_pdf(report_id: int):
    try:
        content = export_report_pdf(report_id)
        filename = f"report_{report_id}.pdf"
        return lambda_file_response(
            content,
            "application/pdf",
            filename
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export PDF: {e}")


# ---------- EXPORT DOCX ----------
@router.get("/{report_id}/export/docx")
def export_docx(report_id: int):
    try:
        content = export_report_docx(report_id)
        filename = f"report_{report_id}.docx"
        return lambda_file_response(
            content,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export DOCX: {e}")

    

@router.get("/status/{job_id}")
def get_report_job_status(job_id: str):
    with get_session() as db:
        job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "id": job.id,
            "status": job.status.value,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "message": job.message,
            "result_summary": job.result_summary,
        }


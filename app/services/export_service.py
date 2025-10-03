from io import BytesIO
from typing import Dict, Any, List
from sqlalchemy.orm import joinedload

from app.repositories.session import get_session
from app.db.models import (
    MotelMaster,
    ReportMaster,
    ReportVacantDirtyRoom,
    ReportOutOfOrderRoom,
    ReportCompRoom,
    ReportIncident,
)
from app.utils.pdf_generator import build_report_pdf
from app.utils.docx_generator import build_report_docx


def _report_to_dict(report: ReportMaster, motel: MotelMaster | None = None) -> Dict[str, Any]:
    """Serialize a full report with motel info and all related child tables."""
    return {
        "id": report.id,
        "motel_id": report.motel_id,
        "motel_name": motel.motel_name if motel else None,
        "location": motel.location if motel else None,
        "property_name": report.property_name,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "department": report.department,
        "auditor": report.auditor,
        "revenue": report.revenue,
        "adr": report.adr,
        "occupancy": report.occupancy,
        "vacant_clean": report.vacant_clean,
        "vacant_dirty": report.vacant_dirty,
        "out_of_order_storage_rooms": report.out_of_order_storage_rooms,
        "created_at": report.created_at.isoformat() if report.created_at else None,

        # ✅ use correct relationship names now
        "vacant_dirty_rooms": [
            {
                "id": r.id,
                "room_number": r.room_number,
                "reason": r.reason,
                "days": r.days,
                "action": r.action,
            }
            for r in (report.vacant_dirty_rooms or [])
        ],
        "out_of_order_rooms": [
            {
                "id": r.id,
                "room_number": r.room_number,
                "reason": r.reason,
                "days": r.days,
                "action": r.action,
            }
            for r in (report.out_of_order_rooms or [])
        ],
        "comp_rooms": [
            {
                "id": r.id,
                "room_number": r.room_number,
                "notes": r.notes,
            }
            for r in (report.comp_room_records or [])
        ],
        "incidents": [
            {
                "id": r.id,
                "description": r.description,
            }
            for r in (report.incident_records or [])
        ],
    }


def get_report_json(report_id: int) -> Dict[str, Any]:
    """Fetch a single report and return full JSON with motel + related data."""
    with get_session() as db:
        rpt = (
            db.query(ReportMaster)
            .options(
                joinedload(ReportMaster.vacant_dirty_rooms),
                joinedload(ReportMaster.out_of_order_rooms),
                joinedload(ReportMaster.comp_room_records),
                joinedload(ReportMaster.incident_records),
            )
            .filter(ReportMaster.id == report_id)
            .first()
        )
        if not rpt:
            raise ValueError(f"Report {report_id} not found")

        motel = db.query(MotelMaster).filter(MotelMaster.id == rpt.motel_id).first()
        return _report_to_dict(rpt, motel)


def get_all_reports_json() -> List[Dict[str, Any]]:
    """Fetch all reports with motel + related tables serialized."""
    with get_session() as db:
        reports = (
            db.query(ReportMaster)
            .options(
                joinedload(ReportMaster.vacant_dirty_rooms),
                joinedload(ReportMaster.out_of_order_rooms),
                joinedload(ReportMaster.comp_room_records),
                joinedload(ReportMaster.incident_records),
            )
            .order_by(ReportMaster.report_date.desc())
            .all()
        )

        result = []
        for rpt in reports:
            motel = db.query(MotelMaster).filter(MotelMaster.id == rpt.motel_id).first()
            result.append(_report_to_dict(rpt, motel))
        return result


def export_report_pdf(report_id: int) -> bytes:
    """Generate a PDF for a given report ID."""
    data = get_report_json(report_id)
    buf = BytesIO()
    build_report_pdf(buf, data)
    return buf.getvalue()


def export_report_docx(report_id: int) -> bytes:
    """Generate a DOCX for a given report ID."""
    data = get_report_json(report_id)
    buf = BytesIO()
    build_report_docx(buf, data)
    return buf.getvalue()

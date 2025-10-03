# app/utils/pdf_generator.py
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.units import inch


def _kv_rows(data: dict, keys: list[tuple[str, str]]):
    rows = []
    for label, key in keys:
        val = data.get(key, "")
        rows.append([label, str(val if val is not None else "")])
    return rows


def _table(title: str, rows: list[list[str]]):
    head = Paragraph(f"<b>{title}</b>", getSampleStyleSheet()["Heading4"])
    tbl = Table(rows, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]))
    return [head, Spacer(1, 0.12 * inch), tbl, Spacer(1, 0.18 * inch)]


def build_report_pdf(buf, data: dict):
    doc = SimpleDocTemplate(buf, pagesize=LETTER, title="Daily Report")
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph("<b>Daily Report</b>", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))

    # Motel / Report overview
    overview_rows = [
        ["Motel", data.get("motel_name") or data.get("property_name", "")],
        ["Location", data.get("location") or ""],
        ["Report Date", data.get("report_date") or ""],
        ["Department", data.get("department") or ""],
        ["Auditor", data.get("auditor") or ""],
    ]
    story += _table("Overview", [["Field", "Value"]] + overview_rows)

    # KPIs
    kpi_rows = [
        ["Revenue", data.get("revenue")],
        ["ADR", data.get("adr")],
        ["Occupancy", data.get("occupancy")],
        ["Vacant Clean", data.get("vacant_clean")],
        ["Vacant Dirty", data.get("vacant_dirty")],
        ["Out of Order / Storage Rooms", data.get("out_of_order_storage_rooms")],
    ]
    story += _table("KPIs", [["Metric", "Value"]] + kpi_rows)

    # Child tables (only if present)
    if data.get("comp_rooms"):
        rows = [["Room #", "Notes"]] + [
            [r.get("room_number", ""), r.get("notes", "")]
            for r in data["comp_rooms"]
        ]
        story += _table("Complementary Rooms", rows)

    if data.get("vacant_dirty_rooms"):
        rows = [["Room #", "Reason", "Days", "Action"]] + [
            [r.get("room_number", ""), r.get("reason", ""), r.get("days", ""), r.get("action", "")]
            for r in data["vacant_dirty_rooms"]
        ]
        story += _table("Vacant / Dirty Rooms", rows)

    if data.get("out_of_order_rooms"):
        rows = [["Room #", "Reason", "Days", "Action"]] + [
            [r.get("room_number", ""), r.get("reason", ""), r.get("days", ""), r.get("action", "")]
            for r in data["out_of_order_rooms"]
        ]
        story += _table("Out of Order / Storage", rows)

    if data.get("incidents"):
        rows = [["Description"]] + [[r.get("description", "")] for r in data["incidents"]]
        story += _table("Incidents", rows)

    doc.build(story)

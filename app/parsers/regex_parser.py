import re
from .base_parser import BaseParser

class RegexReportParser(BaseParser):
    def parse(self, text: str, metadata: dict | None = None) -> dict:
        def find(pattern):
            m = re.search(pattern, text, flags=re.IGNORECASE)
            return m.group(1).strip() if m else None

        property_name = find(r"DAILY\s+REPORT\s*(.*?)[\r\n]+") or find(r"(Monticello\s+Inn[^\r\n]*)")
        department = find(r"Department:\s*([^\r\n]+)")
        report_date = find(r"Date\s*([0-9\.\-\/]+)")
        revenue = find(r"Revenue\s*[\r\n]+\s*([\d\.,]+)")
        adr = find(r"ADR\s*[\r\n]+\s*([\d\.,]+)")
        occupancy = find(r"Occupancy\s*[\r\n]+\s*(\d+)")

        return {
            "property_name": property_name,
            "report_date": report_date,
            "department": department,
            "auditor": None,
            "revenue": revenue,
            "adr": adr,
            "occupancy": occupancy,
            "vacant_dirty_rooms": [],
            "out_of_order_rooms": [],
            "comp_rooms": [],
            "incidents": [],
        }

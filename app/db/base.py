# app/db/base.py
from app.repositories.session import Base
from app.db.models import (
    MotelMaster,
    ReportMaster,
    ReportVacantDirtyRoom,
    ReportOutOfOrderRoom,
    ReportCompRoom,
    ReportIncident
)

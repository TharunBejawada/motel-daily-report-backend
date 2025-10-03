from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, func, Text

Base = declarative_base()

# 🏨 Master table for all motels
class MotelMaster(Base):
    __tablename__ = "motel_master"

    id = Column(Integer, primary_key=True, index=True)
    motel_name = Column(String, nullable=False, unique=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # ✅ FIX: back_populates must match the relationship name in ReportMaster
    reports = relationship("ReportMaster", back_populates="motel_master", cascade="all, delete-orphan")


# 📊 Report master table — main daily report record
class ReportMaster(Base):
    __tablename__ = "motel_daily_report"

    id = Column(Integer, primary_key=True, index=True)
    motel_id = Column(Integer, ForeignKey("motel_master.id", ondelete="CASCADE"), nullable=False)

    property_name = Column(String, nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)
    department = Column(String, nullable=True)
    auditor = Column(String, nullable=True)
    revenue = Column(Float, default=0.0)
    adr = Column(Float, default=0.0)
    occupancy = Column(Integer, default=0)
    vacant_clean = Column(Integer, default=0)
    vacant_dirty = Column(Integer, default=0)
    out_of_order_storage_rooms = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    # ✅ FIX: rename relationship here and match MotelMaster
    motel_master = relationship("MotelMaster", back_populates="reports")

    # ✅ FIX: renamed relationships so they don't clash with columns
    vacant_dirty_rooms = relationship("ReportVacantDirtyRoom", back_populates="report", cascade="all, delete-orphan")
    out_of_order_rooms = relationship("ReportOutOfOrderRoom", back_populates="report", cascade="all, delete-orphan")
    comp_room_records = relationship("ReportCompRoom", back_populates="report", cascade="all, delete-orphan")
    incident_records = relationship("ReportIncident", back_populates="report", cascade="all, delete-orphan")


# 🧹 Vacant or dirty rooms
class ReportVacantDirtyRoom(Base):
    __tablename__ = "report_vacant_dirty_room"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("motel_daily_report.id", ondelete="CASCADE"))
    room_number = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    days = Column(Integer, default=0)
    action = Column(Text, nullable=True)

    report = relationship("ReportMaster", back_populates="vacant_dirty_rooms")


# 🔧 Out-of-order rooms
class ReportOutOfOrderRoom(Base):
    __tablename__ = "report_out_of_order_room"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("motel_daily_report.id", ondelete="CASCADE"))
    room_number = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    days = Column(Integer, default=0)
    action = Column(Text, nullable=True)

    report = relationship("ReportMaster", back_populates="out_of_order_rooms")


# 🎁 Complimentary rooms
class ReportCompRoom(Base):
    __tablename__ = "report_comp_room"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("motel_daily_report.id", ondelete="CASCADE"))
    room_number = Column(String, nullable=False)
    notes = Column(Text, nullable=True)

    report = relationship("ReportMaster", back_populates="comp_room_records")


# ⚠️ Guest / staff incidents
class ReportIncident(Base):
    __tablename__ = "report_incident"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("motel_daily_report.id", ondelete="CASCADE"))
    description = Column(Text, nullable=True)

    report = relationship("ReportMaster", back_populates="incident_records")

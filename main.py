import json
import logging
from datetime import datetime
from mangum import Mangum
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.init_db import init_db
from app.api import reports, motels, chat, usage

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Motel Daily Report API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(motels.router, prefix="/motels", tags=["motels"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(usage.router, prefix="/usage", tags=["usage"])

@app.get("/")
def health():
    return {"status": "ok", "message": "Lambda is working"}

mangum_handler = Mangum(app)


def handler(event, context):
    """Main Lambda handler - routes API Gateway and background triggers."""
    logger.info("🚀 Lambda handler invoked")
    logger.info(f"Event received: {json.dumps(event)[:500]}")  # truncate large events

    # ✅ Background Gmail Fetch Trigger
    if isinstance(event, dict) and event.get("action") == "fetch_reports":
        logger.info("📨 Background job detected: fetch_reports")
        job_id = event.get("job_id")
        params = event.get("params", {})

        logger.info(f"🔧 Job ID: {job_id}")
        logger.info(f"🧩 Params: {params}")

        try:
            from app.api.reports import ingest_reports_from_gmail
            from app.repositories.session import get_session
            from app.db.models import ReportJob, JobStatus

            with get_session() as db:
                job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
                if not job:
                    logger.error(f"❌ Job {job_id} not found in database")
                    return {"ok": False, "message": f"Job {job_id} not found"}

                job.status = JobStatus.IN_PROGRESS
                db.commit()
                logger.info(f"🏃‍♂️ Job {job_id} marked as IN_PROGRESS")

            result = ingest_reports_from_gmail(**params)
            logger.info(f"✅ Gmail ingestion complete: {result}")

            with get_session() as db:
                job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.result_summary = result
                db.commit()
                logger.info(f"🏁 Job {job_id} marked as COMPLETED")

            return {"ok": True, "message": "Job completed successfully"}

        except Exception as e:
            logger.exception(f"💥 Job {job_id} failed: {str(e)}")
            from app.repositories.session import get_session
            from app.db.models import ReportJob, JobStatus

            with get_session() as db:
                job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
                if job:
                    job.status = JobStatus.FAILED
                    job.message = str(e)
                    job.completed_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"❌ Job {job_id} marked as FAILED")

            return {"ok": False, "message": f"Job failed: {e}"}

    # ✅ Normal API Gateway Route
    logger.info("🌐 Passing event to Mangum for API Gateway routing")
    return mangum_handler(event, context)


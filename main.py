from mangum import Mangum
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.init_db import init_db
from app.api import reports
from app.api import motels

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

@app.get("/")
def health():
    return {"status": "ok", "message": "Lambda is working"}

handler = Mangum(app)
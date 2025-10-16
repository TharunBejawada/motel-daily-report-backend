from fastapi import APIRouter
from sqlalchemy import func
from app.repositories.session import get_session
from app.db.models import TokenUsage

router = APIRouter(tags=["usage"])

@router.get("/summary")
def get_usage_summary():
    with get_session() as db:
        total_cost = db.query(func.sum(TokenUsage.cost_usd)).scalar() or 0
        total_tokens = db.query(func.sum(TokenUsage.total_tokens)).scalar() or 0
        by_model = db.query(TokenUsage.model, func.sum(TokenUsage.cost_usd))\
                     .group_by(TokenUsage.model).all()

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "by_model": [
                {"model": m, "cost_usd": round(c, 4)} for m, c in by_model
            ]
        }

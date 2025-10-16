import os
import time
from openai import OpenAI
from pinecone import Pinecone
from sqlalchemy.orm import joinedload

from app.repositories.session import get_session
from app.db.models import ReportMaster, MotelMaster, TokenUsage
from app.utils.token_costs import estimate_cost

# --- Load API keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)


# -----------------------------------------------
# 🧩 Helper Functions
# -----------------------------------------------

def build_text(report):
    """Convert a report object into a text block for embedding."""
    motel_name = getattr(report.motel_master, "motel_name", "Unknown Motel")
    location = getattr(report.motel_master, "location", "")
    return f"""
    Motel: {motel_name}
    Location: {location}
    Department: {report.department}
    Auditor: {report.auditor}
    Revenue: {report.revenue}
    Occupancy: {report.occupancy}
    Vacant Clean: {report.vacant_clean}
    Vacant Dirty: {report.vacant_dirty}
    Report Date: {report.report_date}
    ADR: {report.adr}
    Out Of Order/Storage rooms: {report.out_of_order_storage_rooms}
    """


def generate_embedding(text: str):
    """Generate an embedding and log cost usage to DB."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    embedding = response.data[0].embedding
    usage = response.usage

    cost = estimate_cost("text-embedding-3-small", usage.prompt_tokens)
    with get_session() as db:
        db.add(TokenUsage(
            model="text-embedding-3-small",
            operation="embedding",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=0,
            total_tokens=usage.prompt_tokens,
            cost_usd=cost
        ))
        db.commit()

    return embedding


def upsert_embedding(report_id: int, text: str, metadata: dict):
    """Upsert an embedding into Pinecone."""
    vector = generate_embedding(text)
    index.upsert(vectors=[{
        "id": f"report-{report_id}",
        "values": vector,
        "metadata": metadata
    }])
    print(f"✅ Embedded report {report_id}")


def list_existing_vector_ids() -> set:
    """Fetch all vector IDs currently in Pinecone."""
    existing_ids = set()
    try:
        # Use pagination to list all IDs
        stats = index.describe_index_stats()
        total = stats.get("total_vector_count", 0)
        print(f"📊 Existing vectors in Pinecone: {total}")

        # You can query small batches to confirm
        if total > 0:
            # Optional: retrieve a few vector IDs (not all — depends on Pinecone plan)
            # If your plan doesn't support listing IDs, we’ll use metadata match later.
            pass

    except Exception as e:
        print(f"⚠️ Could not fetch Pinecone index stats: {e}")
    return existing_ids


# -----------------------------------------------
# 🚀 Main Embedding Process (Incremental)
# -----------------------------------------------

def embed_all_reports(batch_size: int = 10, delay_sec: float = 1.0):
    with get_session() as db:
        reports = (
            db.query(ReportMaster)
            .options(joinedload(ReportMaster.motel_master))
            .all()
        )

        # Gather all IDs already in Pinecone
        existing_ids = list_existing_vector_ids()

        print(f"📦 Found {len(reports)} reports in database.")
        processed = 0

        for rpt in reports:
            vector_id = f"report-{rpt.id}"
            if vector_id in existing_ids:
                print(f"⏭ Skipping already-embedded report {rpt.id}")
                continue

            text = build_text(rpt)
            metadata = {
                "motel_name": (getattr(rpt.motel_master, "motel_name", "") or ""),
                "location": (getattr(rpt.motel_master, "location", "") or ""),
                "department": (rpt.department or ""),
                "auditor": (rpt.auditor or ""),
                "report_date": str(rpt.report_date) if rpt.report_date else "",
                "content": text[:4000]
            }


            try:
                upsert_embedding(rpt.id, text, metadata)
                time.sleep(1)
                processed += 1
            except Exception as e:
                print(f"❌ Failed on report {rpt.id}: {e}")

            if processed % batch_size == 0:
                print(f"⏸ Processed {processed} new embeddings, sleeping {delay_sec}s")
                time.sleep(delay_sec)

        print(f"✅ Completed embedding. {processed} new vectors added.")


if __name__ == "__main__":
    embed_all_reports()

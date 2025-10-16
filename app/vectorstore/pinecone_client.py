import os, time, uuid
from openai import OpenAI
from pinecone import Pinecone

from app.repositories.session import get_session
from app.db.models import TokenUsage
from app.utils.token_costs import estimate_cost

# Read environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX  = os.getenv("PINECONE_INDEX")

# Initialize clients
client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)

def generate_embedding(text: str):
    """Generate a 1536-dim vector using OpenAI embeddings."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    data = response.data[0]
    usage = response.usage
    cost = estimate_cost("text-embedding-3-small", usage.prompt_tokens)

    # ✅ Log to DB
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
    return response.data[0].embedding

def upsert_report_embedding(report_id: int, text: str, metadata: dict):
    """Generate and upsert a report embedding into Pinecone."""
    try:
        vector = generate_embedding(text)
        index.upsert(vectors=[
            {
                "id": f"report-{report_id}",
                "values": vector,
                "metadata": metadata
            }
        ])
        time.sleep(2)  # allow for propagation
        print(f"✅ Embedded report {report_id} into Pinecone.")
    except Exception as e:
        print(f"❌ Failed to upsert report embedding: {e}")

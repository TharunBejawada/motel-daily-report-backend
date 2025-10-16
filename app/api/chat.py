from fastapi import APIRouter, HTTPException, Query
from openai import OpenAI
from pydantic import BaseModel
from pinecone import Pinecone
import os
import json

router = APIRouter(tags=["chat"])

# --- Load environment variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)


# ✅ Input model for POST body
class ChatRequest(BaseModel):
    question: str
    top_k: int = 3

@router.post("/query")
def chat_query(req: ChatRequest):
    try:

        def detect_aggregation(q: str) -> bool:
            agg_keywords = [
                "average", "total", "sum", "count", "revenue",
                "occupancy", "rate", "highest", "lowest", "overall",
                "percentage", "compare", "trend"
            ]
            return any(k in q.lower() for k in agg_keywords)

        # Adjust retrieval depth dynamically
        top_k = 25
        if detect_aggregation(req.question):
            top_k = 50  # You can safely increase this up to 50 for small datasets

        # --- 1️⃣ Create embedding for user query ---
        query_emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=req.question
        ).data[0].embedding

        # --- 2️⃣ Query Pinecone for relevant reports ---
        results = index.query(vector=query_emb, top_k=req.top_k, include_metadata=True, namespace="", filter={})

        if not results or not results.get("matches"):
            return {"answer": "No relevant reports found."}

        # # --- 3️⃣ Build context from top results ---
        # contexts = [
        #     f"Motel: {m['metadata'].get('motel_name')}, "
        #     f"Department: {m['metadata'].get('department')}, "
        #     f"Auditor: {m['metadata'].get('auditor')}, "
        #     f"Location: {m['metadata'].get('location')}"
        #     for m in results["matches"]
        # ]
        # context_text = "\n".join(contexts)
        contexts = []
        for m in results["matches"]:
            print(m["score"])
            meta = m["metadata"]
            content = meta.get("content", "")
            context = (
                f"Report ID: {meta.get('report_id')}\n"
                f"Motel: {meta.get('motel_name', 'Unknown')} ({meta.get('location', 'Unknown Location')})\n"
                f"Department: {meta.get('department', 'N/A')}\n"
                f"Auditor: {meta.get('auditor', 'N/A')}\n"
                f"Date: {meta.get('report_date', 'N/A')}\n"
                f"Content Summary:\n{content}\n"
                f"---------------------------"
            )
            contexts.append(context)
        context_text = "\n".join(contexts)


        # --- 4️⃣ Ask GPT to summarize ---
        prompt = f"""
        You are a helpful assistant analyzing motel audit reports.

        Context:
        {context_text}

        Question:
        {req.question}

        If the question involves numeric operations such as averages or totals,
        calculate based only on the data in the context. If insufficient data,
        say "Not enough data found."
        Provide a concise and factual answer using only the provided context.
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an analytical report assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.3,
        )

        usage = completion.usage
        if usage:
            from app.repositories.session import get_session
            from app.db.models import TokenUsage
            from app.utils.token_costs import estimate_cost

            cost = estimate_cost("gpt-4o-mini", usage.prompt_tokens, usage.completion_tokens)
            with get_session() as db:
                db.add(TokenUsage(
                    model="gpt-4o-mini",
                    operation="chat",
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    cost_usd=cost
                ))
                db.commit()


        answer = completion.choices[0].message.content.strip()

        # --- 5️⃣ Return structured response ---
        return {
            "question": req.question,
            "answer": answer,
            "context_used": contexts,
            "usage": completion.usage.model_dump() if hasattr(completion, "usage") else None,
            "top_k_used": top_k
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chatbot query failed: {e}")

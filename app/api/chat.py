# from fastapi import APIRouter, HTTPException, Query
# from openai import OpenAI
# from pydantic import BaseModel
# from pinecone import Pinecone
# import os
# import json

# router = APIRouter(tags=["chat"])

# # --- Load environment variables ---
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# PINECONE_INDEX = os.getenv("PINECONE_INDEX")

# client = OpenAI(api_key=OPENAI_API_KEY)
# pc = Pinecone(api_key=PINECONE_API_KEY)
# index = pc.Index(PINECONE_INDEX)


# # ✅ Input model for POST body
# class ChatRequest(BaseModel):
#     question: str
#     top_k: int = 3

# @router.post("/query")
# def chat_query(req: ChatRequest):
#     try:

#         def detect_aggregation(q: str) -> bool:
#             agg_keywords = [
#                 "average", "total", "sum", "count", "revenue",
#                 "occupancy", "rate", "highest", "lowest", "overall",
#                 "percentage", "compare", "trend"
#             ]
#             return any(k in q.lower() for k in agg_keywords)

#         # Adjust retrieval depth dynamically
#         top_k = 25
#         if detect_aggregation(req.question):
#             top_k = 50  # You can safely increase this up to 50 for small datasets

#         # --- 1️⃣ Create embedding for user query ---
#         query_emb = client.embeddings.create(
#             model="text-embedding-3-small",
#             input=req.question
#         ).data[0].embedding

#         # --- 2️⃣ Query Pinecone for relevant reports ---
#         results = index.query(vector=query_emb, top_k=req.top_k, include_metadata=True, namespace="", filter={})

#         if not results or not results.get("matches"):
#             return {"answer": "No relevant reports found."}

#         # # --- 3️⃣ Build context from top results ---
#         # contexts = [
#         #     f"Motel: {m['metadata'].get('motel_name')}, "
#         #     f"Department: {m['metadata'].get('department')}, "
#         #     f"Auditor: {m['metadata'].get('auditor')}, "
#         #     f"Location: {m['metadata'].get('location')}"
#         #     for m in results["matches"]
#         # ]
#         # context_text = "\n".join(contexts)
#         contexts = []
#         for m in results["matches"]:
#             print(m["score"])
#             meta = m["metadata"]
#             content = meta.get("content", "")
#             context = (
#                 f"Report ID: {meta.get('report_id')}\n"
#                 f"Motel: {meta.get('motel_name', 'Unknown')} ({meta.get('location', 'Unknown Location')})\n"
#                 f"Department: {meta.get('department', 'N/A')}\n"
#                 f"Auditor: {meta.get('auditor', 'N/A')}\n"
#                 f"Date: {meta.get('report_date', 'N/A')}\n"
#                 f"Content Summary:\n{content}\n"
#                 f"---------------------------"
#             )
#             contexts.append(context)
#         context_text = "\n".join(contexts)


#         # --- 4️⃣ Ask GPT to summarize ---
#         prompt = f"""
#         You are a helpful assistant analyzing motel audit reports.

#         Context:
#         {context_text}

#         Question:
#         {req.question}

#         If the question involves numeric operations such as averages or totals,
#         calculate based only on the data in the context. If insufficient data,
#         say "Not enough data found."
#         Provide a concise and factual answer using only the provided context.
#         """

#         completion = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are an analytical report assistant."},
#                 {"role": "user", "content": prompt}
#             ],
#             max_tokens=250,
#             temperature=0.3,
#         )

#         usage = completion.usage
#         if usage:
#             from app.repositories.session import get_session
#             from app.db.models import TokenUsage
#             from app.utils.token_costs import estimate_cost

#             cost = estimate_cost("gpt-4o-mini", usage.prompt_tokens, usage.completion_tokens)
#             with get_session() as db:
#                 db.add(TokenUsage(
#                     model="gpt-4o-mini",
#                     operation="chat",
#                     prompt_tokens=usage.prompt_tokens,
#                     completion_tokens=usage.completion_tokens,
#                     total_tokens=usage.total_tokens,
#                     cost_usd=cost
#                 ))
#                 db.commit()


#         answer = completion.choices[0].message.content.strip()

#         # --- 5️⃣ Return structured response ---
#         return {
#             "question": req.question,
#             "answer": answer,
#             "context_used": contexts,
#             "usage": completion.usage.model_dump() if hasattr(completion, "usage") else None,
#             "top_k_used": top_k
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Chatbot query failed: {e}")
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel
from pinecone import Pinecone
from sqlalchemy import func
import os
import re
import logging

from app.repositories.session import get_session
from app.db.models import MotelMaster, ReportMaster, TokenUsage
from app.utils.token_costs import estimate_cost

router = APIRouter(tags=["chat"])

# ---------- ENV CONFIG ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------- REQUEST MODEL ----------
class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


# ---------- 1️⃣ Intent Analyzer ----------
def analyze_intent(question: str) -> str:
    """Use GPT-4o-mini to decide if the query needs SQL, RAG, or Both."""
    try:
        system_prompt = (
            "You are a query router for a motel analytics system. "
            "Decide whether to answer using SQL data (numeric / list) "
            "or contextual knowledge (RAG) or both."
        )
        user_prompt = f"""
        Question: {question}
        Respond with one of: SQL, RAG, BOTH
        - SQL → numeric data, totals, averages, listings, filters
        - RAG → descriptive or reasoning over report text
        - BOTH → mixed (e.g., compare or explain totals)
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        decision = completion.choices[0].message.content.strip().upper()
        if decision not in ["SQL", "RAG", "BOTH"]:
            decision = "RAG"
        logger.info(f"🧭 Intent decision: {decision}")
        return decision
    except Exception as e:
        logger.error(f"Intent analyzer failed: {e}")
        return "RAG"


# ---------- 2️⃣ SQL Processor ----------
def run_sql_query(question: str):
    """Handles total, average, highest, lowest, or list operations."""
    with get_session() as db:
        q = question.lower()

        # ---- Detect metrics ----
        metric = None
        if "revenue" in q:
            metric = "revenue"
        elif "occupancy" in q:
            metric = "occupancy"
        elif "adr" in q or "rate" in q:
            metric = "adr"

        # ---- LIST QUERIES (early exit) ----
        if "list" in q or "show" in q:
            location_match = re.findall(r"in\s+([a-zA-Z\s]+)", q)
            if location_match:
                location = location_match[0].strip()
                motels = (
                    db.query(MotelMaster)
                    .filter(func.lower(MotelMaster.location) == location.lower())
                    .all()
                )
                if not motels:
                    return f"No motels found in {location}."
                names = [m.motel_name for m in motels]
                return f"Motels in {location}: {', '.join(names)}"
            else:
                motels = db.query(MotelMaster).all()
                names = [m.motel_name for m in motels]
                return f"All registered motels: {', '.join(names)}"

        # ---- Metric-based aggregations ----
        motel_match = re.findall(r"of\s+([a-zA-Z\s]+)", q)
        motel_name = motel_match[0].strip() if motel_match else None

        query = db.query(ReportMaster, MotelMaster).join(MotelMaster, ReportMaster.motel_id == MotelMaster.id)
        if motel_name:
            query = query.filter(func.lower(MotelMaster.motel_name) == motel_name.lower())

        reports = query.all()
        if not reports:
            return f"No matching data found for {motel_name or 'query'}."

        # ---- Compute numeric values ----
        values = []
        for r in reports:
            rm = r.ReportMaster
            val = None
            if metric == "revenue":
                val = rm.revenue
            elif metric == "occupancy":
                val = rm.occupancy
            elif metric == "adr":
                val = rm.adr
            if val is not None:
                values.append(val)

        if not values:
            return f"No {metric or 'numeric'} data found."

        total = sum(values)
        avg = total / len(values)
        high = max(values)
        low = min(values)

        if "average" in q:
            return f"The average {metric} for {motel_name or 'all motels'} is {avg:,.2f}."
        elif "highest" in q:
            return f"The highest {metric} recorded is {high:,.2f}."
        elif "lowest" in q:
            return f"The lowest {metric} recorded is {low:,.2f}."
        elif "total" in q or "sum" in q:
            return f"The total {metric} for {motel_name or 'all motels'} is {total:,.2f}."
        else:
            return f"The {metric or 'metric'} for {motel_name or 'all motels'} averages {avg:,.2f}."



# ---------- 3️⃣ RAG Processor ----------
def run_rag_query(question: str, top_k: int = 5):
    """Handles semantic retrieval via Pinecone + GPT."""
    query_emb = client.embeddings.create(
        model="text-embedding-3-small",
        input=question
    ).data[0].embedding

    results = index.query(vector=query_emb, top_k=top_k, include_metadata=True)

    if not results or not results.get("matches"):
        return "No relevant context found."

    contexts = []
    for m in results["matches"]:
        meta = m["metadata"]
        content = meta.get("content", "")
        context = (
            f"Motel: {meta.get('motel_name', 'Unknown')} ({meta.get('location', 'Unknown')})\n"
            f"Department: {meta.get('department', 'N/A')}, Auditor: {meta.get('auditor', 'N/A')}\n"
            f"Date: {meta.get('report_date', 'N/A')}\n"
            f"Content:\n{content}\n"
            f"---------------------------"
        )
        contexts.append(context)

    context_text = "\n".join(contexts)
    prompt = f"""
    You are an analytical assistant specializing in motel audit data.
    Context:
    {context_text}
    Question: {question}
    Provide a concise, factual answer using only the context.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an analytical report assistant."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=250,
        temperature=0.3,
    )

    return completion.choices[0].message.content.strip()


# ---------- 4️⃣ Main Chat Endpoint ----------
@router.post("/query")
def chat_query(req: ChatRequest):
    try:
        intent = analyze_intent(req.question)
        sql_answer = rag_answer = None

        if intent in ["SQL", "BOTH"]:
            sql_answer = run_sql_query(req.question)
        if intent in ["RAG", "BOTH"]:
            rag_answer = run_rag_query(req.question, req.top_k)

        # Combine both if needed
        if intent == "BOTH":
            combined_prompt = f"""
            SQL Data Insight:
            {sql_answer}

            Contextual Summary:
            {rag_answer}

            Please merge both into a single coherent, factual answer.
            """
            merged = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a data analyst combining SQL and contextual insights."},
                    {"role": "user", "content": combined_prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            final_answer = merged.choices[0].message.content.strip()
        else:
            final_answer = sql_answer or rag_answer

        return {
            "question": req.question,
            "answer": final_answer,
            "mode": intent,
            "sql_used": bool(sql_answer),
            "rag_used": bool(rag_answer),
        }

    except Exception as e:
        logger.exception("Chatbot error")
        raise HTTPException(status_code=500, detail=f"Chatbot query failed: {e}")

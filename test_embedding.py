import os, uuid
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

# --- Config ---
openai_key = os.getenv("OPENAI_API_KEY")
pinecone_key = os.getenv("PINECONE_API_KEY")
index_name  = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=openai_key)
pc = Pinecone(api_key=pinecone_key)
index = pc.Index(index_name)

# --- Step 1: create an embedding ---
text = "The Monticello Inn in Framingham had 85% occupancy last week."
print("Creating embedding…")
emb = client.embeddings.create(
    model="text-embedding-3-small",
    input=text
).data[0].embedding
print(f"Embedding length: {len(emb)}")

# --- Step 2: upsert into Pinecone ---
vec_id = str(uuid.uuid4())
index.upsert(vectors=[{"id": vec_id, "values": emb, "metadata": {"text": text}}])
print(f"Inserted vector id={vec_id}")

# ✅ wait a few seconds before querying
import time
time.sleep(3)

# --- Step 3: query a similar sentence ---
query = "Occupancy for Monticello Inn last week"
query_emb = client.embeddings.create(
    model="text-embedding-3-small",
    input=query
).data[0].embedding

results = index.query(vector=query_emb, top_k=3, include_metadata=True)
print("Query results:\n", results)

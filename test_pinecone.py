import os
from dotenv import load_dotenv
from pinecone import Pinecone

# ✅ Load .env file
load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX", "motel-reports")

if not api_key:
    raise ValueError("Missing PINECONE_API_KEY in environment")

pc = Pinecone(api_key=api_key)

print("Indexes:", pc.list_indexes())

index = pc.Index(index_name)
print("Describe:", index.describe_index_stats())

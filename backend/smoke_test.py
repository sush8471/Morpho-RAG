"""
smoke_test.py — quick sanity check that Qdrant is reachable.

Run from the project root (venv activated):
    python backend/smoke_test.py

QDRANT_URL is read from the environment / .env file (default: http://localhost:6333).
If Qdrant is not reachable the script prints a clear message and exits with code 1.
"""
import sys
import time

from config import QDRANT_URL
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

print(f"Connecting to Qdrant at {QDRANT_URL} ...")
try:
    client = QdrantClient(url=QDRANT_URL, timeout=5)
    client.get_collections()          # lightweight health check
except Exception as exc:
    print(
        f"\n[ERROR] Cannot reach Qdrant at {QDRANT_URL}: {exc}\n"
        "  -> Is Docker Desktop running?\n"
        "  -> Is the 'qdrant' container started?  Try:  docker start qdrant\n"
        "  -> Or start a fresh container:\n"
        "       docker run -d --name qdrant -p 6333:6333 -p 6334:6334 "
        "-v qdrant_storage:/qdrant/storage qdrant/qdrant"
    )
    sys.exit(1)

print("1. Creating collection 'smoke_test'...")
try:
    client.create_collection(
        collection_name="smoke_test",
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
except Exception as exc:
    print(f"[WARN] create_collection failed (may already exist): {exc}")

collections = client.get_collections()
print(f"2. Current Collections: {collections}")
print("   -> Open http://localhost:6333/dashboard to view 'smoke_test' under Collections.")

pause_seconds = 5
print(f"3. Pausing {pause_seconds}s before deletion...")
for remaining in range(pause_seconds, 0, -1):
    print(f"   Deleting in {remaining}s...", end="\r", flush=True)
    time.sleep(1)

print("\n4. Deleting collection 'smoke_test'...")
client.delete_collection("smoke_test")

remaining = client.get_collections()
print(f"5. Remaining Collections: {remaining}")
print("Qdrant smoke test passed.")

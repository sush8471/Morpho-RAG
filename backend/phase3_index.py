"""
Phase 3 — Vector Indexing: chunks.jsonl -> Qdrant vector database.

Takes the 160 chunks from data/processed/chunks.jsonl, computes 3072-dimensional
dense embeddings using Google Gemini (gemini-embedding-001 with task_type="RETRIEVAL_DOCUMENT"),
and indexes them into a Qdrant collection ('morpho_rag') with full metadata payloads
and keyword indexes on section_id and chunk type.

Run from the project root (venv activated):
    python backend/phase3_index.py
    python backend/phase3_verify.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add backend directory to sys.path so config imports cleanly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from config import (
    CHUNKS_PATH,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)


def load_chunks(path: Path) -> list[dict]:
    """Load chunks from chunks.jsonl."""
    if not path.is_file():
        raise FileNotFoundError(f"Chunks file not found at: {path}. Run phase2_chunk.py first.")
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


import re

def embed_batch_with_retry(
    client: genai.Client,
    texts: list[str],
    model: str,
    max_retries: int = 5,
) -> list[list[float]]:
    """Embed a list of texts using Gemini API with rate-limit backoff."""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.embed_content(
                model=model,
                contents=texts,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            return [e.values for e in response.embeddings]
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait_sec = 60.0
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
                if match:
                    wait_sec = float(match.group(1)) + 2.0
                print(
                    f"\n[RATE LIMIT] Hit Gemini Free Tier quota (100 embeddings/min). "
                    f"Waiting {wait_sec:.1f}s for quota window to reset (attempt {attempt}/{max_retries})..."
                )
                time.sleep(wait_sec)
            else:
                if attempt == max_retries:
                    print(f"\n[ERROR] Failed to embed batch after {max_retries} attempts: {exc}")
                    raise
                print(f"\n[WARN] Embed attempt {attempt} failed ({exc}). Retrying in 5s...")
                time.sleep(5.0)
    raise RuntimeError(f"Failed to embed batch after {max_retries} attempts")


def index_chunks(batch_size: int = 20, recreate: bool = True) -> None:
    print("=" * 60)
    print("Phase 3 — Indexing chunks into Qdrant")
    print("=" * 60)

    # 1. Load chunks
    chunks = load_chunks(CHUNKS_PATH)
    total_chunks = len(chunks)
    print(f"Loaded {total_chunks} chunks from {CHUNKS_PATH.name}")

    # 2. Connect to Qdrant
    print(f"Connecting to Qdrant at {QDRANT_URL} ...")
    qc = QdrantClient(url=QDRANT_URL)

    # 3. Connect to Gemini
    print(f"Initializing Gemini client with model '{EMBEDDING_MODEL}' (dim {EMBEDDING_DIM}) ...")
    gemini_client = genai.Client(api_key=GOOGLE_API_KEY)

    # 4. Prepare collection
    existing_ids = set()
    if qc.collection_exists(QDRANT_COLLECTION):
        if recreate:
            print(f"Collection '{QDRANT_COLLECTION}' exists. Recreating...")
            qc.delete_collection(QDRANT_COLLECTION)
            qc.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
        else:
            print(f"Collection '{QDRANT_COLLECTION}' already exists. Resuming index...")
            # Query existing point IDs to skip re-embedding
            records, _ = qc.scroll(collection_name=QDRANT_COLLECTION, limit=total_chunks, with_payload=False, with_vectors=False)
            existing_ids = {r.id for r in records}
            print(f"Found {len(existing_ids)} points already indexed. Will only embed missing chunks.")
    else:
        print(f"Creating collection '{QDRANT_COLLECTION}'...")
        qc.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    # 5. Create payload indexes for fast filtering
    print("Configuring payload keyword indexes (section_id, type)...")
    try:
        qc.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name="section_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        qc.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name="type",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # Indexes may already exist if not recreating

    # Filter chunks that need indexing
    chunks_to_index = [
        c for c in chunks
        if int(c["chunk_id"].replace("chk", "")) not in existing_ids
    ]
    print(f"Chunks to index: {len(chunks_to_index)} / {total_chunks}")

    if not chunks_to_index:
        print("All chunks are already indexed!")
        return

    # 6. Batch embed & upsert
    print(f"\nEmbedding and indexing in batches of {batch_size}...")
    total_batches = (len(chunks_to_index) + batch_size - 1) // batch_size
    start_time = time.time()

    for batch_idx in range(total_batches):
        start_i = batch_idx * batch_size
        end_i = min(start_i + batch_size, len(chunks_to_index))
        batch = chunks_to_index[start_i:end_i]

        texts = [c["embed_text"] for c in batch]
        embeddings = embed_batch_with_retry(gemini_client, texts, EMBEDDING_MODEL)

        points = []
        for c, vec in zip(batch, embeddings):
            point_id = int(c["chunk_id"].replace("chk", ""))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=c,
                )
            )

        qc.upsert(collection_name=QDRANT_COLLECTION, points=points)
        print(
            f"  [Batch {batch_idx + 1}/{total_batches}] Indexed {len(points)} chunks "
            f"(IDs {[p.id for p in points[:2]]}...{[p.id for p in points[-1:]]})"
        )

    elapsed = time.time() - start_time
    collection_info = qc.get_collection(QDRANT_COLLECTION)
    indexed_count = collection_info.points_count

    print("\n" + "=" * 60)
    print(f"Phase 3 indexing complete in {elapsed:.1f}s!")
    print(f"  Collection:   {QDRANT_COLLECTION}")
    print(f"  Total points: {indexed_count} (expected {total_chunks})")
    print(f"  Status:       {collection_info.status}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index chunks into Qdrant with Gemini embeddings.")
    parser.add_argument("--batch-size", type=int, default=20, help="Number of chunks per embedding batch.")
    parser.add_argument("--no-recreate", dest="recreate", action="store_false", help="Do not drop and recreate collection.")
    args = parser.parse_args()

    index_chunks(batch_size=args.batch_size, recreate=args.recreate)


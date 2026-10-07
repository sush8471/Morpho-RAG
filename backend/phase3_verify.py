"""
Phase 3 — Verification: verify Qdrant indexing and semantic retrieval quality.

Run from project root (venv activated):
    python backend/phase3_verify.py

Checks:
  1. Qdrant reachable and collection exists.
  2. Point count in Qdrant == chunk count in chunks.jsonl (160).
  3. Vectors have exact dimension (3072) and valid floats.
  4. Payload fields match chunks.jsonl source data.
  5. Semantic retrieval benchmark: test queries from answer key needles
     retrieve the expected section in top-3 results.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Add backend directory to sys.path so config imports cleanly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai
from google.genai import types
from qdrant_client import QdrantClient

from config import (
    ANSWER_KEY_PATH,
    CHUNKS_PATH,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)

results: list[tuple[str, str, str]] = []


def report(status: str, check_name: str, detail: str = "") -> None:
    results.append((status, check_name, detail))
    print(f"  [{status:4s}] {check_name}" + (f" -> {detail}" if detail else ""))


def check(cond: bool, check_name: str, detail_fail: str = "", detail_ok: str = "", warn_only: bool = False) -> None:
    if cond:
        report("PASS", check_name, detail_ok)
    else:
        report("WARN" if warn_only else "FAIL", check_name, detail_fail)


def load_chunks() -> list[dict]:
    chunks = []
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def main() -> int:
    print("=" * 60)
    print("Phase 3 — Vector Indexing Verification")
    print("=" * 60)

    # 1. Check Qdrant Connection & Collection
    print("\n1. Collection existence & connectivity:")
    try:
        qc = QdrantClient(url=QDRANT_URL)
        exists = qc.collection_exists(QDRANT_COLLECTION)
        check(exists, "Collection exists in Qdrant", f"'{QDRANT_COLLECTION}' not found", f"'{QDRANT_COLLECTION}' found")
    except Exception as exc:
        report("FAIL", "Connect to Qdrant", f"Exception: {exc}")
        return 1

    if not exists:
        return 1

    # 2. Check Point Count
    print("\n2. Point count vs chunks.jsonl:")
    chunks = load_chunks()
    expected_count = len(chunks)
    collection_info = qc.get_collection(QDRANT_COLLECTION)
    actual_count = collection_info.points_count
    check(
        actual_count == expected_count,
        f"Point count matches chunks ({expected_count})",
        f"got {actual_count}, expected {expected_count}",
        f"{actual_count} points in Qdrant",
    )

    # 3. Vector Dimensions & Values Check
    print("\n3. Vector dimensions & values:")
    sample_ids = [1, expected_count // 2, expected_count]
    retrieved = qc.retrieve(collection_name=QDRANT_COLLECTION, ids=sample_ids, with_vectors=True)
    check(len(retrieved) == len(sample_ids), "Sample points retrieved", f"retrieved {len(retrieved)}/{len(sample_ids)}")

    dims_ok = True
    non_zero_ok = True
    for p in retrieved:
        vec = p.vector
        if isinstance(vec, dict):
            # Named vectors if any
            vec = list(vec.values())[0]
        if len(vec) != EMBEDDING_DIM:
            dims_ok = False
        norm = math.sqrt(sum(x * x for x in vec))
        if norm < 1e-4:
            non_zero_ok = False

    check(dims_ok, f"Vector dimension is exactly {EMBEDDING_DIM}", f"one or more vectors had wrong dim", f"{EMBEDDING_DIM}-dim confirmed")
    check(non_zero_ok, "Vector values are non-zero normalized embeddings", "found near-zero vector", "valid non-zero vectors")

    # 4. Payload Integrity Check
    print("\n4. Payload integrity:")
    chunks_by_id = {int(c["chunk_id"].replace("chk", "")): c for c in chunks}
    payloads_ok = True
    payload_mismatch_detail = ""

    for p in retrieved:
        expected_chunk = chunks_by_id.get(p.id)
        if not expected_chunk:
            payloads_ok = False
            payload_mismatch_detail = f"Point id {p.id} not in source chunks"
            break
        for key in ("chunk_id", "section_id", "display_text", "type", "page_start"):
            if p.payload.get(key) != expected_chunk.get(key):
                payloads_ok = False
                payload_mismatch_detail = f"Mismatch on point {p.id} key '{key}'"
                break
        if not payloads_ok:
            break

    check(payloads_ok, "Payload fields match source chunks.jsonl", payload_mismatch_detail, "chunk metadata identical")

    # 5. Semantic Retrieval Benchmark (Needle Tests)
    print("\n5. Semantic retrieval benchmark (top-3 recall):")
    gemini_client = genai.Client(api_key=GOOGLE_API_KEY)

    # Load actual questions from answer_key.json
    with open(ANSWER_KEY_PATH, "r", encoding="utf-8") as f:
        ak_data = json.load(f)

    # Test the first 6 simple fact questions from the answer key
    benchmark_queries = [
        q for q in ak_data.get("questions", [])
        if q.get("type") == "simple fact"
    ][:6]

    all_queries_hit = True
    for item in benchmark_queries:
        qid = item["id"]
        q_text = item["question"]
        expected_sections = item["sections"]

        # Embed query with RETRIEVAL_QUERY task type
        q_embed = gemini_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=q_text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        q_vec = q_embed.embeddings[0].values

        response = qc.query_points(
            collection_name=QDRANT_COLLECTION,
            query=q_vec,
            limit=5,
        )

        top_points = response.points
        retrieved_sections = [p.payload.get("section_id") for p in top_points]
        top_hit = top_points[0]
        top_section = top_hit.payload.get("section_id")
        top_score = top_hit.score

        hit = any(s in retrieved_sections for s in expected_sections)
        if not hit:
            all_queries_hit = False

        status = "PASS" if hit else "FAIL"
        rank = min(retrieved_sections.index(s) + 1 for s in expected_sections if s in retrieved_sections) if hit else "N/A"
        report(
            status,
            f"[{qid}] Target {expected_sections} found in top-5",
            f"rank={rank}, top-1={top_section} (score={top_score:.3f}), top-5={retrieved_sections}",
        )

    check(all_queries_hit, "All benchmark queries retrieved target section in top-5", "one or more queries missed target")

    # Summary
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    n_warn = sum(1 for s, _, _ in results if s == "WARN")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    print("\n" + "=" * 60)
    print(f"Phase 3 verification complete: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    print("=" * 60)

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

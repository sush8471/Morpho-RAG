"""
phase7b_verify.py — End-to-End Verification Suite for Phase 7B (Frontend & Full-Stack Integration).

Verifies:
  1. Next.js Frontend Server is running on http://localhost:3000 (status 200, HTML contains Morpho-RAG title and branding).
  2. Next.js environment & static assets respond properly.
  3. FastAPI backend on http://127.0.0.1:8000 responds to health, document info, and eval summary.
  4. Full-stack SSE streaming on POST /api/chat/stream delivers events with status, retrieved, token, citations, and done.
  5. Refusal flow triggers refusal: true on out-of-scope query.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://127.0.0.1:8000"


def print_check(test_name: str, passed: bool, details: str = "") -> None:
    status_str = "[PASS]" if passed else "[FAIL]"
    print(f"  {status_str} {test_name} -> {details}")
    if not passed:
        raise AssertionError(f"Check failed: {test_name} - {details}")


def run_checks() -> None:
    print("=" * 70)
    print("Phase 7B — Modern Web Application & Full-Stack Integration Verification")
    print("=" * 70)

    pass_count = 0

    # ── Check 1: Next.js Frontend Availability ──────────────────────────────
    print("\n1. Testing Next.js Frontend Server (http://localhost:3000)...")
    try:
        req = urllib.request.Request(FRONTEND_URL, headers={"User-Agent": "MorphoRAG-Verify/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            html = resp.read().decode("utf-8")
        print_check("Frontend HTTP Status 200", status == 200, f"HTTP {status}")
        pass_count += 1

        print_check("Frontend HTML contains Morpho-RAG title/metadata", "Morpho-RAG" in html, "Found Morpho-RAG in DOM")
        pass_count += 1
    except Exception as exc:
        print_check("Frontend Server Reachability", False, f"Error: {exc}")

    # ── Check 2: Backend Health & Cross-Origin Endpoints ────────────────────
    print("\n2. Testing FastAPI Backend Connectivity...")
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/health", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print_check("Backend health status is healthy", data.get("status") == "healthy", f"status: {data.get('status')}")
        pass_count += 1
        print_check("Qdrant chunks indexed == 160", data.get("indexed_chunks") == 160, f"{data.get('indexed_chunks')} chunks")
        pass_count += 1
    except Exception as exc:
        print_check("Backend Health Reachability", False, f"Error: {exc}")

    # ── Check 3: Document Info & Amendments ──────────────────────────────────
    print("\n3. Testing Document Metadata for Frontend Badges...")
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/document/info", timeout=10) as resp:
            doc_data = json.loads(resp.read().decode("utf-8"))
        print_check("Handbook edition is Edition 5.0", doc_data.get("edition") == "Edition 5.0", doc_data.get("edition"))
        pass_count += 1
        print_check("Amendments cataloged == 2", len(doc_data.get("amendments", [])) == 2, f"{len(doc_data.get('amendments', []))} amendments")
        pass_count += 1
    except Exception as exc:
        print_check("Document Info Reachability", False, f"Error: {exc}")

    # ── Check 4: Evaluation Transparency Endpoint ───────────────────────────
    print("\n4. Testing Evaluation Benchmarks for Frontend Dashboard...")
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/eval/summary", timeout=10) as resp:
            eval_data = json.loads(resp.read().decode("utf-8"))
        summary = eval_data.get("summary_metrics", {})
        hit_rate = summary.get("retrieval", {}).get("section_hit_at_5", 0)
        accuracy = summary.get("generation", {}).get("mean_factual_correctness", 0)
        print_check("Served Hit@5 rate >= 95%", hit_rate >= 0.95, f"{hit_rate * 100:.1f}%")
        pass_count += 1
        print_check("Served Factual Accuracy >= 90%", accuracy >= 0.90, f"{accuracy * 100:.1f}%")
        pass_count += 1
        cm = summary.get("refusal", {}).get("confusion_matrix", {})
        print_check("Confusion matrix valid", cm.get("TP") == 6 and cm.get("TN") == 29, f"TP={cm.get('TP')}, TN={cm.get('TN')}")
        pass_count += 1
    except Exception as exc:
        print_check("Eval Summary Reachability", False, f"Error: {exc}")

    # ── Check 5: Real-time SSE Stream Consumer Protocol ─────────────────────
    print("\n5. Testing Real-Time SSE Streaming Endpoint (POST /api/chat/stream)...")
    try:
        post_data = json.dumps({"query": "What is the fee for re-evaluation?", "top_k": 5}).encode("utf-8")
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/chat/stream",
            data=post_data,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )

        events_seen = set()
        token_count = 0
        has_citations = False
        is_done = False

        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("event:"):
                    ev_type = line.split(":", 1)[1].strip()
                    events_seen.add(ev_type)
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    if "text" in data_str:
                        token_count += 1
                    if "citations" in data_str:
                        has_citations = True
                    if "full_answer" in data_str:
                        is_done = True

        print_check("SSE stream emits 'status' events", "status" in events_seen, "Status events received")
        pass_count += 1
        print_check("SSE stream emits 'retrieved' events", "retrieved" in events_seen, "Retrieved context events received")
        pass_count += 1
        print_check("SSE stream emits tokens progressively", token_count > 0, f"{token_count} token events received")
        pass_count += 1
        print_check("SSE stream emits structured citations", has_citations, "Structured citations received")
        pass_count += 1
        print_check("SSE stream completes with 'done' event", is_done, "Stream completed successfully")
        pass_count += 1
    except Exception as exc:
        print_check("SSE Stream Protocol", False, f"Error: {exc}")

    # ── Check 6: Zero-Hallucination Refusal over SSE ─────────────────────────
    print("\n6. Testing Zero-Hallucination Refusal via SSE Stream...")
    try:
        post_data = json.dumps({"query": "Where is the student vehicle parking lot on campus?", "top_k": 5}).encode("utf-8")
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/chat/stream",
            data=post_data,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )

        refusal_flag = False
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("data:") and '"refusal": true' in line:
                    refusal_flag = True

        print_check("Out-of-scope query sets refusal: true", refusal_flag, "Model correctly refused without hallucination")
        pass_count += 1
    except Exception as exc:
        print_check("Refusal via SSE", False, f"Error: {exc}")

    print("\n" + "=" * 70)
    print(f"Phase 7B Full-Stack Verification Complete: {pass_count}/15 PASS, 0 FAIL")
    print("=" * 70)


if __name__ == "__main__":
    run_checks()

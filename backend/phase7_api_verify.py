"""
phase7_api_verify.py — Automated verification script for the Morpho-RAG FastAPI endpoints.

Tests:
  1. GET /api/health -> confirms Qdrant status, 160 points indexed, retriever initialized.
  2. GET /api/document/info -> confirms handbook metadata and 2 recorded amendments.
  3. GET /api/eval/summary -> confirms Phase 6 evaluation benchmarks served accurately.
  4. POST /api/chat (factual query) -> confirms grounded answer, section 3.1 citation, 75% answer.
  5. POST /api/chat (unanswerable query) -> confirms refusal handling (refusal=true).

Run from project root:
    backend\\venv\\Scripts\\python.exe backend/phase7_api_verify.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from main import app, startup_event

results: list[tuple[str, str, str]] = []


def report(status: str, check_name: str, detail: str = "") -> None:
    results.append((status, check_name, detail))
    print(f"  [{status:4s}] {check_name}" + (f" -> {detail}" if detail else ""))


def check(cond: bool, check_name: str, detail_fail: str = "", detail_ok: str = "") -> None:
    if cond:
        report("PASS", check_name, detail_ok)
    else:
        report("FAIL", check_name, detail_fail)


def main() -> int:
    print("=" * 70)
    print("Phase 7A — FastAPI Endpoints Verification")
    print("=" * 70)

    # Initialize app state
    startup_event()
    client = TestClient(app)

    # ── Test 1: GET /api/health ───────────────────────────────────────────────
    print("\n1. Testing GET /api/health...")
    resp_health = client.get("/api/health")
    check(resp_health.status_code == 200, "Health check status code 200", f"got {resp_health.status_code}", "status 200 OK")
    data_health = resp_health.json()
    check(data_health.get("status") == "healthy", "Health status is 'healthy'", f"got {data_health.get('status')}", "healthy")
    check(data_health.get("indexed_chunks") == 160, "Qdrant indexed chunks == 160", f"got {data_health.get('indexed_chunks')}", "160 chunks verified")

    # ── Test 2: GET /api/document/info ────────────────────────────────────────
    print("\n2. Testing GET /api/document/info...")
    resp_doc = client.get("/api/document/info")
    check(resp_doc.status_code == 200, "Doc info status code 200", f"got {resp_doc.status_code}", "status 200 OK")
    data_doc = resp_doc.json()
    check(data_doc.get("total_chunks") == 160, "Total chunks == 160", f"got {data_doc.get('total_chunks')}", "160 chunks")
    check(len(data_doc.get("amendments", [])) == 2, "Amendments cataloged == 2", f"got {len(data_doc.get('amendments', []))}", "2 amendments cataloged")

    # ── Test 3: GET /api/eval/summary ─────────────────────────────────────────
    print("\n3. Testing GET /api/eval/summary...")
    resp_eval = client.get("/api/eval/summary")
    check(resp_eval.status_code == 200, "Eval summary status code 200", f"got {resp_eval.status_code}", "status 200 OK")
    data_eval = resp_eval.json()
    hit_5 = data_eval.get("summary_metrics", {}).get("retrieval", {}).get("section_hit_at_5", 0.0)
    fact_score = data_eval.get("summary_metrics", {}).get("generation", {}).get("mean_factual_correctness", 0.0)
    check(hit_5 >= 0.95, "Served evaluation Hit@5 >= 95%", f"got {hit_5 * 100:.1f}%", f"{hit_5 * 100:.1f}% verified")
    check(fact_score >= 0.90, "Served evaluation Factual Accuracy >= 90%", f"got {fact_score * 100:.1f}%", f"{fact_score * 100:.1f}% verified")

    # ── Test 4: POST /api/chat (Answerable Query) ──────────────────────────────
    print("\n4. Testing POST /api/chat with answerable question (Q01: Attendance)...")
    t0 = time.time()
    resp_chat = client.post(
        "/api/chat",
        json={"query": "What is the minimum percentage of scheduled class sessions a student must attend in a course to be eligible for the end-semester examination?"},
    )
    lat_chat = time.time() - t0
    check(resp_chat.status_code == 200, "Chat endpoint status code 200", f"got {resp_chat.status_code}", f"status 200 in {lat_chat:.2f}s")
    data_chat = resp_chat.json()
    ans = data_chat.get("answer", "").lower()
    cits = data_chat.get("citations", [])
    refusal = data_chat.get("refusal", False)

    check("75" in ans and not refusal, "Answer contains '75%' without refusal", f"answer: {ans[:100]}", "Answer correctly states 75%")
    check(any("3.1" in c.get("section_id", "") for c in cits), "Citations include Section 3.1", f"citations: {cits}", f"{len(cits)} citations provided")
    check(len(data_chat.get("retrieved_chunks", [])) == 5, "Retrieved context contains 5 chunks", f"got {len(data_chat.get('retrieved_chunks', []))}", "5 chunks returned")

    # ── Test 5: POST /api/chat (Unanswerable Query) ────────────────────────────
    print("\n5. Testing POST /api/chat with unanswerable question (Parking)...")
    resp_unans = client.post(
        "/api/chat",
        json={"query": "Where on campus may students park their cars, and is a permit required?"},
    )
    check(resp_unans.status_code == 200, "Unanswerable chat status code 200", f"got {resp_unans.status_code}", "status 200 OK")
    data_unans = resp_unans.json()
    unans_refused = data_unans.get("refusal") or "not found" in data_unans.get("answer", "").lower()
    check(unans_refused, "Unanswerable query is explicitly refused", f"got answer: {data_unans.get('answer', '')[:80]}", "Model correctly refused")

    # Summary
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    print("\n" + "=" * 70)
    print(f"Phase 7A API verification complete: {n_pass} PASS, {n_fail} FAIL")
    print("=" * 70)

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

"""
phase4_verify.py — Evaluation and verification of the hybrid retrieval pipeline.

Runs the hybrid retriever (Dense + BM25 + RRF + FlashRank) across all 25 questions
in eval/answer_key.json. Measures:
  - Hit@1: Does the Top-1 chunk come from one of the cited sections?
  - Hit@3: Does a chunk in Top-3 come from one of the cited sections?
  - Hit@5: Does a chunk in Top-5 come from one of the cited sections?
  - MRR: Mean Reciprocal Rank (1 / rank_of_first_relevant_hit).
  - Breakdown by question type (simple fact, table lookup, exception, etc.).

Run from project root (venv activated):
    python backend/phase4_verify.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ANSWER_KEY_PATH
from retriever import HybridRetriever


def main() -> int:
    print("=" * 70)
    print("Phase 4 — Hybrid Retrieval Verification & Benchmark")
    print("=" * 70)

    # 1. Initialize retriever
    print("\nInitializing HybridRetriever (Dense + BM25 + RRF + FlashRank)...")
    start_init = time.time()
    retriever = HybridRetriever()
    print(f"Retriever ready in {time.time() - start_init:.2f}s ({len(retriever.chunks)} chunks indexed)")

    # 2. Load questions from answer_key.json
    with open(ANSWER_KEY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    print(f"Loaded {len(questions)} evaluation questions from {ANSWER_KEY_PATH.name}\n")

    # 3. Benchmark questions
    results_by_type = defaultdict(list)
    all_eval_results = []

    print(f"{'ID':4s} | {'Type':16s} | {'Hit@1':5s} | {'Hit@3':5s} | {'Hit@5':5s} | {'Rank':4s} | {'Expected':12s} | {'Top-1 Sec':9s} | {'Top Score':9s}")
    print("-" * 85)

    for q in questions:
        qid = q["id"]
        q_type = q.get("type", "unknown")
        q_text = q["question"]
        expected_sections = q.get("sections", [])

        # Retrieve top 5
        retrieved_chunks = retriever.retrieve(q_text, top_k=5)
        retrieved_sections = [
            c["payload"].get("section_id") for c in retrieved_chunks
        ]

        # For unanswerable questions, there is no cited section in handbook
        if not expected_sections or q_type.lower() == "unanswerable":
            top_sec = retrieved_sections[0] if retrieved_sections else "None"
            top_score = retrieved_chunks[0].get("rerank_score", 0.0) if retrieved_chunks else 0.0
            print(f"{qid:4s} | {q_type:16s} | {'N/A':5s} | {'N/A':5s} | {'N/A':5s} | {'-':4s} | {'[Refusal]':12s} | {top_sec:9s} | {top_score:9.4f}")
            results_by_type[q_type].append({"qid": qid, "unanswerable": True, "top_score": top_score})
            continue

        # Check hits
        ranks = [
            idx + 1
            for idx, sec in enumerate(retrieved_sections)
            if sec in expected_sections
        ]

        first_rank = ranks[0] if ranks else None
        hit1 = first_rank == 1
        hit3 = first_rank is not None and first_rank <= 3
        hit5 = first_rank is not None and first_rank <= 5
        rr = (1.0 / first_rank) if first_rank else 0.0

        top_sec = retrieved_sections[0] if retrieved_sections else "None"
        top_score = retrieved_chunks[0].get("rerank_score", 0.0) if retrieved_chunks else 0.0

        str_hit1 = "YES" if hit1 else "no"
        str_hit3 = "YES" if hit3 else "no"
        str_hit5 = "YES" if hit5 else "no"
        str_rank = str(first_rank) if first_rank else "-"
        str_exp = str(expected_sections[:2])

        print(f"{qid:4s} | {q_type:16s} | {str_hit1:5s} | {str_hit3:5s} | {str_hit5:5s} | {str_rank:4s} | {str_exp:12s} | {top_sec:9s} | {top_score:9.4f}")

        record = {
            "qid": qid,
            "type": q_type,
            "hit1": hit1,
            "hit3": hit3,
            "hit5": hit5,
            "rr": rr,
            "rank": first_rank,
            "retrieved_sections": retrieved_sections,
            "expected_sections": expected_sections,
        }
        all_eval_results.append(record)
        results_by_type[q_type].append(record)

    # 4. Summary metrics
    print("\n" + "=" * 70)
    print("Summary Metrics by Question Type")
    print("=" * 70)

    for q_type, recs in results_by_type.items():
        eval_recs = [r for r in recs if "unanswerable" not in r]
        if not eval_recs:
            print(f"\n{q_type.upper()} ({len(recs)} questions): Unanswerable / refusal probe questions")
            continue
        n = len(eval_recs)
        h1 = sum(1 for r in eval_recs if r["hit1"]) / n * 100
        h3 = sum(1 for r in eval_recs if r["hit3"]) / n * 100
        h5 = sum(1 for r in eval_recs if r["hit5"]) / n * 100
        mrr = sum(r["rr"] for r in eval_recs) / n
        print(f"\n{q_type.upper()} ({n} questions):")
        print(f"  Hit@1: {h1:5.1f}% | Hit@3: {h3:5.1f}% | Hit@5: {h5:5.1f}% | MRR: {mrr:.3f}")

    # Overall metrics across all answerable questions
    n_total = len(all_eval_results)
    tot_h1 = sum(1 for r in all_eval_results if r["hit1"]) / n_total * 100
    tot_h3 = sum(1 for r in all_eval_results if r["hit3"]) / n_total * 100
    tot_h5 = sum(1 for r in all_eval_results if r["hit5"]) / n_total * 100
    tot_mrr = sum(r["rr"] for r in all_eval_results) / n_total

    print("\n" + "=" * 70)
    print(f"OVERALL PERFORMANCE ({n_total} answerable questions):")
    print(f"  Hit@1: {tot_h1:5.1f}% ({sum(1 for r in all_eval_results if r['hit1'])}/{n_total})")
    print(f"  Hit@3: {tot_h3:5.1f}% ({sum(1 for r in all_eval_results if r['hit3'])}/{n_total})")
    print(f"  Hit@5: {tot_h5:5.1f}% ({sum(1 for r in all_eval_results if r['hit5'])}/{n_total})")
    print(f"  MRR:   {tot_mrr:.3f}")
    print("=" * 70)

    # Verification threshold: Hit@5 must be >= 85%
    if tot_h5 < 85.0:
        print(f"\n[FAIL] Overall Hit@5 {tot_h5:.1f}% below 85.0% threshold")
        return 1

    print(f"\n[PASS] Phase 4 verification passed! Hit@5 is {tot_h5:.1f}%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
phase6_verify.py — Quality verification script for Phase 6 evaluation report.

Asserts that:
  1. eval/eval_report.json exists and contains complete run metadata.
  2. All 30 answerable and 6 unanswerable questions were evaluated (total = 36).
  3. Retrieval Section Hit@5 is >= 90%.
  4. Citation Grounding Rate is 100% (zero hallucinated chunk IDs).
  5. Refusal Recall and Precision are >= 80% on out-of-document queries.
  6. Mean Factual Correctness is >= 80%.
  7. All question types (simple fact, table lookup, multi-section, exception, amendment) have metrics recorded.

Run from project root:
    backend\\venv\\Scripts\\python.exe backend/phase6_verify.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import EVAL_REPORT_PATH

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
    print("Phase 6 — Evaluation Report Quality Verification")
    print("=" * 70)

    # 1. File existence
    check(EVAL_REPORT_PATH.exists(), "eval_report.json exists", f"Not found at {EVAL_REPORT_PATH}", str(EVAL_REPORT_PATH))
    if not EVAL_REPORT_PATH.exists():
        print("[FAIL] Cannot proceed without eval_report.json. Run evaluate.py first.")
        return 1

    with open(EVAL_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("metadata", {})
    summary = data.get("summary_metrics", {})
    breakdown = data.get("category_breakdown", {})
    detailed = data.get("detailed_results", [])

    # 2. Count assertions
    tot_eval = meta.get("total_questions", 0)
    ans_count = meta.get("answerable_count", 0)
    unans_count = meta.get("unanswerable_count", 0)

    check(tot_eval == 36, "Total evaluated questions == 36", f"got {tot_eval}", f"36 questions evaluated")
    check(ans_count == 30, "Answerable questions == 30", f"got {ans_count}", f"30 answerable questions")
    check(unans_count == 6, "Unanswerable questions == 6", f"got {unans_count}", f"6 unanswerable questions")

    # 3. Retrieval Metrics
    retrieval = summary.get("retrieval", {})
    hit_at_5 = retrieval.get("section_hit_at_5", 0.0)
    check(hit_at_5 >= 0.90, "Retrieval Section Hit@5 >= 90%", f"got {hit_at_5 * 100:.1f}%", f"{hit_at_5 * 100:.1f}%")

    sec_recall = retrieval.get("mean_section_recall", 0.0)
    check(sec_recall >= 0.85, "Retrieval Mean Section Recall >= 85%", f"got {sec_recall * 100:.1f}%", f"{sec_recall * 100:.1f}%")

    # 4. Citation Grounding (Zero Hallucinated Citations)
    citations = summary.get("citations", {})
    grounding_rate = citations.get("citation_grounding_rate", 0.0)
    check(grounding_rate >= 0.999, "Citation Grounding Rate == 100% (Zero Hallucinated Chunks)", f"got {grounding_rate * 100:.1f}%", f"{grounding_rate * 100:.1f}%")

    # 5. Refusal Performance
    refusal = summary.get("refusal", {})
    ref_prec = refusal.get("precision", 0.0)
    ref_rec = refusal.get("recall", 0.0)
    ref_f1 = refusal.get("f1_score", 0.0)
    check(ref_prec >= 0.80, "Refusal Precision >= 80%", f"got {ref_prec * 100:.1f}%", f"{ref_prec * 100:.1f}%")
    check(ref_rec >= 0.80, "Refusal Recall >= 80%", f"got {ref_rec * 100:.1f}%", f"{ref_rec * 100:.1f}%")
    check(ref_f1 >= 0.80, "Refusal F1 Score >= 0.80", f"got {ref_f1:.4f}", f"{ref_f1:.4f}")

    # 6. Factual Correctness
    gen = summary.get("generation", {})
    fact_score = gen.get("mean_factual_correctness", 0.0)
    check(fact_score >= 0.80, "Mean Factual Correctness >= 80%", f"got {fact_score * 100:.1f}%", f"{fact_score * 100:.1f}%")

    # 7. Check coverage of all required categories
    expected_categories = {"simple fact", "table lookup", "multi-section", "exception", "amendment", "not in document"}
    present_categories = set(breakdown.keys())
    missing_cats = expected_categories - present_categories
    check(len(missing_cats) == 0, "All question categories evaluated", f"missing: {missing_cats}", f"all {len(expected_categories)} categories present")

    # Summary
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    print("\n" + "=" * 70)
    print(f"Phase 6 verification complete: {n_pass} PASS, {n_fail} FAIL")
    print("=" * 70)

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

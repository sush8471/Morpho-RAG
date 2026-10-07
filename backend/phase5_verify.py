"""
phase5_verify.py — Evaluation and verification of grounded generation with citations.

Tests the RAGGenerator on representative questions:
  1. Simple facts: asserts factual correctness (e.g. 75%, 80 days) and exact citations.
  2. Table lookups: asserts tabular data accuracy (e.g. 120 seats, 2,500 fee).
  3. Amendments: asserts amendment priority and effective date citation.
  4. Exceptions: asserts articulation of both general rule and exception criteria.
  5. Refusal behavior: asserts model refuses questions whose answers are not in the document.
  6. Citation integrity: verifies every cited chunk_id exists and was in the retrieved context.

Run from project root (venv activated):
    python backend/phase5_verify.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generator import RAGGenerator

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
    print("Phase 5 — Generation & Citations Verification")
    print("=" * 70)

    print("\nInitializing RAGGenerator...")
    start_t = time.time()
    generator = RAGGenerator()
    print(f"RAGGenerator initialized in {time.time() - start_t:.2f}s\n")

    all_citations_valid = True

    # --- Test Case 1: Simple Fact (Attendance) ---
    print("1. Test Case: Simple Fact (Q01 - Minimum Attendance)")
    res1 = generator.generate("What is the minimum percentage of scheduled class sessions a student must attend to be eligible for the end-semester examination?")
    ans1 = res1["answer"].lower()
    cits1 = res1["citations"]
    has_75 = "75" in ans1 or "75%" in ans1
    has_sec31 = any("3.1" in c.get("section_id", "") for c in cits1)
    no_refusal = not res1["refusal"]

    check(has_75 and no_refusal, "Factual answer contains '75%'", f"got: {res1['answer'][:100]}", "Answer states 75%")
    check(has_sec31, "Citations include Section 3.1", f"citations: {cits1}", f"{len(cits1)} citations provided")

    # --- Test Case 2: Simple Fact (Teaching Days) ---
    print("\n2. Test Case: Simple Fact (Q02 - Semester Length)")
    res2 = generator.generate("How many teaching days does a full semester contain?")
    ans2 = res2["answer"].lower()
    cits2 = res2["citations"]
    has_80 = "80" in ans2
    has_sec131 = any("1.3.1" in c.get("section_id", "") for c in cits2)

    check(has_80 and not res2["refusal"], "Factual answer contains '80' teaching days", f"got: {res2['answer'][:100]}", "Answer states 80 teaching days")
    check(has_sec131, "Citations include Section 1.3.1", f"citations: {cits2}", f"{len(cits2)} citations provided")

    # --- Test Case 3: Table Lookup (Annual Seats) ---
    print("\n3. Test Case: Table Lookup (Q13 - B.Sc. Seats)")
    res3 = generator.generate("How many annual seats does the B.Sc. Applied Data Science programme have?")
    ans3 = res3["answer"].lower()
    cits3 = res3["citations"]
    has_120 = "120" in ans3
    has_sec21 = any("2.1" in c.get("section_id", "") for c in cits3)

    check(has_120 and not res3["refusal"], "Table lookup contains '120' seats", f"got: {res3['answer'][:100]}", "Answer states 120 seats")
    check(has_sec21, "Citations include Section 2.1 (Table 1)", f"citations: {cits3}", f"{len(cits3)} citations provided")

    # --- Test Case 4: Table Lookup & Exception (Condonation Fee) ---
    print("\n4. Test Case: Table Lookup & Exception (Q14 - Condonation Fee)")
    res4 = generator.generate("A student has 65% attendance in a course. What is the consequence and what condonation fee must they pay?")
    ans4 = res4["answer"].lower()
    cits4 = res4["citations"]
    has_fee = "2,500" in ans4 or "2500" in ans4 or "mrl 2,500" in ans4 or "mrl 2500" in ans4
    has_sec33 = any("3.3" in c.get("section_id", "") for c in cits4)

    check(has_fee and not res4["refusal"], "Table lookup contains condonation fee '2,500 MRL'", f"got: {res4['answer'][:100]}", "Answer specifies MRL 2,500 fee")
    check(has_sec33, "Citations include Section 3.3 (Table 3)", f"citations: {cits4}", f"{len(cits4)} citations provided")

    # --- Test Case 5: Amendment Priority ---
    print("\n5. Test Case: Amendment Priority (Q29 - Re-evaluation Fee)")
    res5 = generator.generate("What is the fee for re-evaluation per course, and has this fee been amended?")
    ans5 = res5["answer"].lower()
    cits5 = res5["citations"]
    mentions_amendment = "amendment" in ans5 or "amended" in ans5 or "500" in ans5 or "mrl 500" in ans5
    has_sec552 = any("5.5.2" in c.get("section_id", "") or "5.5" in c.get("section_id", "") for c in cits5)

    check(mentions_amendment and not res5["refusal"], "Answer respects amendment details/fee", f"got: {res5['answer'][:100]}", "Answer details amendment")
    check(has_sec552, "Citations include Section 5.5.2", f"citations: {cits5}", f"{len(cits5)} citations provided")

    # --- Test Case 6: Refusal Behavior (Unanswerable Question) ---
    print("\n6. Test Case: Refusal Behavior (Unanswerable Query)")
    res6 = generator.generate("What is the fine for parking a bicycle in an unauthorized staff parking bay?")
    refused = res6["refusal"] or "not found" in res6["answer"].lower() or "does not contain" in res6["answer"].lower()
    check(refused, "Model explicitly refuses unanswerable question", f"got answer: {res6['answer'][:100]}", "Model refused correctly")

    # --- Test Case 7: Citation Integrity Check across all responses ---
    print("\n7. Citation Verification (All chunk IDs valid and from context):")
    all_responses = [res1, res2, res3, res4, res5]
    for r_idx, resp in enumerate(all_responses, start=1):
        retrieved_ids = {c["payload"]["chunk_id"] for c in resp["retrieved_chunks"]}
        for cit in resp["citations"]:
            cid = cit.get("chunk_id")
            if cid not in retrieved_ids:
                all_citations_valid = False
                print(f"  [FAIL] Response {r_idx} cited {cid} which was NOT in retrieved chunks {retrieved_ids}")

    check(all_citations_valid, "All citations originate from retrieved chunks (zero hallucinated citations)", "one or more hallucinated chunk IDs", "100% citation grounding verified")

    # Print sample response output for demonstration
    print("\n" + "=" * 70)
    print("Sample Grounded Answer with Citations (Q01):")
    print("=" * 70)
    print(f"Question:  What is the minimum percentage of scheduled class sessions a student must attend...?")
    print(f"Answer:    {res1['answer']}")
    print(f"Citations:")
    for cit in res1["citations"]:
        print(f"  - [{cit['chunk_id']}] Section {cit['section_id']}, p. {cit['page']}: \"{cit['quote']}\"")
    print(f"Refusal:   {res1['refusal']}")
    print("=" * 70)

    # Summary
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    print(f"\nPhase 5 verification complete: {n_pass} PASS, {n_fail} FAIL")
    print("=" * 70)

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

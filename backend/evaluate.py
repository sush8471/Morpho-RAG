"""
evaluate.py — Automated End-to-End Evaluation for Morpho-RAG.

Evaluates the full RAG pipeline across all 30 questions + 6 unanswerable questions
in eval/answer_key.json. Measures:
  1. Retrieval Quality: Section Hit@5 and Section Recall across ground truth sections.
  2. Citation Integrity: Grounding rate (zero hallucinated chunks), quote veracity, and section alignment.
  3. Factual Correctness: Structured LLM-as-a-Judge against authoritative ground-truth answers.
  4. Refusal Performance: Precision, Recall, and F1 on out-of-document questions.
  5. Per-category breakdowns (simple fact, table lookup, multi-section, exception, amendment, not in document).

Outputs comprehensive results to eval/eval_report.json.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    ANSWER_KEY_PATH,
    EVAL_REPORT_PATH,
    FALLBACK_LLM_MODEL,
    GOOGLE_API_KEY,
    LLM_MODEL,
)
from generator import RAGGenerator


class FactualJudgment(BaseModel):
    score: float = Field(
        description="Factual correctness score: 1.0 (Fully Correct), 0.5 (Partially Correct), 0.0 (Incorrect)."
    )
    verdict: str = Field(
        description="Categorical verdict: EXACT_MATCH, CORRECT, PARTIAL, or INCORRECT."
    )
    explanation: str = Field(
        description="Concise rationale explaining factual alignment or discrepancies against ground truth."
    )


JUDGE_SYSTEM_PROMPT = """You are an authoritative, impartial, and strict academic judge evaluating candidate RAG answers against official ground-truth answers from an academic policy handbook.

RUBRIC:
- 1.0 (CORRECT): The candidate answer contains all critical facts, figures, thresholds, conditions, or amendment updates from the ground truth answer without stating contradicting facts. Paraphrasing is fully acceptable as long as facts are exact.
- 0.5 (PARTIAL): The candidate answer captures the primary rule or premise, but misses a secondary condition, a fee detail, an exception rule, or an amendment nuance.
- 0.0 (INCORRECT): The candidate answer contains incorrect facts, contradicts the ground truth, invents rules, or refuses to answer an answerable question.

Assess the candidate response strictly against the reference answer."""


class JudgeEvaluator:
    def __init__(
        self,
        model_name: str = LLM_MODEL,
        fallback_model: str = FALLBACK_LLM_MODEL,
        api_key: str = GOOGLE_API_KEY,
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.fallback_model = fallback_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def evaluate(
        self,
        question: str,
        ground_truth: str,
        candidate_answer: str,
        candidate_refusal: bool,
    ) -> dict[str, Any]:
        """Score candidate answer against ground truth using structured Gemini output."""
        if candidate_refusal:
            return {
                "score": 0.0,
                "verdict": "INCORRECT",
                "explanation": "Model refused an answerable question.",
            }

        prompt = f"""Question:
{question}

Official Reference Ground-Truth Answer:
{ground_truth}

Candidate Model Answer:
{candidate_answer}

Evaluate the candidate answer using the rubric and output score, verdict, and explanation."""

        config = types.GenerateContentConfig(
            system_instruction=JUDGE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=FactualJudgment,
            temperature=0.0,
        )

        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            data = json.loads(resp.text)
        except Exception as exc:
            # Fallback to secondary model
            resp = self.client.models.generate_content(
                model=self.fallback_model,
                contents=prompt,
                config=config,
            )
            data = json.loads(resp.text)

        # Normalize score to 0.0, 0.5, or 1.0
        raw_score = float(data.get("score", 0.0))
        if raw_score >= 0.8:
            score = 1.0
        elif raw_score >= 0.3:
            score = 0.5
        else:
            score = 0.0

        return {
            "score": score,
            "verdict": data.get("verdict", "INCORRECT"),
            "explanation": data.get("explanation", ""),
        }


def section_matches(target_sec: str, candidate_sec: str) -> bool:
    """Check if a candidate section matches a target section or subsection."""
    t = target_sec.strip()
    c = candidate_sec.strip()
    if not t or not c:
        return False
    return (
        t == c
        or c.startswith(t + ".")
        or t.startswith(c + ".")
        or f"section {t}".lower() in c.lower()
    )


class RAGEvaluator:
    def __init__(self) -> None:
        print("[Init] Initializing RAGGenerator and JudgeEvaluator...")
        self.generator = RAGGenerator()
        self.judge = JudgeEvaluator()
        with open(ANSWER_KEY_PATH, "r", encoding="utf-8") as f:
            self.answer_key = json.load(f)

    def evaluate_all(self, delay_sec: float = 0.5) -> dict[str, Any]:
        questions = self.answer_key.get("questions", [])
        unanswerable = self.answer_key.get("unanswerable_questions", [])

        print(f"\nLoaded {len(questions)} answerable questions and {len(unanswerable)} unanswerable questions.")
        print("=" * 80)
        print(f"{'ID':4s} | {'Type':16s} | {'Hit@5':5s} | {'SecRec':6s} | {'FactScore':9s} | {'Refused':7s} | {'Latency':7s}")
        print("-" * 80)

        detailed_results: list[dict[str, Any]] = []

        # ── 1. Evaluate 30 Answerable Questions ─────────────────────────────
        for q in questions:
            qid = q["id"]
            qtype = q["type"]
            query = q["question"]
            gt_answer = q["answer"]
            gt_sections = [str(s) for s in q.get("sections", [])]

            t0 = time.time()
            gen_res = self.generator.generate(query, top_k=5)
            latency = time.time() - t0

            answer = gen_res["answer"]
            citations = gen_res["citations"]
            refusal = gen_res["refusal"]
            retrieved_chunks = gen_res["retrieved_chunks"]

            # Retrieval section evaluation
            retrieved_secs = [c["payload"].get("section_id", "") for c in retrieved_chunks]
            retrieved_ids = {c["payload"].get("chunk_id", "") for c in retrieved_chunks}

            hit_count = 0
            for gt_sec in gt_sections:
                if any(section_matches(gt_sec, r_sec) for r_sec in retrieved_secs):
                    hit_count += 1

            hit_at_5 = 1.0 if hit_count > 0 else 0.0
            section_recall = (hit_count / len(gt_sections)) if gt_sections else 1.0

            # Citation grounding & veracity evaluation
            valid_citations = 0
            grounded_chunks = 0
            verbatim_quotes = 0
            for cit in citations:
                cid = cit.get("chunk_id", "")
                if cid in retrieved_ids:
                    grounded_chunks += 1

                # Check quote veracity
                quote = cit.get("quote", "").strip().lower()
                chunk_obj = next((c for c in retrieved_chunks if c["payload"].get("chunk_id") == cid), None)
                if chunk_obj:
                    chunk_text = (chunk_obj["payload"].get("embed_text", "") + " " + chunk_obj["payload"].get("display_text", "")).lower()
                    if quote and (quote in chunk_text or any(part in chunk_text for part in quote.split(". ") if len(part) > 10)):
                        verbatim_quotes += 1

                c_sec = str(cit.get("section_id", ""))
                if any(section_matches(gt_sec, c_sec) for gt_sec in gt_sections):
                    valid_citations += 1

            total_cits = len(citations)
            cit_grounding_rate = (grounded_chunks / total_cits) if total_cits > 0 else 1.0
            cit_veracity_rate = (verbatim_quotes / total_cits) if total_cits > 0 else 1.0
            cit_section_match_rate = (valid_citations / total_cits) if total_cits > 0 else 0.0

            # LLM-as-a-Judge Factual evaluation
            judgment = self.judge.evaluate(
                question=query,
                ground_truth=gt_answer,
                candidate_answer=answer,
                candidate_refusal=refusal,
            )

            record = {
                "id": qid,
                "type": qtype,
                "question": query,
                "ground_truth_answer": gt_answer,
                "ground_truth_sections": gt_sections,
                "candidate_answer": answer,
                "citations": citations,
                "refusal": refusal,
                "model_used": gen_res.get("model_used", ""),
                "latency_sec": round(latency, 2),
                "retrieval": {
                    "hit_at_5": hit_at_5,
                    "section_recall": round(section_recall, 3),
                    "retrieved_sections": retrieved_secs,
                },
                "citations_eval": {
                    "count": total_cits,
                    "grounding_rate": round(cit_grounding_rate, 3),
                    "veracity_rate": round(cit_veracity_rate, 3),
                    "section_match_rate": round(cit_section_match_rate, 3),
                },
                "factual_correctness": {
                    "score": judgment["score"],
                    "verdict": judgment["verdict"],
                    "explanation": judgment["explanation"],
                },
            }
            detailed_results.append(record)

            print(
                f"{qid:4s} | {qtype:16s} | {hit_at_5:5.1f} | {section_recall:6.2f} | "
                f"{judgment['score']:9.1f} | {str(refusal):7s} | {latency:6.2f}s"
            )

            if delay_sec > 0:
                time.sleep(delay_sec)

        # ── 2. Evaluate 6 Unanswerable Questions ───────────────────────────
        print("-" * 80)
        print("Evaluating 6 Unanswerable Questions (Refusal Precision)...")
        print("-" * 80)

        for u in unanswerable:
            uid = u["id"]
            utype = u["type"]
            uquery = u["question"]
            expected = u["expected_response"]

            t0 = time.time()
            gen_res = self.generator.generate(uquery, top_k=5)
            latency = time.time() - t0

            answer = gen_res["answer"]
            citations = gen_res["citations"]
            explicit_refusal = gen_res["refusal"]
            ans_lower = answer.lower()
            text_refused = "not found" in ans_lower or "does not contain" in ans_lower or "no information" in ans_lower
            refused = explicit_refusal or text_refused

            record = {
                "id": uid,
                "type": utype,
                "question": uquery,
                "ground_truth_answer": expected,
                "ground_truth_sections": [],
                "candidate_answer": answer,
                "citations": citations,
                "refusal": explicit_refusal,
                "effective_refusal": refused,
                "model_used": gen_res.get("model_used", ""),
                "latency_sec": round(latency, 2),
                "factual_correctness": {
                    "score": 1.0 if refused else 0.0,
                    "verdict": "REFUSED_CORRECTLY" if refused else "HALLUCINATED_ANSWER",
                    "explanation": "Correctly refused unanswerable question." if refused else "Failed to refuse unanswerable question.",
                },
            }
            detailed_results.append(record)

            print(
                f"{uid:4s} | {utype:16s} | {'N/A':5s} | {'N/A':6s} | "
                f"{(1.0 if refused else 0.0):9.1f} | {str(refused):7s} | {latency:6.2f}s"
            )

            if delay_sec > 0:
                time.sleep(delay_sec)

        # ── 3. Aggregate Overall Metrics ───────────────────────────────────
        answerable_records = [r for r in detailed_results if r["type"] != "not in document"]
        unanswerable_records = [r for r in detailed_results if r["type"] == "not in document"]

        n_ans = len(answerable_records)
        n_unans = len(unanswerable_records)

        # Retrieval aggregates
        avg_hit_5 = sum(r["retrieval"]["hit_at_5"] for r in answerable_records) / n_ans if n_ans else 0.0
        avg_sec_recall = sum(r["retrieval"]["section_recall"] for r in answerable_records) / n_ans if n_ans else 0.0

        # Factual correctness aggregates
        fact_scores = [r["factual_correctness"]["score"] for r in answerable_records]
        avg_fact_score = sum(fact_scores) / n_ans if n_ans else 0.0
        verdicts = {}
        for r in answerable_records:
            v = r["factual_correctness"]["verdict"]
            verdicts[v] = verdicts.get(v, 0) + 1

        # Citation aggregates
        all_cit_counts = sum(r["citations_eval"]["count"] for r in answerable_records)
        all_grounded = sum(r["citations_eval"]["grounding_rate"] * r["citations_eval"]["count"] for r in answerable_records)
        all_veracity = sum(r["citations_eval"]["veracity_rate"] * r["citations_eval"]["count"] for r in answerable_records)
        citation_grounding_rate = (all_grounded / all_cit_counts) if all_cit_counts else 1.0
        citation_veracity_rate = (all_veracity / all_cit_counts) if all_cit_counts else 1.0

        # Refusal Confusion Matrix
        # TP: unanswerable correctly refused
        tp = sum(1 for r in unanswerable_records if r.get("effective_refusal", False))
        # FN: unanswerable mistakenly answered
        fn = sum(1 for r in unanswerable_records if not r.get("effective_refusal", False))
        # FP: answerable mistakenly refused
        fp = sum(1 for r in answerable_records if r.get("refusal", False))
        # TN: answerable correctly answered
        tn = sum(1 for r in answerable_records if not r.get("refusal", False))

        refusal_precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        refusal_recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        refusal_f1 = (2 * refusal_precision * refusal_recall / (refusal_precision + refusal_recall)) if (refusal_precision + refusal_recall) > 0 else 0.0

        # Per-Category Breakdown
        category_breakdown: dict[str, dict[str, Any]] = {}
        distinct_types = sorted(list({r["type"] for r in detailed_results}))
        for cat in distinct_types:
            cat_recs = [r for r in detailed_results if r["type"] == cat]
            c_count = len(cat_recs)
            if cat == "not in document":
                c_refused = sum(1 for r in cat_recs if r.get("effective_refusal", False))
                category_breakdown[cat] = {
                    "count": c_count,
                    "refusal_rate": round(c_refused / c_count, 3),
                    "factual_score": round(c_refused / c_count, 3),
                }
            else:
                c_hit = sum(r["retrieval"]["hit_at_5"] for r in cat_recs) / c_count
                c_recall = sum(r["retrieval"]["section_recall"] for r in cat_recs) / c_count
                c_score = sum(r["factual_correctness"]["score"] for r in cat_recs) / c_count
                category_breakdown[cat] = {
                    "count": c_count,
                    "hit_at_5": round(c_hit, 3),
                    "section_recall": round(c_recall, 3),
                    "factual_correctness": round(c_score, 3),
                }

        # Full Report Object
        eval_report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "llm_model": self.generator.model_name,
                "judge_model": self.judge.model_name,
                "total_questions": len(detailed_results),
                "answerable_count": n_ans,
                "unanswerable_count": n_unans,
            },
            "summary_metrics": {
                "retrieval": {
                    "section_hit_at_5": round(avg_hit_5, 4),
                    "mean_section_recall": round(avg_sec_recall, 4),
                },
                "generation": {
                    "mean_factual_correctness": round(avg_fact_score, 4),
                    "exact_or_correct_pct": round(verdicts.get("CORRECT", 0) / n_ans, 4) if n_ans else 0.0,
                    "verdict_distribution": verdicts,
                },
                "citations": {
                    "total_citations_evaluated": all_cit_counts,
                    "citation_grounding_rate": round(citation_grounding_rate, 4),
                    "quote_veracity_rate": round(citation_veracity_rate, 4),
                },
                "refusal": {
                    "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
                    "precision": round(refusal_precision, 4),
                    "recall": round(refusal_recall, 4),
                    "f1_score": round(refusal_f1, 4),
                },
            },
            "category_breakdown": category_breakdown,
            "detailed_results": detailed_results,
        }

        # ── 4. Save to eval/eval_report.json ────────────────────────────────
        with open(EVAL_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(eval_report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 80)
        print("PHASE 6 EVALUATION SUMMARY REPORT")
        print("=" * 80)
        print(f"Total Evaluated:          {len(detailed_results)} (30 Answerable, 6 Unanswerable)")
        print(f"Retrieval Section Hit@5:  {avg_hit_5 * 100:.1f}%")
        print(f"Retrieval Section Recall: {avg_sec_recall * 100:.1f}%")
        print(f"Mean Factual Score:       {avg_fact_score * 100:.1f}%")
        print(f"Verdict Counts:           {verdicts}")
        print(f"Citation Grounding:       {citation_grounding_rate * 100:.1f}% (zero hallucinated chunks)")
        print(f"Citation Quote Veracity:  {citation_veracity_rate * 100:.1f}%")
        print(f"Refusal Precision:        {refusal_precision * 100:.1f}%")
        print(f"Refusal Recall:           {refusal_recall * 100:.1f}%")
        print(f"Refusal F1:               {refusal_f1:.4f}")
        print("\nBreakdown by Question Type:")
        for cat, c_data in category_breakdown.items():
            print(f"  - {cat:16s} (n={c_data['count']}): {c_data}")
        print("=" * 80)
        print(f"Full report saved to: {EVAL_REPORT_PATH}")

        return eval_report


def main() -> int:
    evaluator = RAGEvaluator()
    evaluator.evaluate_all(delay_sec=0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())

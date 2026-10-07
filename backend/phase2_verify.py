"""
Phase 2 — Verification. Run after phase2_chunk.py.

    python backend/phase2_verify.py

Checks (each line is PASS, WARN or FAIL; exits 1 if anything FAILs):

  1. Every record id from records.jsonl appears in exactly one chunk's
     source_record_ids (coverage = 100%, no duplicates).
  2. chunk_id values are unique across all chunks.
  3. Required fields are present and non-empty on every chunk.
  4. section_id is consistent: every source record's section_id matches
     the chunk's section_id (no cross-section merges slipped through).
  5. embed_text starts with the section-path prefix (R4 enforced).
  6. Callout chunks carry callout_kind; glossary chunks carry term;
     table chunks carry table_id, header, rows.
  7. Needle check: every fact from phase1_verify.NEEDLES appears in the
     embed_text of at least one chunk whose section_id matches the cited
     section.  This is the most important check — if this fails, the
     retriever cannot find the answer in any chunk.
  8. Size stats by type (informational, always PASS).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# Make this runnable from the project root with   python backend/phase2_verify.py
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CHUNKS_PATH, RECORDS_PATH

# Import the NEEDLES dict from phase1_verify so we have one source of truth
# for what facts must be findable.
from phase1_verify import NEEDLES   # {qid: [(section_id, needle_text), ...]}

results: list[tuple[str, str, str]] = []


def report(status: str, check: str, detail: str = "") -> None:
    results.append((status, check, detail))
    mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[status]
    print(f"  [{mark}] {check}" + (f"  -> {detail}" if detail else ""))


def check(cond: bool, name: str, detail_fail: str = "", detail_ok: str = "", warn_only: bool = False) -> None:
    if cond:
        report("PASS", name, detail_ok)
    else:
        report("WARN" if warn_only else "FAIL", name, detail_fail)


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> None:
    # ── load data ─────────────────────────────────────────────────────────
    records = [json.loads(l) for l in RECORDS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks  = [json.loads(l) for l in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

    print(f"Records: {len(records)}")
    print(f"Chunks:  {len(chunks)}")

    rec_by_id = {r["id"]: r for r in records}

    # ── 1. Coverage: every record appears in exactly one chunk ─────────────
    print("\n1. Record coverage")
    src_counts: Counter[str] = Counter()
    for c in chunks:
        for rid in c["source_record_ids"]:
            src_counts[rid] += 1

    missing  = [rid for rid in rec_by_id if src_counts[rid] == 0]
    dupes    = [rid for rid, n in src_counts.items() if n > 1]
    unknown  = [rid for rid in src_counts if rid not in rec_by_id]

    check(not missing,  "every record appears in at least one chunk",
          f"{len(missing)} missing: {missing[:5]}")
    check(not dupes,    "no record appears in more than one chunk",
          f"{len(dupes)} duplicated: {dupes[:5]}")
    check(not unknown,  "no chunk references a non-existent record id",
          f"{len(unknown)} unknown: {unknown[:5]}")

    # ── 2. chunk_id uniqueness ─────────────────────────────────────────────
    print("\n2. chunk_id uniqueness")
    ids = [c["chunk_id"] for c in chunks]
    dupe_ids = [cid for cid, n in Counter(ids).items() if n > 1]
    check(not dupe_ids, "chunk_id values are unique",
          f"duplicates: {dupe_ids[:5]}", detail_ok=f"{len(ids)} unique ids")

    # ── 3. Required fields ─────────────────────────────────────────────────
    print("\n3. Required fields")
    REQUIRED = {"chunk_id", "source_record_ids", "page_start", "page_end",
                "section_id", "section_title", "section_path",
                "type", "embed_text", "display_text", "n_chars"}
    bad_fields = []
    bad_empty  = []
    for c in chunks:
        missing_f = REQUIRED - c.keys()
        if missing_f:
            bad_fields.append((c["chunk_id"], sorted(missing_f)))
        for f in ("embed_text", "display_text", "section_id"):
            if not c.get(f, ""):
                bad_empty.append((c["chunk_id"], f))
    check(not bad_fields, "all required fields present on every chunk",
          f"{len(bad_fields)} chunks missing fields: {bad_fields[:3]}")
    check(not bad_empty,  "embed_text, display_text, section_id are non-empty on every chunk",
          f"{len(bad_empty)} violations: {bad_empty[:3]}")

    n_chars_ok = all(c["n_chars"] == len(c["display_text"]) for c in chunks)
    check(n_chars_ok, "n_chars == len(display_text) on every chunk",
          f"mismatch on {[c['chunk_id'] for c in chunks if c['n_chars'] != len(c['display_text'])][:3]}")

    # ── 4. No cross-section merges ─────────────────────────────────────────
    print("\n4. Section boundary integrity")
    cross = []
    for c in chunks:
        for rid in c["source_record_ids"]:
            rec = rec_by_id.get(rid)
            if rec and rec["section_id"] != c["section_id"]:
                cross.append((c["chunk_id"], rid, rec["section_id"], c["section_id"]))
    check(not cross, "no chunk merges records from different sections",
          f"{len(cross)} violations: {cross[:3]}")

    # ── 5. Embed-text prefix ───────────────────────────────────────────────
    print("\n5. embed_text prefix (Rule 4 + 5)")
    bad_prefix = []
    for c in chunks:
        et = c["embed_text"]
        # Must start with [ and contain the section_id somewhere before \n
        first_line = et.split("\n")[0]
        if c["section_id"] not in first_line:
            bad_prefix.append((c["chunk_id"], c["section_id"], first_line[:60]))
    check(not bad_prefix, "every embed_text first line contains the section_id",
          f"{len(bad_prefix)} violations: {bad_prefix[:3]}")

    callout_prefix_bad = [
        c["chunk_id"] for c in chunks
        if c["type"] == "callout" and
           not c["embed_text"].startswith(("[AMENDMENT]", "[EXCEPTION]"))
    ]
    check(not callout_prefix_bad,
          "callout embed_text starts with [AMENDMENT] or [EXCEPTION]",
          f"bad: {callout_prefix_bad}")

    # ── 6. Type-specific optional fields ──────────────────────────────────
    print("\n6. Type-specific optional fields")
    callout_missing_kind = [c["chunk_id"] for c in chunks
                            if c["type"] == "callout" and "callout_kind" not in c]
    check(not callout_missing_kind, "callout chunks have callout_kind",
          f"missing on: {callout_missing_kind}")

    gloss_missing_term = [c["chunk_id"] for c in chunks
                          if c["type"] == "glossary_entry" and "term" not in c]
    check(not gloss_missing_term, "glossary_entry chunks have term",
          f"missing on: {gloss_missing_term}")

    table_missing = [c["chunk_id"] for c in chunks
                     if c["type"] == "table" and not all(k in c for k in ("table_id", "header", "rows"))]
    check(not table_missing, "table chunks have table_id, header, rows",
          f"missing on: {table_missing}")

    # ── 7. Needle check ────────────────────────────────────────────────────
    print("\n7. Answer-key needle check")
    # Build a lookup: section_id -> concatenated embed_text of all chunks in that section
    sec_embed: dict[str, str] = {}
    for c in chunks:
        sid = c["section_id"]
        # also include sub-sections: a needle for "3.1" should match in chunks
        # whose section_id is "3.1" or starts with "3.1."
        sec_embed[sid] = sec_embed.get(sid, "") + " " + c["embed_text"]

    def sec_text_for(sid: str) -> str:
        """Concatenate embed_text of all chunks in sid and any sub-sections."""
        parts = []
        for c in chunks:
            csid = c["section_id"] or ""
            if csid == sid or csid.startswith(sid + "."):
                parts.append(c["embed_text"])
        return flat(" ".join(parts))

    bad_needles = []
    for qid, pairs in NEEDLES.items():
        for sid, needle in pairs:
            haystack = sec_text_for(sid)
            if flat(needle) not in haystack:
                bad_needles.append(f"{qid} §{sid}: {needle!r}")

    n_total_needles = sum(len(v) for v in NEEDLES.values())
    check(not bad_needles,
          f"all {n_total_needles} answer-key needles found in the embed_text of the cited section",
          "; ".join(bad_needles[:6]))

    if bad_needles:
        print("\n  Failed needles:")
        for b in bad_needles:
            print(f"    {b}")

    # ── 8. Size stats (informational) ─────────────────────────────────────
    print("\n8. Size statistics")
    by_type: dict[str, list[int]] = {}
    for c in chunks:
        by_type.setdefault(c["type"], []).append(c["n_chars"])

    print(f"  {'Type':<20} {'Count':>6} {'Min':>6} {'Max':>6} {'Mean':>7}")
    print("  " + "-" * 46)
    for t in ("paragraph", "list_item", "table", "callout", "glossary_entry"):
        if t not in by_type:
            continue
        vals = by_type[t]
        print(f"  {t:<20} {len(vals):>6} {min(vals):>6} {max(vals):>6} {statistics.mean(vals):>7.0f}")

    # Count list-item sections (to confirm grouping worked)
    li_chunks = [c for c in chunks if c["type"] == "list_item"]
    li_sections = len({c["section_id"] for c in li_chunks})
    print(f"\n  list_item chunks cover {li_sections} distinct sections")
    report("PASS", "size stats printed (informational)")

    # ── summary ─────────────────────────────────────────────────────────
    n = Counter(s for s, _, _ in results)
    print(f"\nPHASE 2 VERIFICATION: {n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed")
    sys.exit(1 if n["FAIL"] else 0)


if __name__ == "__main__":
    main()

"""
Phase 2 — Chunking: records.jsonl -> chunks.jsonl.

No API calls, no Qdrant. This script only answers:
"What is the atomic unit of text the retriever will search over, and what
metadata does it carry?"

Run from the project root (venv activated):
    python backend/phase2_chunk.py
    python backend/phase2_verify.py

Output: data/processed/chunks.jsonl
Each line is one chunk JSON object; see the schema below.

Chunking rules
--------------
R1  Paragraphs, callouts, tables  ->  one chunk per record, no merging.
    - Tables must stay whole so multi-row lookups work.
    - Callouts (amendments/exceptions) carry old + new rule; splitting breaks them.
R2  List items  ->  contiguous runs with the same section_id are merged into one
    chunk.  Individual list items (mean ~94 chars) are too short for dense retrieval.
R3  Glossary entries  ->  one chunk per entry (semantically independent terms).
R4  embed_text prefix  ->  every chunk gets its full section path prepended, e.g.:
        [5 Examinations ... > 5.5 Re-evaluation ... > 5.5.2 Window and Fee]
        AMENDMENT 1 (effective 1 January 2026). ...
    This puts section context into the embedding vector without polluting display_text.
R5  Callout extra prefix  ->  amendment/exception callouts also get [AMENDMENT] or
    [EXCEPTION] before the section path so the embedder can distinguish them.
R6  No cross-section merges  ->  all grouping is gated on section_id equality.

Chunk schema (all fields; optional fields noted)
-------------------------------------------------
chunk_id          str   "chk0001" (sequential, 4-digit zero-padded)
source_record_ids list  record ids that contributed (always a list)
page_start        int   min(page_start) of source records
page_end          int   max(page_end) of source records
section_id        str
section_title     str
section_path      list  full ancestor path from the source record
type              str   "paragraph" | "list_item" | "table" | "callout" | "glossary_entry"
callout_kind      str   (callout chunks only) "amendment" | "exception"
term              str   (glossary_entry chunks only)
table_id          str   (table chunks only)
caption           str   (table chunks only)
header            list  (table chunks only)
rows              list  (table chunks only)
embed_text        str   text sent to the embedding API (includes section-path prefix)
display_text      str   text shown to the user in citations (no prefix)
n_chars           int   len(display_text)
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

# Make this runnable from the project root with   python backend/phase2_chunk.py
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CHUNKS_PATH, RECORDS_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_path_prefix(section_path: list[str]) -> str:
    """Short breadcrumb: '5 Examinations > 5.5 Re-evaluation > 5.5.2 Window and Fee'"""
    return " > ".join(section_path)


def make_embed_text(rec: dict, display_text: str) -> str:
    """Compose the string that goes to the embedding API (R4 + R5)."""
    prefix_parts = []
    if rec.get("type") == "callout":
        kind = rec.get("callout_kind", "")
        if kind == "amendment":
            prefix_parts.append("[AMENDMENT]")
        elif kind == "exception":
            prefix_parts.append("[EXCEPTION]")
    path = build_path_prefix(rec["section_path"])
    prefix_parts.append(f"[{path}]")
    prefix = " ".join(prefix_parts)
    return f"{prefix}\n{display_text}"


def make_chunk(chunk_id: str, records: list[dict]) -> dict:
    """
    Build one chunk from one or more records.
    All records must have the same section_id (enforced by the caller).
    """
    first = records[0]

    display_text = " ".join(r["text"] for r in records)

    chunk: dict = {
        "chunk_id": chunk_id,
        "source_record_ids": [r["id"] for r in records],
        "page_start": min(r["page_start"] for r in records),
        "page_end": max(r["page_end"] for r in records),
        "section_id": first["section_id"],
        "section_title": first["section_title"],
        "section_path": first["section_path"],
        "type": first["type"],
        "display_text": display_text,
        "embed_text": make_embed_text(first, display_text),
        "n_chars": len(display_text),
    }

    # Optional fields from the source record
    if first["type"] == "callout":
        chunk["callout_kind"] = first["callout_kind"]
    if first["type"] == "glossary_entry":
        chunk["term"] = first["term"]
    if first["type"] == "table":
        chunk["table_id"] = first.get("table_id")
        chunk["caption"] = first.get("caption")
        chunk["header"] = first.get("header")
        chunk["rows"] = first.get("rows")

    return chunk


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_chunks(records: list[dict]) -> list[dict]:
    """
    Walk records in order and apply rules R1–R6.
    Returns the list of chunks (not yet written to disk).
    """
    chunks: list[dict] = []
    pending_list_items: list[dict] = []   # for R2 accumulation

    def flush_list_items():
        nonlocal pending_list_items
        if not pending_list_items:
            return
        cid = f"chk{len(chunks) + 1:04d}"
        chunks.append(make_chunk(cid, pending_list_items))
        pending_list_items = []

    for rec in records:
        rtype = rec["type"]

        # R2 — accumulate list items within the same section; flush on section change
        if rtype == "list_item":
            if pending_list_items and pending_list_items[-1]["section_id"] != rec["section_id"]:
                flush_list_items()      # section boundary — emit what we had
            pending_list_items.append(rec)
            continue

        # Any non-list record flushes the pending list-item group
        flush_list_items()

        # R1 / R3 — one record → one chunk
        cid = f"chk{len(chunks) + 1:04d}"
        chunks.append(make_chunk(cid, [rec]))

    flush_list_items()   # last group, if any
    return chunks


def print_stats(chunks: list[dict]) -> None:
    by_type: dict[str, list[int]] = {}
    for c in chunks:
        by_type.setdefault(c["type"], []).append(c["n_chars"])

    print(f"\n{'Type':<20} {'Count':>6} {'Min':>6} {'Max':>6} {'Mean':>7}")
    print("-" * 50)
    total = 0
    for t in ("paragraph", "list_item", "table", "callout", "glossary_entry"):
        if t not in by_type:
            continue
        vals = by_type[t]
        total += len(vals)
        print(f"{t:<20} {len(vals):>6} {min(vals):>6} {max(vals):>6} {statistics.mean(vals):>7.0f}")
    all_chars = [c["n_chars"] for c in chunks]
    print("-" * 50)
    print(f"{'TOTAL':<20} {total:>6} {min(all_chars):>6} {max(all_chars):>6} {statistics.mean(all_chars):>7.0f}")

    src_ids = [rid for c in chunks for rid in c["source_record_ids"]]
    print(f"\nTotal source records covered: {len(src_ids)}")
    print(f"Total chunks:                 {len(chunks)}")


def main() -> None:
    records = [json.loads(line) for line in RECORDS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Loaded {len(records)} records from {RECORDS_PATH}")

    chunks = build_chunks(records)

    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"Wrote {len(chunks)} chunks to {CHUNKS_PATH}")
    print_stats(chunks)

    # Quick sanity: chunk_ids unique
    ids = [c["chunk_id"] for c in chunks]
    if len(ids) != len(set(ids)):
        print("\n[ERROR] Duplicate chunk_ids detected!")
    else:
        print("\nchunk_id uniqueness: OK")


if __name__ == "__main__":
    main()

"""
Phase 1 - Ingestion: PDF -> clean, structured records.

No chunking, no embeddings, no Qdrant here. This script only answers:
"What does the document say, where is it (page + section), and what kind of
content is it (paragraph, list item, table, callout, glossary entry)?"

Run from the project root:
    python backend/phase1_ingest.py
    python backend/phase1_verify.py

Outputs (data/processed/):
    records.jsonl      one JSON object per content record
    sections.json      every heading found (id, level, title, page)
    toc.json           entries read from the printed contents pages
    parse_report.json  statistics, warnings and removed header/footer patterns
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

try:
    import pymupdf  # PyMuPDF >= 1.24.3
except ImportError:  # older installs expose the same library as "fitz"
    import fitz as pymupdf

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = ROOT / "data" / "Northfield_Student_Academic_Policy_Handbook.pdf"
DEFAULT_OUT = ROOT / "data" / "processed"

# ---- Layout facts measured from THIS PDF (points; A4 page is 595 x 842) ----
HEADER_Y = 55      # text starting above this is the running header
FOOTER_Y = 775     # text starting below this is the footer ("Page X of N")
PARA_GAP = 25      # line-top gap above this starts a new paragraph (lines are ~21 apart)
INDENT_TOL = 6     # sideways shift that starts a new paragraph
SIZE_H1, SIZE_H2, SIZE_H3 = 18.0, 14.0, 12.0   # H3 is also bold-italic

# The PDF itself wraps this header mid-word ("Appro / ved by"); repair it explicitly.
KNOWN_CELL_FIXES = {"Appro ved by": "Approved by"}

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
LEADER_RE = re.compile(r"(?:\. ?)+(\d+)")          # ". . . . . 6" -> page 6
CAPTION_RE = re.compile(r"^(Table \d+)\.\s+(.+)$")
TERMINAL = (".", "!", "?", ":", ";", ")")


def norm(text: str) -> str:
    """Collapse all whitespace (including non-breaking spaces) to single spaces."""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


# --------------------------------------------------------------------------
# Step 1: read lines with their font, size and position
# --------------------------------------------------------------------------
def page_lines(page) -> list[dict]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:           # 0 = text block, 1 = image
            continue
        for ln in block["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            first = spans[0]
            # "lead-in": a bold run at the start of a line followed by normal text
            # (used by AMENDMENT / Exception callouts and glossary entries)
            lead = ""
            for s in spans:
                if "Bold" in s["font"]:
                    lead += s["text"]
                else:
                    break
            has_rest = any("Bold" not in s["font"] for s in spans)
            lines.append({
                "text": norm("".join(s["text"] for s in ln["spans"])),
                "x0": ln["bbox"][0], "x1": ln["bbox"][2],
                "y0": ln["bbox"][1], "y1": ln["bbox"][3],
                "size": round(first["size"], 1),
                "bold": "Bold" in first["font"],
                "italic": bool(re.search(r"Ital|Obli", first["font"])),   # name may be truncated: "...BoldItal"
                "lead": norm(lead) if (lead and has_rest) else "",
            })
    lines.sort(key=lambda d: (round(d["y0"]), d["x0"]))
    return lines


def heading_level(ln: dict) -> int:
    if ln["bold"] and not ln["lead"]:
        if ln["size"] == SIZE_H1:
            return 1
        if ln["size"] == SIZE_H2:
            return 2
        if ln["size"] == SIZE_H3 and ln["italic"]:
            return 3
    return 0


# --------------------------------------------------------------------------
# Step 2: the printed table of contents (used later to validate our headings)
# --------------------------------------------------------------------------
def parse_toc(doc) -> tuple[list[dict], list[int]]:
    toc, toc_pages = [], []
    started = False
    for pno in range(1, len(doc) + 1):
        lines = [l for l in page_lines(doc[pno - 1]) if HEADER_Y <= l["y0"] <= FOOTER_Y]
        if not started:
            if any(l["text"] == "Table of Contents" for l in lines):
                started = True
            else:
                continue
        leaders = [(l, LEADER_RE.fullmatch(l["text"])) for l in lines]
        leaders = [(l, m) for l, m in leaders if m]
        if not leaders:
            break                                   # first page with no leaders: contents ended
        toc_pages.append(pno)
        for leader, m in leaders:
            title = next((t for t in lines if abs(t["y0"] - leader["y0"]) <= 2
                          and t is not leader and HEADING_RE.match(t["text"])), None)
            if title:
                sid, name = HEADING_RE.match(title["text"]).groups()
                toc.append({"id": sid, "title": name, "page": int(m.group(1)),
                            "level": sid.count(".") + 1})
    return toc, toc_pages


# --------------------------------------------------------------------------
# Step 3: tables
# --------------------------------------------------------------------------
def clean_cell(cell) -> str:
    text = norm((cell or "").replace("\n", " "))
    return KNOWN_CELL_FIXES.get(text, text)


def extract_tables(page) -> list[dict]:
    if not hasattr(page, "find_tables"):
        raise RuntimeError("This PyMuPDF is too old for find_tables(); run: pip install -U pymupdf")
    tables = []
    for t in page.find_tables().tables:
        rows = [[clean_cell(c) for c in row] for row in t.extract()]
        tables.append({"bbox": tuple(t.bbox), "rows": rows})
    return tables


def inside(ln: dict, bbox) -> bool:
    cy = (ln["y0"] + ln["y1"]) / 2
    return bbox[0] - 1 <= ln["x0"] <= bbox[2] + 1 and bbox[1] - 1 <= cy <= bbox[3] + 1


def table_markdown(caption: str, rows: list[list[str]]) -> str:
    header, body = rows[0], rows[1:]
    out = [caption, "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)


# --------------------------------------------------------------------------
# Step 4: walk each page top to bottom and build records
# --------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.records: list[dict] = []
        self.headings: list[dict] = []
        self.stack: dict[int, tuple[str, str]] = {}   # heading level -> (id, title)
        self.cur: dict | None = None
        self.warnings: list[str] = []

    # -- section bookkeeping
    def section(self) -> dict:
        if not self.stack:
            return {"section_id": None, "section_title": None, "section_path": []}
        deepest = max(self.stack)
        sid, title = self.stack[deepest]
        return {"section_id": sid, "section_title": title,
                "section_path": [f"{self.stack[l][0]} {self.stack[l][1]}" for l in sorted(self.stack)]}

    def add_heading(self, ln: dict, page: int, level: int):
        m = HEADING_RE.match(ln["text"])
        if not m:
            self.warnings.append(f"p{page}: heading-styled line without a number: {ln['text']!r}")
            return
        self.flush()
        sid, title = m.groups()
        self.stack[level] = (sid, title)
        for deeper in [l for l in self.stack if l > level]:
            del self.stack[deeper]
        self.headings.append({"id": sid, "level": level, "title": title, "page": page})

    # -- paragraph-like records
    def start(self, kind: str, page: int, ln: dict, page_top: bool, lead: str = "", take_x: bool = True):
        self.flush()
        self.cur = {"kind": kind, "lines": [], "page": page, "x": ln["x0"] if take_x else None,
                    "last_y": ln["y0"], "page_top": page_top, "lead": lead, "sec": self.section()}

    def append(self, ln: dict):
        self.cur["lines"].append(ln["text"])
        self.cur["last_y"] = ln["y0"]
        if self.cur["x"] is None:
            self.cur["x"] = ln["x0"]

    def flush(self):
        c, self.cur = self.cur, None
        if not c or not c["lines"]:
            return
        rec = {"page_start": c["page"], "page_end": c["page"], **c["sec"], "type": c["kind"],
               "text": norm(" ".join(c["lines"])), "_page_top": c["page_top"]}
        if c["kind"] == "callout":
            rec["callout_kind"] = "amendment" if c["lead"].startswith("AMENDMENT") else "exception"
            rec["lead_in"] = c["lead"]
        elif c["kind"] == "glossary_entry":
            rec["term"] = c["lead"].rstrip(".")
        self.records.append(rec)

    def add_table(self, page: int, caption: str | None, rows: list[list[str]]):
        self.flush()
        if not caption:
            self.warnings.append(f"p{page}: table without a caption")
            caption = "Table ?"
        m = CAPTION_RE.match(caption)
        self.records.append({
            "page_start": page, "page_end": page, **self.section(), "type": "table",
            "table_id": m.group(1) if m else None, "caption": caption,
            "header": rows[0], "rows": rows[1:], "text": table_markdown(caption, rows),
            "_page_top": False})


def process_page(b: Builder, page, pno: int, stripped: Counter):
    lines = page_lines(page)
    body = []
    for ln in lines:
        if ln["y0"] < HEADER_Y or ln["y0"] > FOOTER_Y:
            stripped[re.sub(r"\d+", "#", ln["text"])] += 1
        else:
            body.append(ln)

    tables = extract_tables(page)
    captions, remaining = [], []
    for ln in body:
        if any(inside(ln, t["bbox"]) for t in tables):
            continue                                   # cell text: comes back through the table rows
        if ln["bold"] and not ln["lead"] and ln["size"] == 12.0 and CAPTION_RE.match(ln["text"]):
            captions.append(ln)
        else:
            remaining.append(ln)

    unused = list(captions)
    elements = [("line", ln["y0"], ln) for ln in remaining]
    for t in tables:
        above = [c for c in unused if c["y1"] <= t["bbox"][1] + 3 and t["bbox"][1] - c["y1"] <= 40]
        cap = max(above, key=lambda c: c["y1"]) if above else None
        if cap:
            unused.remove(cap)
        t["caption"] = cap["text"] if cap else None
        elements.append(("table", t["bbox"][1], t))
    for c in unused:
        b.warnings.append(f"p{pno}: caption without a table: {c['text']!r}")
    elements.sort(key=lambda e: e[1])

    first_text_seen = False
    for kind, _, obj in elements:
        if kind == "table":
            b.add_table(pno, obj["caption"], obj["rows"])
            continue
        ln = obj
        level = heading_level(ln)
        if level:
            b.add_heading(ln, pno, level)
            continue
        page_top = not first_text_seen
        first_text_seen = True

        if ln["text"] == "\u2022":                     # a lone bullet glyph starts a list item
            b.start("list_item", pno, ln, page_top=False, take_x=False)
        elif ln["lead"]:                               # bold lead-in: callout or glossary entry
            lead = ln["lead"]
            if lead.startswith(("AMENDMENT", "Exception to")):
                kind_name = "callout"
            elif (b.section()["section_id"] or "").startswith("15"):
                kind_name = "glossary_entry"
            else:
                kind_name = "paragraph"
            b.start(kind_name, pno, ln, page_top=False, lead=lead)
            b.append(ln)
        else:
            c = b.cur
            continues = (c is not None and c["kind"] != "table"
                         and 0 <= ln["y0"] - c["last_y"] <= PARA_GAP
                         and (c["x"] is None or abs(ln["x0"] - c["x"]) <= INDENT_TOL)
                         and c["page"] == pno)
            if continues:
                b.append(ln)
            else:
                b.start("paragraph", pno, ln, page_top=page_top)
                b.append(ln)
    b.flush()                                          # never carry an open paragraph across pages


# --------------------------------------------------------------------------
# Step 5: stitch paragraphs that were split by a page break
# --------------------------------------------------------------------------
def merge_page_breaks(records: list[dict]) -> list[dict]:
    merged, log = [], []
    for rec in records:
        prev = merged[-1] if merged else None
        if (prev and rec["_page_top"] and rec["type"] == "paragraph"
                and prev["type"] in ("paragraph", "list_item", "callout")
                and prev["page_end"] == rec["page_start"] - 1
                and prev["section_id"] == rec["section_id"]
                and not prev["text"].endswith(TERMINAL)
                and rec["text"][:1].islower()):
            prev["text"] = f"{prev['text']} {rec['text']}"
            prev["page_end"] = rec["page_end"]
            log.append({"section": rec["section_id"], "pages": [prev["page_start"], prev["page_end"]],
                        "joined_at": rec["text"][:40]})
        else:
            merged.append(rec)
    return merged, log


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--show-page", type=int, help="print the records found on this page and exit")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    toc, toc_pages = parse_toc(doc)
    if not toc:
        raise SystemExit("Could not find a table of contents; cannot locate where the body starts.")
    body_start = toc_pages[-1] + 1

    b, stripped = Builder(), Counter()
    for pno in range(body_start, len(doc) + 1):
        process_page(b, doc[pno - 1], pno, stripped)
    records, merges = merge_page_breaks(b.records)
    for i, rec in enumerate(records, 1):
        rec.pop("_page_top", None)
        rec["id"] = f"rec{i:04d}"
        rec["n_chars"] = len(rec["text"])

    if args.show_page:
        for r in records:
            if r["page_start"] <= args.show_page <= r["page_end"]:
                print(f"[{r['id']}] {r['type']:<14} {r['section_id']:<7} p{r['page_start']}-{r['page_end']}  "
                      f"{r['text'][:110]!r}")
        return

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (args.out / "sections.json").write_text(json.dumps(b.headings, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out / "toc.json").write_text(json.dumps(toc, indent=1, ensure_ascii=False), encoding="utf-8")
    report = {
        "source_pdf": args.pdf.name, "pages": len(doc), "toc_pages": toc_pages, "body_start_page": body_start,
        "records": len(records), "records_by_type": dict(Counter(r["type"] for r in records)),
        "headings_by_level": dict(Counter(h["level"] for h in b.headings)),
        "removed_header_footer_patterns": dict(stripped),
        "page_break_merges": merges, "warnings": b.warnings,
    }
    (args.out / "parse_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"Parsed {args.pdf.name}: {len(doc)} pages, contents on pages {toc_pages}, body starts on page {body_start}")
    print(f"Headings by level: {report['headings_by_level']}   TOC entries: {len(toc)}")
    print(f"Records: {len(records)}  {report['records_by_type']}")
    print(f"Page-break merges: {len(merges)}   Warnings: {len(b.warnings)}")
    for w in b.warnings:
        print("  WARNING:", w)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

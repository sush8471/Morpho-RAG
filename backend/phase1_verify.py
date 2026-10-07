"""
Phase 1 - Verification. Run after phase1_ingest.py.

    python backend/phase1_verify.py

It re-reads the PDF and checks the parsed output (data/processed/) against it:
  1. page structure and printed page numbers
  2. header/footer removal
  3. every printed contents entry matches a detected heading (id, title, page)
  4. all 8 tables: pages, sections, row counts, spot-checked cells
  5. no text lost or duplicated (character-level comparison with the PDF)
  6. callouts, glossary entries, list items, broken paragraphs
  7. excluded topics are really absent from the document
  8. every answer-key section exists, with its page, and key facts appear in the cited sections

Each line is PASS, WARN or FAIL. Exit code is 1 if anything FAILs.
The EXPECT values are facts about the Northfield handbook that we measured by hand
(page footers, contents page, table captions). Change them if you change the document.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

from phase1_ingest import DEFAULT_OUT, DEFAULT_PDF, FOOTER_Y, HEADER_Y, ROOT, page_lines

DEFAULT_KEY = ROOT / "eval" / "answer_key.json"
HEADER_TEXT = "Northfield Institute of Technology - Student Academic Policy Handbook"

EXPECT = {
    "pages": 41, "body_start": 6, "toc_entries": 123, "h3_headings": 11,
    "glossary_entries": 23,
    "amendment_sections": {"5.5.2", "7.2"},
    "exception_sections": {"10.2", "12.1", "14.3"},
}
# table id -> (page, section, number of rows including the header row)
TABLES = {
    "Table 1": (9, "2.1", 5), "Table 2": (12, "3.3", 5), "Table 3": (14, "4.4", 8),
    "Table 4": (17, "5.1", 9), "Table 5": (22, "7.1", 6), "Table 6": (23, "7.4", 6),
    "Table 7": (25, "8.2", 4), "Table 8": (41, "16.1", 8),
}
# (table, value in first column, column header, expected cell)
CELLS = [
    ("Table 1", "B.Sc. Applied Data Science", "Annual seats", "120"),
    ("Table 2", "60% to below 70%", "Condonation fee per course", "MRL 2,500"),
    ("Table 3", "70 to 79", "Letter grade", "B+"),
    ("Table 4", "End-semester examinations", "Spring semester 2027", "3 to 14 May 2027"),
    ("Table 5", "Tuition fee per semester", "B.Tech", "42,000"),
    ("Table 5", "Tuition fee per semester", "M.Tech", "48,000"),
    ("Table 6", "8 to 21 days after the start date", "Tuition fee refund", "60%"),
    ("Table 6", "22 to 35 days after the start date", "Tuition fee refund", "30%"),
    ("Table 6", "36 days or more after the start date", "Tuition fee refund", "0%"),
    ("Table 7", "Tier 2", "Scholarship name", "Northfield Excellence Award"),
    ("Table 8", "5.0", "Effective date", "3 August 2026"),
    ("Table 8", "4.1", "Approved by", "ASC"),          # header that the PDF wraps mid-word
]
EXCLUDED_WORDS = ["parking", "cafeteria", "canteen", "football", "athletics", "alumni", "sports"]

# Key facts that must appear in the cited sections (section id, text). Matching ignores
# case and extra whitespace. Tables are searched in their "| a | b |" markdown form.
NEEDLES = {
    "Q01": [("3.1", "at least 75% of the scheduled class sessions")],
    "Q02": [("1.3.1", "contains 80 teaching days")],
    "Q03": [("1.5", "48 hours after posting")],
    "Q04": [("2.3", "application fee is MRL 1,000 and is not refundable")],
    "Q05": [("4.1", "32 contact hours of laboratory work")],
    "Q06": [("4.3", "at least 40% of the total marks"), ("4.3", "at least 35% of the maximum marks")],
    "Q07": [("6.2", "above 40% is referred automatically")],
    "Q08": [("9.3", "inside their residence block by 22:00"), ("9.3", "reopen at 05:30")],
    "Q09": [("10.3", "at most 2 semesters of leave of absence")],
    "Q10": [("11.1", "has six members")],
    "Q11": [("12.2", "postgraduate student may borrow 10 books for 30 days")],
    "Q12": [("13.1", "B.Tech: at least 8 weeks, worth 6 credits")],
    "Q13": [("2.1", "B.Sc. Applied Data Science | 6 | 120 |")],
    "Q14": [("3.3", "60% to below 70% | Eligible only after condonation approved by the Dean of Academic Affairs | MRL 2,500")],
    "Q15": [("4.4", "70 to 79 | B+ | 8 |")],
    "Q16": [("5.1", "End-semester examinations | 30 November to 11 December 2026 | 3 to 14 May 2027")],
    "Q17": [("7.1", "Tuition fee per semester | 42,000 | 36,000 | 48,000 | 45,000")],
    "Q18": [("7.4", "22 to 35 days after the start date | 30% | 0%")],
    "Q19": [("8.2", "Tier 2 | Northfield Excellence Award | 8.50 | 50% | 40")],
    "Q20": [("5.1", "Semester begins | 3 August 2026"), ("7.1", "Tuition fee per semester | 42,000"),
            ("7.4", "8 to 21 days after the start date | 60% | 0%"),
            ("10.4", "date and time on which the Registrar receives the notice")],
    "Q21": [("3.1", "at least 75%"), ("10.2", "counted as attended")],
    "Q22": [("8.2", "Tier 1 | Kestrel Founders"), ("8.4", "at least 36 credits"), ("8.4", "still at least 8.00")],
    "Q23": [("13.1", "worth 6 credits"), ("13.1", "count towards the total required for graduation"),
            ("14.1", "B.Tech, 160 credits")],
    "Q24": [("12.4", "exceed MRL 200"), ("5.2", "no clearance hold from the library")],
    "Q25": [("6.4", "Level 2: grade F in the course"), ("8.5", "forfeits the scholarship for the rest of the academic year")],
    "Q26": [("10.2", "up to a maximum of 20 teaching days of medical leave")],
    "Q27": [("12.1", "00:45"), ("12.1", "Late Study Pass"), ("9.3", "22:00")],
    "Q28": [("14.3", "up to 30 credits"), ("14.3", "CGPA of at least 6.00"), ("4.2", "maximum is 26 credits")],
    "Q29": [("5.5.2", "MRL 600"), ("5.5.2", "within 10 days"), ("5.5.2", "MRL 400")],
    "Q30": [("7.2", "MRL 500 is charged for each week"), ("7.2", "MRL 3,000"), ("7.2", "MRL 100 was charged")],
}

results: list[tuple[str, str, str]] = []


def report(status: str, check: str, detail: str = ""):
    results.append((status, check, detail))
    mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[status]
    print(f"  [{mark}] {check}" + (f"  -> {detail}" if detail else ""))


def check(cond: bool, name: str, detail_fail: str = "", detail_ok: str = "", warn_only: bool = False):
    if cond:
        report("PASS", name, detail_ok)
    else:
        report("WARN" if warn_only else "FAIL", name, detail_fail)


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def alnum_counter(text: str) -> Counter:
    return Counter(ch for ch in text if ch.isalnum())


def sequence_problems(ids: list[str]) -> list[str]:
    """Headings must be numbered 1,2,3... within their parent, with no gaps or repeats."""
    problems, last_child = [], {}
    for sid in ids:
        parts = tuple(int(p) for p in sid.split("."))
        parent, n = parts[:-1], parts[-1]
        if parent and last_child.get(parent[:-1], 0) < parent[-1] and parent not in last_child:
            problems.append(f"{sid}: parent {'.'.join(map(str, parent))} not seen before it")
        if n != last_child.get(parent, 0) + 1:
            problems.append(f"{sid}: expected number {last_child.get(parent, 0) + 1} under "
                            f"{'.'.join(map(str, parent)) or 'top level'}")
        last_child[parent] = n
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    recs = [json.loads(l) for l in open(args.out / "records.jsonl", encoding="utf-8")]
    sections = json.load(open(args.out / "sections.json", encoding="utf-8"))
    toc = json.load(open(args.out / "toc.json", encoding="utf-8"))
    rep = json.load(open(args.out / "parse_report.json", encoding="utf-8"))
    body_start, last = rep["body_start_page"], len(doc)

    # ---------------------------------------------------------------- 1
    print("\n1. Page structure")
    check(len(doc) == EXPECT["pages"], f"PDF has {EXPECT['pages']} pages", f"found {len(doc)}")
    check(body_start == EXPECT["body_start"], f"body starts on page {EXPECT['body_start']}", f"found {body_start}")
    toc_one = next((e["page"] for e in toc if e["id"] == "1"), None)
    check(toc_one == body_start, "contents page says section 1 is on the page where the body starts",
          f"contents says {toc_one}, body starts on {body_start}")
    bad_footers = []
    for pno in range(2, last + 1):
        foot = [l["text"] for l in page_lines(doc[pno - 1]) if l["y0"] > FOOTER_Y]
        m = re.fullmatch(r"Page (\d+) of (\d+)", foot[0]) if foot else None
        if not m or int(m.group(1)) != pno or int(m.group(2)) != last:
            bad_footers.append((pno, foot))
    check(not bad_footers, "printed page number equals PDF page position on every page (cover excluded)",
          f"mismatches: {bad_footers[:3]}")

    # ---------------------------------------------------------------- 2
    print("\n2. Header / footer removal")
    patterns = set(rep["removed_header_footer_patterns"])
    allowed = {HEADER_TEXT, "Page # of #"}
    check(patterns <= allowed, "only the running header and 'Page X of N' were removed",
          f"unexpected removed lines: {sorted(patterns - allowed)}")
    leak = [r["id"] for r in recs if HEADER_TEXT in r["text"] or re.search(r"Page \d+ of \d+", r["text"])]
    check(not leak, "no header/footer text inside any record", f"records: {leak[:5]}")

    # ---------------------------------------------------------------- 3
    print("\n3. Headings vs printed contents")
    check(len(toc) == EXPECT["toc_entries"], f"contents lists {EXPECT['toc_entries']} headings", f"found {len(toc)}")
    by_id = {h["id"]: h for h in sections}
    check(len(by_id) == len(sections), "heading ids are unique", f"{len(sections) - len(by_id)} duplicates")
    mism = []
    for e in toc:
        h = by_id.get(e["id"])
        if not h:
            mism.append(f"{e['id']} missing")
        elif (h["title"], h["page"], h["level"]) != (e["title"], e["page"], e["level"]):
            mism.append(f"{e['id']}: contents={e['title']!r}/p{e['page']} found={h['title']!r}/p{h['page']}")
    check(not mism, f"all {len(toc)} contents entries found with the same title, level and page", "; ".join(mism[:5]))
    toc_ids = {e["id"] for e in toc}
    extra = [h for h in sections if h["id"] not in toc_ids]
    check(len(extra) == EXPECT["h3_headings"] and all(h["level"] == 3 for h in extra),
          f"the {EXPECT['h3_headings']} headings not in the contents are all level 3 (x.y.z)",
          f"found {len(extra)} extra: {[h['id'] for h in extra]}")
    wrong_depth = [h["id"] for h in sections if h["level"] != h["id"].count(".") + 1]
    check(not wrong_depth, "heading level matches numbering depth", f"{wrong_depth[:5]}")
    seq = sequence_problems([h["id"] for h in sections])
    check(not seq, "numbering is sequential, with no gaps or repeats", "; ".join(seq[:4]))

    # ---------------------------------------------------------------- 4
    print("\n4. Tables")
    tabs = {r["table_id"]: r for r in recs if r["type"] == "table"}
    check(len(tabs) == len(TABLES), f"{len(TABLES)} tables found", f"found {sorted(tabs)}")
    for tid, (pg, sec, nrows) in TABLES.items():
        r = tabs.get(tid)
        ok = bool(r) and r["page_start"] == pg and r["section_id"] == sec and len(r["rows"]) + 1 == nrows
        check(ok, f"{tid}: page {pg}, section {sec}, {nrows} rows incl. header",
              f"found {(r['page_start'], r['section_id'], len(r['rows']) + 1) if r else None}")
    for tid, key, col, want in CELLS:
        r, got = tabs.get(tid), None
        if r and col in r["header"]:
            row = next((x for x in r["rows"] if x[0] == key), None)
            got = row[r["header"].index(col)] if row else None
        check(got == want, f"{tid} [{key}] / {col} = {want!r}", f"got {got!r}")

    # ---------------------------------------------------------------- 5
    print("\n5. No text lost or duplicated")
    raw = Counter()
    for pno in range(body_start, last + 1):
        for l in page_lines(doc[pno - 1]):
            if HEADER_Y <= l["y0"] <= FOOTER_Y:
                raw += alnum_counter(l["text"])
    rebuilt = Counter()
    for h in sections:
        rebuilt += alnum_counter(f"{h['id']} {h['title']}")
    for r in recs:
        rebuilt += alnum_counter(r["text"])
    check(raw == rebuilt, f"letters and digits in pages {body_start}-{last} match the records exactly",
          f"missing from records: {dict((raw - rebuilt).most_common(6))}; extra in records: "
          f"{dict((rebuilt - raw).most_common(6))}", detail_ok=f"{sum(raw.values()):,} characters compared")

    # ---------------------------------------------------------------- 6
    print("\n6. Record types and paragraph quality")
    check(all(r["text"].strip() for r in recs), "no empty records")
    check(all(r["section_id"] and body_start <= r["page_start"] <= r["page_end"] <= last for r in recs),
          "every record has a section and a valid page range")
    bullets = sum(1 for pno in range(body_start, last + 1) for l in page_lines(doc[pno - 1]) if l["text"] == "\u2022")
    n_list = sum(1 for r in recs if r["type"] == "list_item")
    check(bullets == n_list, "list items equal bullet glyphs in the PDF", f"{bullets} bullets vs {n_list} list items",
          detail_ok=f"{n_list} items")
    callouts = [r for r in recs if r["type"] == "callout"]
    amend = {r["section_id"] for r in callouts if r["callout_kind"] == "amendment"}
    exc = {r["section_id"] for r in callouts if r["callout_kind"] == "exception"}
    check(amend == EXPECT["amendment_sections"], f"amendment callouts in {sorted(EXPECT['amendment_sections'])}", f"found {sorted(amend)}")
    check(exc == EXPECT["exception_sections"], f"exception callouts in {sorted(EXPECT['exception_sections'])}", f"found {sorted(exc)}")
    gloss = [r for r in recs if r["type"] == "glossary_entry"]
    check(len(gloss) == EXPECT["glossary_entries"] and all(r["section_id"] == "15.1" for r in gloss),
          f"{EXPECT['glossary_entries']} glossary entries, all in 15.1", f"found {len(gloss)}")
    check(len({r["term"] for r in gloss}) == len(gloss), "glossary terms are unique")
    joins = rep["page_break_merges"]
    check(len(joins) >= 1, "paragraphs split by a page break were rejoined", "none rejoined",
          detail_ok="; ".join(f"{j['section']} p{j['pages'][0]}-{j['pages'][1]}" for j in joins))
    low = [r["id"] for r in recs if r["type"] == "paragraph" and r["text"][:1].islower()]
    check(not low, "no paragraph starts in lower case (broken paragraph)", f"{low[:5]}", warn_only=True)
    dangling = [r["id"] for r in recs if r["type"] == "paragraph" and re.search(r"(,|\band|\bor|\bthe|\bof)$", r["text"])]
    check(not dangling, "no paragraph ends mid-sentence", f"{dangling[:5]}", warn_only=True)
    print(f"      record counts: {rep['records_by_type']}")

    # ---------------------------------------------------------------- 7
    print("\n7. Excluded topics (for the 'not found' tests)")
    full = " ".join(doc[i].get_text() for i in range(last)).lower()
    found = [w for w in EXCLUDED_WORDS if w in full]
    check(not found, f"none of {EXCLUDED_WORDS} appear anywhere in the PDF", f"found: {found}")

    # ---------------------------------------------------------------- 8
    print("\n8. Answer key")
    if not args.key.exists():
        report("WARN", "answer key not found; skipped", str(args.key))
    else:
        key = json.load(open(args.key, encoding="utf-8"))
        qs = key["questions"]
        print(f"      {len(qs)} questions, {len(key.get('unanswerable_questions', []))} unanswerable")

        def sec_records(sid):
            return [r for r in recs if r["section_id"] == sid or (r["section_id"] or "").startswith(sid + ".")]

        def sec_text(sid):
            return flat(" ".join(r["text"] for r in sec_records(sid)))

        pages_out, missing = {}, []
        for q in qs:
            info = {}
            for sid in q["sections"]:
                h = by_id.get(sid)
                if not h:
                    missing.append(f"{q['id']}:{sid}")
                    continue
                rs = sec_records(sid)
                info[sid] = {"heading_page": h["page"],
                             "pages": [min(r["page_start"] for r in rs), max(r["page_end"] for r in rs)] if rs else None}
            pages_out[q["id"]] = info
        check(not missing, "every section cited in the key exists in the handbook", f"missing: {missing}")

        bad = []
        for q in qs:
            for sid, needle in NEEDLES.get(q["id"], []):
                if flat(needle) not in sec_text(sid):
                    bad.append(f"{q['id']} §{sid}: {needle!r}")
        n_needles = sum(len(v) for v in NEEDLES.values())
        check(not bad, f"{n_needles} key facts found in the cited sections", "; ".join(bad[:6]))
        uncovered = []
        for q in qs:
            listed = set(q["sections"])
            for sid, _ in NEEDLES.get(q["id"], []):
                if sid not in listed:
                    uncovered.append(f"{q['id']} needs §{sid}")
        check(not uncovered, "each question lists every section its answer depends on",
              "; ".join(sorted(set(uncovered))), warn_only=True)
        check(all(q["id"] in NEEDLES for q in qs), "every question has automatic fact checks",
              f"no checks for {[q['id'] for q in qs if q['id'] not in NEEDLES]} (verify those by hand)", warn_only=True)

        (args.out / "answer_key_pages.json").write_text(json.dumps(pages_out, indent=1), encoding="utf-8")
        print("\n      question -> section: page(s)")
        for q in qs:
            cells = ", ".join(f"§{s}: p{v['pages'][0]}" + (f"-{v['pages'][1]}" if v['pages'][1] != v['pages'][0] else "")
                              for s, v in pages_out[q["id"]].items() if v["pages"])
            print(f"      {q['id']}  [{q['type']}]  {cells}")
        print(f"      (saved {args.out / 'answer_key_pages.json'})")

    # ---------------------------------------------------------------- summary
    n = Counter(s for s, _, _ in results)
    print(f"\nPHASE 1 VERIFICATION: {n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed")
    sys.exit(1 if n["FAIL"] else 0)


if __name__ == "__main__":
    main()

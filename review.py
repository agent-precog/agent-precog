#!/usr/bin/env python3
"""Build the maintainer's title/abstract review workbook, and apply the returned workbook to decisions.csv.

    python3 review.py build --run 2026-11-15_p1 [--leak-frac 0.05 --leak-min 100 --seed 20261115]
    python3 review.py apply --run 2026-11-15_p1 --sheet path/to/returned.xlsx [--date 2026-11-20]

build: tab 1 lists every AI include (title, abstract, AI reason) with a decision dropdown; tab 2 is the seeded leak-check
       sample of AI excludes. Writes data/screening/<run>_review.xlsx and <run>_leakcheck_ids.json.
apply: reads the maintainer's choices back into data/decisions.csv (human_decision, exclusion_code, decided_on, notes),
       and writes data/screening/<run>_fulltext_queue.csv for the records that go to full text.
"""
import argparse, csv, json, random, re, time
from pathlib import Path

ROOT = Path(__file__).parent
SCREEN = ROOT / "data" / "screening"
INC_OPTS = '"include,exclude-E1 off-topic,exclude-E2 no evaluation,exclude-E3 survey,exclude-E4 wrong level,exclude-E7 not English"'
LEAK_OPTS = '"agree exclude,leak - include"'
MECH = re.compile(r"collision[- ]avoid|collision[- ]free|safety filter|barrier function|\bCBF|shield|runtime (monitor|verification|assurance|enforcement)|interven|defer|halt|guardrail|validator|safety-critical control|emergency (stop|brak)|veto|abstain|fail-safe|reachab|safety guarantee|provably safe|hazard detect|anomaly detect|cascad", re.I)
LLM = re.compile(r"\bLLM|large language model|tool-call|agentic|language[- ]model agent", re.I)


def tier(title, abstract, year):
    t = title + " " + abstract
    m, l = bool(MECH.search(t)), bool(LLM.search(t))
    y = int(year) if str(year).isdigit() else 0
    return "A" if (m and y >= 2022) or (m and l) else ("B" if m or l else "C")


def build(a):
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, Alignment, PatternFill
    recs = {r["record_id"]: r for r in csv.DictReader(open(SCREEN / f"{a.run}_records.csv", newline="", encoding="utf-8"))}
    labels = list(csv.DictReader(open(SCREEN / f"{a.run}_ai_labels.csv", newline="", encoding="utf-8")))
    inc = [l for l in labels if l["ai_label"] in ("include", "unlabelled")]
    exc = [l for l in labels if l["ai_label"] == "exclude"]
    rng = random.Random(a.seed)
    leak = rng.sample(exc, min(len(exc), max(a.leak_min, round(a.leak_frac * len(exc))))) if exc else []
    json.dump(sorted(l["record_id"] for l in leak), open(SCREEN / f"{a.run}_leakcheck_ids.json", "w"), indent=0)
    hdr = ["record_id", "database", "year", "title", "venue", "abstract", "AI label / reason", "YOUR DECISION", "notes"]

    def sheet(ws, rows, opts):
        ws.append(hdr)
        for l in sorted(rows, key=lambda l: (-int(recs[l["record_id"]]["year"] or 0), recs[l["record_id"]]["title"])):
            r = recs[l["record_id"]]
            ws.append([r["record_id"], r["database"], r["year"], r["title"], r["venue"], r["abstract"], f"{l['ai_label']}{(' ' + l['ai_code']) if l['ai_code'] else ''}: {l['ai_reason']}", "", ""])
        dv = DataValidation(type="list", formula1=opts, allow_blank=True); ws.add_data_validation(dv); dv.add(f"H2:H{ws.max_row}")
        for i, wd in enumerate([28, 14, 6, 44, 26, 90, 44, 26, 24], 1):
            c = ws.cell(1, i); c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="DDE7E3"); ws.column_dimensions[c.column_letter].width = wd
        for row in ws.iter_rows(min_row=2):
            for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
        for rr in range(2, ws.max_row + 1): ws.cell(rr, 8).fill = PatternFill("solid", fgColor="FFF4CC")
        ws.freeze_panes = "D2"

    wb = Workbook(); sheet(wb.active, inc, INC_OPTS); wb.active.title = "AI includes"
    sheet(wb.create_sheet("Leak check"), leak, LEAK_OPTS)
    out = SCREEN / f"{a.run}_review.xlsx"; wb.save(out)
    print(f"{len(inc)} AI includes to review, {len(leak)} leak-check records (of {len(exc)} AI excludes) -> {out}")


def apply(a):
    from openpyxl import load_workbook
    wb = load_workbook(a.sheet, data_only=True)
    dec = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2, values_only=True):
            rid, choice, note = row[0], row[7], row[8] or ""
            if not choice:
                continue
            if choice == "include" or choice.startswith("leak"):
                dec[rid] = ("include", "", note)
            elif choice.startswith("exclude"):
                dec[rid] = ("exclude", choice.split()[0].split("-")[1], note)
            elif choice.startswith("agree"):
                dec[rid] = ("exclude", None, note)  # keep the AI code
    leak = set(json.load(open(SCREEN / f"{a.run}_leakcheck_ids.json")))
    dpath = ROOT / "data" / "decisions.csv"
    rows = list(csv.DictReader(open(dpath, newline="", encoding="utf-8")))
    n = 0
    for d in rows:
        if d["stage"] == "title_abstract" and d["record_id"] in dec and a.run in d["notes"]:
            h, code, note = dec[d["record_id"]]
            d["human_decision"] = h
            d["exclusion_code"] = d["ai_code"] if code is None else code
            d["decided_on"] = a.date
            tag = "leak-check sample" if d["record_id"] in leak else "maintainer review of AI inclusion"
            d["notes"] = f"{d['notes']}; {tag}" + (f"; {note}" if note else "")
            n += 1
    with open(dpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    recs = {r["record_id"]: r for r in csv.DictReader(open(SCREEN / f"{a.run}_records.csv", newline="", encoding="utf-8"))}
    q = [d for d in rows if d["stage"] == "title_abstract" and a.run in d["notes"] and d["record_id"] in recs and
         (d["human_decision"] == "include" or (d["human_decision"] == "" and d["ai_label"] == "include"))]
    qcols = ["record_id", "tier", "year", "title", "venue", "doi", "url", "arxiv_id", "pdf", "status"]
    with open(SCREEN / f"{a.run}_fulltext_queue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qcols); w.writeheader()
        for d in sorted(q, key=lambda d: (tier(recs[d["record_id"]]["title"], recs[d["record_id"]]["abstract"], recs[d["record_id"]]["year"]), -int(recs[d["record_id"]]["year"] or 0))):
            r = recs[d["record_id"]]
            w.writerow(dict(record_id=r["record_id"], tier=tier(r["title"], r["abstract"], r["year"]), year=r["year"], title=r["title"], venue=r["venue"],
                            doi=r["doi"], url=r["url"], arxiv_id=r["arxiv_id"], pdf="", status="queued"))
    leaks = sum(1 for d in rows if d["record_id"] in leak and d["human_decision"] == "include" and a.run in d["notes"])
    print(f"{n} decisions applied; {len(q)} records to full text -> {SCREEN / (a.run + '_fulltext_queue.csv')}; leak check: {leaks} leaks in {len(leak)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--run", required=True); b.add_argument("--leak-frac", type=float, default=0.05); b.add_argument("--leak-min", type=int, default=100); b.add_argument("--seed", type=int, default=None)
    p = sub.add_parser("apply"); p.add_argument("--run", required=True); p.add_argument("--sheet", required=True); p.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    if a.cmd == "build":
        if a.seed is None: a.seed = int(re.sub(r"\D", "", a.run)[:8] or 20261109)
        build(a)
    else:
        apply(a)

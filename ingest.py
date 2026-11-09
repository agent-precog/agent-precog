#!/usr/bin/env python3
"""Turn raw database exports into a normalised screening set and a blind dual-screen sample.

    python3 ingest.py --run 2026-11-09_p1_ieee --pillar 1 --database "IEEE Xplore" [--sample 0.2 --seed 20261109]

Reads  data/raw/<run>_*.csv       (one or more export files from the database)
Writes data/screening/<run>_records.csv   normalised records: record_id,title,authors,year,venue,type,doi,url,abstract
       data/screening/<run>_blind.csv     the maintainer's blind sample (no AI columns), with empty decision/code columns

record_id is the DOI where present, otherwise the IEEE document number from the PDF link, prefixed by database.
The sample is drawn with a fixed seed so it can be reproduced; the seed is written into the file header comment.
Records already in data/papers.csv (by DOI or normalised title) are kept in the set but flagged in the `in_review`
column so they can be coded E5 (duplicate) at screening.
"""
import argparse, csv, glob, html, random, re, sys
from pathlib import Path

ROOT = Path(__file__).parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "screening"


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def ieee_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("Document Title"):
                continue
            doi = (r.get("DOI") or "").strip().lower()
            m = re.search(r"arnumber=(\d+)|fileName=(\d+)\.pdf", r.get("PDF Link") or "")
            num = next((g for g in (m.groups() if m else ()) if g), "")
            rid = f"doi:{doi}" if doi else f"ieee:{num}" if num else f"title:{norm_title(r['Document Title'])[:60]}"
            yield {
                "record_id": rid,
                "title": clean(r["Document Title"]),
                "authors": clean(r.get("Authors", "")),
                "year": (r.get("Publication Year") or "").strip(),
                "venue": clean(r.get("Publication Title", "")),
                "type": clean(r.get("Document Identifier", "")),
                "doi": doi,
                "url": (f"https://doi.org/{doi}" if doi else (r.get("PDF Link") or "").strip()),
                "abstract": clean(r.get("Abstract", "")),
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--pillar", type=int, required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--sample", type=float, default=0.20)
    ap.add_argument("--min-sample", type=int, default=50)
    ap.add_argument("--max-sample", type=int, default=150, help="protocol v1.1: blind sample is 20%% of the batch, min 50, max 150")
    ap.add_argument("--seed", type=int, default=20261109)
    a = ap.parse_args()

    files = sorted(glob.glob(str(RAW / f"{a.run}_*.csv")))
    if not files:
        sys.exit(f"no raw files matching data/raw/{a.run}_*.csv")
    records, seen = [], set()
    for f in files:
        for r in ieee_rows(f):
            if r["record_id"] in seen:
                continue
            seen.add(r["record_id"]); records.append(r)

    # flag anything already in the review
    papers = list(csv.DictReader(open(ROOT / "data" / "papers.csv", newline="", encoding="utf-8")))
    in_dois = {p["doi_or_arxiv"].strip().lower() for p in papers if p["doi_or_arxiv"].startswith("10.")}
    in_titles = {norm_title(p["title"]) for p in papers}
    for r in records:
        r["in_review"] = "yes" if (r["doi"] in in_dois or norm_title(r["title"]) in in_titles) else ""
        r["pillar"], r["database"] = a.pillar, a.database

    OUT.mkdir(exist_ok=True)
    cols = ["record_id", "pillar", "database", "title", "authors", "year", "venue", "type", "doi", "url", "in_review", "abstract"]
    with open(OUT / f"{a.run}_records.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(records)

    n_draw = min(len(records), max(a.min_sample, round(len(records) * a.sample)))
    rng = random.Random(a.seed)
    draw = rng.sample(records, n_draw)          # the full 20% draw, reproducible from the seed
    sample = draw[: min(n_draw, a.max_sample)]  # protocol v1.1 cap: the first max_sample of that draw
    sample.sort(key=lambda r: (r["year"], r["title"]))
    with open(OUT / f"{a.run}_blind.csv", "w", newline="", encoding="utf-8") as f:
        f.write(f"# blind dual-screen sample: {len(sample)} of {len(records)} records (first {len(sample)} of a {n_draw}-record draw, seed {a.seed}, protocol v1.1 cap {a.max_sample}), drawn before any AI label existed\n")
        w = csv.DictWriter(f, fieldnames=["record_id", "title", "year", "venue", "abstract", "url", "human_decision", "exclusion_code", "notes"])
        w.writeheader()
        for r in sample:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    print(f"{len(records)} records from {len(files)} files -> {OUT / (a.run + '_records.csv')}")
    print(f"{len(sample)} blind-sample records -> {OUT / (a.run + '_blind.csv')}  (already in review: {sum(1 for r in records if r['in_review'])})")


if __name__ == "__main__":
    main()

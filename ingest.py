#!/usr/bin/env python3
"""Turn raw database exports into a normalised, deduplicated screening set.

    python3 ingest.py --run 2026-11-09_p1_ieee --pillar 1 --database "IEEE Xplore"            # IEEE Xplore CSV exports
    python3 ingest.py --run 2026-11-15_p1 --pillar 1 --database api                           # files written by search.py

Reads  data/raw/<run>_*.csv|.bib  one or more export files (IEEE Xplore CSV, ACM Digital Library BibTeX, or the normalised format search.py writes)
Writes data/screening/<run>_records.csv   record_id,pillar,database,title,authors,year,venue,type,doi,url,arxiv_id,in_review,duplicate_of,abstract
       data/screening/<run>_blind.csv     only with --blind (protocols v1.0-v1.2; retired by v1.3)

record_id is the DOI where present, otherwise the arXiv id, otherwise the database's own id.
Deduplication (PRISMA "records removed before screening"): a record is marked duplicate_of = <earlier record_id> when its
DOI, arXiv id or normalised title matches a record in any earlier run's *_records.csv or a paper already in papers.csv.
Duplicates stay in the file so the count is auditable but are not screened. --blind retains the original reproducible
sample draw for anyone re-running the calibration rounds.
"""
import argparse, csv, glob, html, random, re, sys
from pathlib import Path

ROOT = Path(__file__).parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "screening"
COLS = ["record_id", "pillar", "database", "title", "authors", "year", "venue", "type", "doi", "url", "arxiv_id", "in_review", "duplicate_of", "abstract"]


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def ieee_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("Document Title"):
                continue
            doi = (r.get("DOI") or "").strip().lower()
            m = re.search(r"arnumber=(\d+)|fileName=(\d+)\.pdf", r.get("PDF Link") or "")
            num = next((g for g in (m.groups() if m else ()) if g), "")
            rid = f"doi:{doi}" if doi else f"ieee:{num}" if num else f"title:{norm_title(r['Document Title'])[:60]}"
            yield {"record_id": rid, "title": clean(r["Document Title"]), "authors": clean(r.get("Authors", "")),
                   "year": (r.get("Publication Year") or "").strip(), "venue": clean(r.get("Publication Title", "")),
                   "type": clean(r.get("Document Identifier", "")), "doi": doi,
                   "url": f"https://doi.org/{doi}" if doi else (r.get("PDF Link") or "").strip(),
                   "arxiv_id": "", "abstract": clean(r.get("Abstract", "")), "database": "IEEE Xplore"}


def api_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("title"):
                yield {k: r.get(k, "") for k in ("record_id", "title", "authors", "year", "venue", "type", "doi", "url", "arxiv_id", "abstract", "database")}


def bibtex_rows(path):
    """ACM Digital Library or Scopus citation export (BibTeX). One record per @type{key, ...} block."""
    text = open(path, encoding="utf-8-sig", errors="replace").read()
    for block in re.split(r"\n(?=@)", text):
        if not block.lstrip().startswith("@"):
            continue
        fields = {}
        for m in re.finditer(r"(\w+)\s*=\s*\{", block):
            k, i, depth = m.group(1).lower(), m.end(), 1
            while i < len(block) and depth:
                if block[i] == "{": depth += 1
                elif block[i] == "}": depth -= 1
                i += 1
            fields[k] = block[m.end():i - 1]
        if not fields.get("title"):
            continue
        de = lambda v: clean(re.sub(r"[{}]", "", v or "").replace("\\&", "&").replace("\\_", "_"))
        doi = de(fields.get("doi", "")).lower()
        if not doi:   # some entries carry the DOI only in the entry key or the url
            mdoi = re.search(r"10\.\d{4,9}/[^\s,}]+", block.split("abstract", 1)[0])
            doi = mdoi.group(0).lower().rstrip(",}") if mdoi else ""
        kind = (block.lstrip()[1:].split("{", 1)[0] or "").lower()
        sid = re.search(r"scopus\.com/pages/publications/(\d+)", block)   # Scopus export: entry keys repeat, use the Scopus id
        rid = f"doi:{doi}" if doi else f"scopus:{sid.group(1)}" if sid else "acm:" + de(block.lstrip()[1:].split("{", 1)[1].split(",", 1)[0])
        yield {"record_id": rid,
               "title": de(fields.get("title")), "authors": "; ".join(a.strip() for a in de(fields.get("author", "")).split(" and ")),
               "year": de(fields.get("year", ""))[:4], "venue": de(fields.get("booktitle") or fields.get("journal") or fields.get("series", "")),
               "type": {"inproceedings": "Conference", "conference": "Conference", "article": "Journal", "incollection": "Book chapter",
                        "book": "Book", "phdthesis": "Thesis"}.get(kind, kind),
               "doi": doi, "url": de(fields.get("url", "")) or (f"https://doi.org/{doi}" if doi else ""),
               "arxiv_id": "", "abstract": de(fields.get("abstract", "")), "database": "ACM Digital Library"}


def reader_for(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        head = f.read(4000)
    if "Document Title" in head:
        return ieee_rows
    if head.lstrip().startswith("@") or re.search(r"^@\w+\{", head, re.M):   # ACM, or Scopus (which puts two header lines first)
        return bibtex_rows
    return api_rows


def prior_index(run):
    """DOI, arXiv id and normalised title of everything already in an earlier run or in the review."""
    idx = {}
    for p in sorted(glob.glob(str(OUT / "*_records.csv"))):
        if Path(p).name == f"{run}_records.csv":
            continue
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            for k in (f"doi:{r['doi']}" if r.get("doi") else "", f"arxiv:{r.get('arxiv_id','')}" if r.get("arxiv_id") else "", "t:" + norm_title(r["title"])):
                if k and k not in idx:
                    idx[k] = r["record_id"]
    run_date = run[:10]
    for p in csv.DictReader(open(ROOT / "data" / "papers.csv", newline="", encoding="utf-8")):
        if p["included_via"] == "search" and p["screened_on"] >= run_date:
            continue  # included from this run (or later): not a prior duplicate
        d = p["doi_or_arxiv"].strip().lower()
        for k in (f"doi:{d}" if d.startswith("10.") else "", f"arxiv:{d.replace('arxiv:','')}" if d.startswith("arxiv:") else "", "t:" + norm_title(p["title"])):
            if k and k not in idx:
                idx[k] = "paper:" + p["id"]
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--pillar", type=int, required=True)
    ap.add_argument("--database", required=True, help='database name, or "api" to take each file\'s own database column')
    ap.add_argument("--blind", action="store_true", help="also draw the protocol v1.1 blind sample (retired)")
    ap.add_argument("--sample", type=float, default=0.20)
    ap.add_argument("--min-sample", type=int, default=50)
    ap.add_argument("--max-sample", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261109)
    a = ap.parse_args()

    files = sorted(glob.glob(str(RAW / f"{a.run}_*.csv")) + glob.glob(str(RAW / f"{a.run}_*.bib")))
    if a.database == "api":   # an API run "<date>_pN" must not also pick up "<date>_pN_ieee_1.csv" and the like
        files = [f for f in files if re.fullmatch(re.escape(a.run) + r"_(arxiv|openalex|semanticscholar)\.csv", Path(f).name)]
    if not files:
        sys.exit(f"no raw files matching data/raw/{a.run}_*.csv or .bib")
    records, seen = [], {}
    for f in files:
        for r in reader_for(f)(f):
            # within-run dedup across databases: keep the first, remember the others' sources
            keys = [r["record_id"]] + ([f"arxiv:{r['arxiv_id']}"] if r["arxiv_id"] else []) + ["t:" + norm_title(r["title"])]
            hit = next((seen[k] for k in keys if k in seen), None)
            if hit is not None:
                if r["database"] not in hit["database"]:
                    hit["database"] += ";" + r["database"]
                continue
            for k in keys:
                seen[k] = r
            records.append(r)

    prior = prior_index(a.run)
    papers_idx = {k for k, v in prior.items() if v.startswith("paper:")}
    for p in csv.DictReader(open(ROOT / "data" / "papers.csv", newline="", encoding="utf-8")):
        d = p["doi_or_arxiv"].strip().lower()
        papers_idx.update(k for k in (f"doi:{d}" if d.startswith("10.") else "", "t:" + norm_title(p["title"])) if k)
    for r in records:
        r["pillar"] = a.pillar
        if a.database != "api":
            r["database"] = a.database
        keys = [r["record_id"], f"arxiv:{r['arxiv_id']}" if r["arxiv_id"] else "", "t:" + norm_title(r["title"])]
        dup = next((prior[k] for k in keys if k and k in prior), "")
        r["duplicate_of"] = dup
        r["in_review"] = "yes" if dup.startswith("paper:") or any(k and k in papers_idx for k in keys) else ""
        r.setdefault("arxiv_id", "")

    OUT.mkdir(exist_ok=True)
    with open(OUT / f"{a.run}_records.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows({k: r.get(k, "") for k in COLS} for r in records)
    new = [r for r in records if not r["duplicate_of"]]
    print(f"{len(records)} unique records from {len(files)} files; {len(records) - len(new)} duplicates of earlier runs or included papers; {len(new)} to screen -> {OUT / (a.run + '_records.csv')}")

    if a.blind:
        n_draw = min(len(new), max(a.min_sample, round(len(new) * a.sample)))
        rng = random.Random(a.seed)
        sample = rng.sample(new, n_draw)[: min(n_draw, a.max_sample)]
        sample.sort(key=lambda r: (r["year"], r["title"]))
        with open(OUT / f"{a.run}_blind.csv", "w", newline="", encoding="utf-8") as f:
            f.write(f"# blind dual-screen sample: {len(sample)} of {len(new)} records (first {len(sample)} of a {n_draw}-record draw, seed {a.seed}, cap {a.max_sample})\n")
            w = csv.DictWriter(f, fieldnames=["record_id", "title", "year", "venue", "abstract", "url", "human_decision", "exclusion_code", "notes"])
            w.writeheader(); w.writerows({k: r.get(k, "") for k in w.fieldnames} for r in sample)
        print(f"{len(sample)} blind-sample records -> {OUT / (a.run + '_blind.csv')}")


if __name__ == "__main__":
    main()

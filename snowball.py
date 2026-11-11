"""Backward and forward citation chasing on the included set (protocol: PRISMA-S snowballing).

The review's method commits to snowballing "backward and forward via Semantic Scholar and OpenAlex
on the included set after each quarterly pass", stopping when a full pass adds fewer than five
papers. This script performs one pass.

Seeds are every paper in data/papers.csv plus every record excluded E3 (survey or tutorial, kept
for snowballing by protocol). Backward chasing takes each seed's references; forward chasing takes
the works citing it. Records are written in the same normalised format search.py produces, so
ingest.py reads them unchanged and dedups them against every earlier run.

Neither api.semanticscholar.org nor api.openalex.org is reachable from the maintainer's container;
this runs in GitHub Actions like search.py. Set S2_API_KEY for a usable Semantic Scholar rate limit.

Run with --count-only first: forward citation counts are unbounded in principle and the volume
decides whether a cap is needed before a pass is worth screening.
"""
import argparse, csv, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, RAW = ROOT / "data", ROOT / "data" / "raw"
COLS = ["record_id", "title", "authors", "year", "venue", "type", "doi", "url", "abstract", "arxiv_id", "database"]
S2 = "https://api.semanticscholar.org/graph/v1"
OA = "https://api.openalex.org"
FIELDS = "title,abstract,year,venue,externalIds,authors.name,publicationTypes"
MAILTO = "agent-precog@dewar.cloud"


def get(url, headers=None, retries=5, pause=3.0):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": f"agent-precog ({MAILTO})"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            if e.code == 404:
                return None
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            raise
    return None


def seeds():
    """Included papers plus E3 surveys held back for snowballing."""
    out = {}
    for p in csv.DictReader(open(DATA / "papers.csv", newline="", encoding="utf-8")):
        d = (p.get("doi_or_arxiv") or "").strip().lower()
        if d and not d.startswith("10."):
            out.setdefault(("arxiv", d), p["title"])
        elif d:
            out.setdefault(("doi", d), p["title"])
    cur = {}
    for d in csv.DictReader(open(DATA / "decisions.csv", newline="", encoding="utf-8")):
        cur[(d["record_id"], d["stage"])] = d
    e3 = {k[0] for k, d in cur.items()
          if (d["exclusion_code"] == "E3") or (not d["human_decision"] and d["ai_code"] == "E3")}
    for rid in e3:
        if rid.startswith("doi:"):
            out.setdefault(("doi", rid[4:].lower()), "")
    return out


def s2_id(kind, value):
    return f"DOI:{value}" if kind == "doi" else f"ARXIV:{value}"


def norm(rec, database):
    ext = rec.get("externalIds") or {}
    doi = (ext.get("DOI") or "").lower()
    arx = ext.get("ArXiv") or ""
    rid = f"doi:{doi}" if doi else (f"arxiv:{arx}" if arx else "s2:" + str(rec.get("paperId", ""))[:16])
    types = rec.get("publicationTypes") or []
    return {"record_id": rid, "title": (rec.get("title") or "").strip(),
            "authors": "; ".join(a.get("name", "") for a in (rec.get("authors") or [])),
            "year": str(rec.get("year") or ""), "venue": (rec.get("venue") or "").strip(),
            "type": "Conference" if "Conference" in types else ("Journal" if "JournalArticle" in types else ""),
            "doi": doi, "url": f"https://doi.org/{doi}" if doi else (f"https://arxiv.org/abs/{arx}" if arx else ""),
            "abstract": (rec.get("abstract") or "").replace("\n", " ").strip(),
            "arxiv_id": arx, "database": database}


def chase(kind, value, direction, key, cap, min_year):
    """One seed, one direction. Returns normalised records."""
    headers = {"User-Agent": f"agent-precog ({MAILTO})"}
    if key: headers["x-api-key"] = key
    out, offset = [], 0
    while True:
        url = (f"{S2}/paper/{s2_id(kind, value)}/{direction}"
               f"?fields={urllib.parse.quote(FIELDS)}&limit=100&offset={offset}")
        page = get(url, headers)
        if not page or not page.get("data"):
            break
        for item in page["data"]:
            rec = item.get("citedPaper") if direction == "references" else item.get("citingPaper")
            if not rec or not rec.get("title"):
                continue
            y = rec.get("year") or 0
            if min_year and y and int(y) < min_year:
                continue
            out.append(norm(rec, "Semantic Scholar (snowball)"))
        offset += 100
        if cap and len(out) >= cap:
            out = out[:cap]; break
        if len(page["data"]) < 100 or offset >= 9900:
            break
        time.sleep(0.4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=time.strftime("%Y-%m-%d") + "_snowball")
    ap.add_argument("--pillar", default="1")
    ap.add_argument("--direction", default="both", choices=["backward", "forward", "both"])
    ap.add_argument("--cap", type=int, default=0, help="max records per seed per direction; 0 means no cap")
    ap.add_argument("--min-year", type=int, default=2015)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--limit-seeds", type=int, default=0)
    a = ap.parse_args()

    key = os.environ.get("S2_API_KEY", "")
    if not key:
        print("no S2_API_KEY set; the anonymous pool is shared and will usually answer 429", flush=True)
    sd = seeds()
    items = sorted(sd)
    if a.limit_seeds:
        items = items[:a.limit_seeds]
    dirs = {"backward": ["references"], "forward": ["citations"], "both": ["references", "citations"]}[a.direction]
    print(f"{len(items)} seeds, directions {dirs}, min year {a.min_year}, cap {a.cap or 'none'}", flush=True)

    found, per_dir, failed = {}, {d: 0 for d in dirs}, 0
    for i, (kind, value) in enumerate(items, 1):
        for d in dirs:
            try:
                recs = chase(kind, value, d, key, a.cap, a.min_year)
            except Exception as e:
                failed += 1; print(f"  seed {value} {d}: {e}", flush=True); continue
            per_dir[d] += len(recs)
            for r in recs:
                found.setdefault(r["record_id"], r)
            time.sleep(0.4 if key else 3.0)
        if i % 10 == 0 or i == len(items):
            print(f"  {i}/{len(items)} seeds; {len(found)} unique records so far", flush=True)

    print(f"\nunique records found: {len(found)}")
    for d in dirs:
        print(f"  {d}: {per_dir[d]} (before dedup)")
    if failed:
        print(f"  {failed} seed/direction lookups failed")
    if a.count_only:
        print("\ncount-only: nothing written")
        return
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"{a.run}_s2.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in found.values():
            w.writerow({k: r.get(k, "") for k in COLS})
    print(f"wrote {out}")
    log = DATA / "search_log.csv"
    rows = list(csv.DictReader(open(log, newline="", encoding="utf-8")))
    with open(log, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            time.strftime("%Y-%m-%d"), a.pillar, "Snowballing (Semantic Scholar)",
            f"citation chasing, direction {a.direction}, on {len(items)} seeds (included papers plus E3 surveys)",
            f"min year {a.min_year}; cap {a.cap or 'none'} per seed per direction",
            str(len(found)), "script",
            "backward and forward citation chasing per the published protocol; seeds are the included set "
            "plus records excluded E3 and kept for snowballing"])
    print("logged to search_log.csv")


if __name__ == "__main__":
    main()

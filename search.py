#!/usr/bin/env python3
"""Run a pillar's search string against the open bibliographic APIs and write normalised records.

    python3 search.py --pillar 1 --databases arxiv,openalex,semanticscholar --count-only
    python3 search.py --pillar 1 --databases arxiv,openalex,semanticscholar --run 2026-11-15_p1

Reads  data/pillars.json                   (the per-pillar boolean query, written for IEEE Xplore)
Writes data/raw/<run>_<db>.csv              normalised rows: record_id,title,authors,year,venue,type,doi,url,abstract,database
       data/search_log.csv                  one appended row per database (date, pillar, database, query as sent, filters, hits)

The IEEE-style query is translated per API: wildcards are expanded (the APIs do not all support them), phrase quotes
are kept, and the date floor (2015) is applied through each API's own filter. The translated string is what is logged,
so the search is reproducible exactly as run.

Network: arXiv (export.arxiv.org, no key), OpenAlex (api.openalex.org, optional OPENALEX_MAILTO for the polite pool),
Semantic Scholar (api.semanticscholar.org, optional S2_API_KEY). All three are rate-limited; this script is deliberately
slow (one request every few seconds) and must not be parallelised against any of them.
"""
import argparse, csv, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
DATA, RAW = ROOT / "data", ROOT / "data" / "raw"
YEAR_FROM = 2015
UA = "agent-precog.org living review (https://agent-precog.org; search.py)"

# wildcard expansions: the IEEE string uses trailing * which arXiv and OpenAlex do not support
EXPAND = {
    "catastroph*": ["catastrophe", "catastrophic", "catastrophes"],
    "robot*": ["robot", "robots", "robotic", "robotics"],
    "tool call*": ["tool call", "tool calls", "tool calling", "tool-calling"],
    "LLM agent*": ["LLM agent", "LLM agents", "LLM-agent"],
    "Poincar*": ["Poincare", "Poincaré"],
    "predict*": ["predict", "predicts", "prediction", "predictive", "predicting"],
    "shield*": ["shield", "shields", "shielding", "shielded"],
    "runtime monitor*": ["runtime monitor", "runtime monitoring", "runtime monitors"],
    "quantiz*": ["quantization", "quantisation", "quantized", "quantised"],
    "agent*": ["agent", "agents", "agentic"],
}


def expand(query):
    """Replace each quoted wildcard term by an OR-group of its expansions."""
    def rep(m):
        term = m.group(1)
        if term in EXPAND:
            return "(" + " OR ".join(f'"{t}"' for t in EXPAND[term]) + ")"
        if term.endswith("*"):
            sys.exit(f"no expansion defined for wildcard term {term!r}; add it to EXPAND")
        return f'"{term}"'
    return re.sub(r'"([^"]+)"', rep, query)


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get(url, headers=None, retries=4, pause=3.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(pause * (2 ** attempt)); continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(pause * (2 ** attempt)); continue
            raise


# ---------------------------------------------------------------- arXiv
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv_query(query):
    # arXiv's API: fielded terms, AND/OR/ANDNOT, phrases in quotes. Search title+abstract via all: on each phrase.
    q = expand(query).replace(" OR ", " OR ").replace(" AND ", " AND ")
    q = re.sub(r'"([^"]+)"', lambda m: 'all:"' + m.group(1) + '"', q)
    return q + f" AND submittedDate:[{YEAR_FROM}01010000 TO 209912312359]"


def arxiv(query, count_only):
    q = arxiv_query(query)
    rows, start, total = [], 0, None
    while True:
        url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": q, "start": start, "max_results": 200, "sortBy": "submittedDate", "sortOrder": "descending"})
        root = ET.fromstring(get(url))
        total = int(root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults").text)
        if count_only:
            return q, total, []
        entries = root.findall("a:entry", ATOM)
        if not entries:
            break
        for e in entries:
            aid = e.find("a:id", ATOM).text.rsplit("/", 1)[-1]
            aid = re.sub(r"v\d+$", "", aid)
            doi_el = e.find("arxiv:doi", ATOM)
            doi = (doi_el.text or "").strip().lower() if doi_el is not None else ""
            rows.append({
                "record_id": f"doi:{doi}" if doi else f"arxiv:{aid}",
                "title": clean(e.find("a:title", ATOM).text),
                "authors": "; ".join(clean(a.find("a:name", ATOM).text) for a in e.findall("a:author", ATOM)),
                "year": (e.find("a:published", ATOM).text or "")[:4],
                "venue": "arXiv " + (e.find("arxiv:primary_category", ATOM).get("term") if e.find("arxiv:primary_category", ATOM) is not None else ""),
                "type": "preprint", "doi": doi, "url": f"https://arxiv.org/abs/{aid}",
                "abstract": clean(e.find("a:summary", ATOM).text), "arxiv_id": aid, "database": "arXiv",
            })
        start += 200
        if start >= total:
            break
        time.sleep(3.0)
    return q, total, rows


# ---------------------------------------------------------------- OpenAlex
def openalex_query(query):
    # OpenAlex search filters accept AND/OR/NOT, parentheses and quoted phrases; no wildcards.
    return expand(query)


def openalex(query, count_only):
    q = openalex_query(query)
    mailto = os.environ.get("OPENALEX_MAILTO", "")
    base = {"filter": f"title_and_abstract.search:{q},publication_year:{YEAR_FROM}-2099",
            "per_page": 200, "select": "id,doi,title,display_name,publication_year,authorships,primary_location,type,abstract_inverted_index,ids"}
    if mailto:
        base["mailto"] = mailto
    rows, cursor, total = [], "*", None
    while cursor:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode({**base, "cursor": cursor})
        d = json.loads(get(url))
        total = d["meta"]["count"]
        if count_only:
            return q, total, []
        for w in d["results"]:
            inv = w.get("abstract_inverted_index") or {}
            words = sorted(((pos, t) for t, poss in inv.items() for pos in poss))
            abstract = " ".join(t for _, t in words)
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            arx = ""
            for loc in [w.get("primary_location") or {}]:
                u = (loc.get("landing_page_url") or "") + " " + (loc.get("pdf_url") or "")
                m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", u)
                if m: arx = m.group(1)
            src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
            rows.append({
                "record_id": f"doi:{doi}" if doi else (f"arxiv:{arx}" if arx else "openalex:" + w["id"].rsplit("/", 1)[-1]),
                "title": clean(w.get("title") or w.get("display_name") or ""),
                "authors": "; ".join(clean((a.get("author") or {}).get("display_name", "")) for a in w.get("authorships", [])),
                "year": str(w.get("publication_year") or ""), "venue": clean(src), "type": w.get("type", ""),
                "doi": doi, "url": f"https://doi.org/{doi}" if doi else (w.get("primary_location") or {}).get("landing_page_url", "") or w["id"],
                "abstract": clean(abstract), "arxiv_id": arx, "database": "OpenAlex",
            })
        cursor = d["meta"].get("next_cursor")
        time.sleep(1.0)
    return q, total, rows


# ---------------------------------------------------------------- Semantic Scholar
def s2_query(query):
    # bulk search syntax: + for AND, | for OR, quotes for phrases, * prefix wildcard supported
    q = query.replace(" AND ", " + ").replace(" OR ", " | ")
    return q


def semanticscholar(query, count_only):
    q = s2_query(query)
    key = os.environ.get("S2_API_KEY", "")
    headers = {"x-api-key": key} if key else {}
    fields = "externalIds,title,authors,year,venue,publicationTypes,abstract,url"
    rows, token, total = [], None, None
    while True:
        params = {"query": q, "year": f"{YEAR_FROM}-", "fields": fields}
        if token: params["token"] = token
        url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk?" + urllib.parse.urlencode(params)
        d = json.loads(get(url, headers=headers, pause=5.0))
        total = d.get("total", 0)
        if count_only:
            return q, total, []
        for p in d.get("data", []):
            ext = p.get("externalIds") or {}
            doi = (ext.get("DOI") or "").lower(); arx = ext.get("ArXiv") or ""
            rows.append({
                "record_id": f"doi:{doi}" if doi else (f"arxiv:{arx}" if arx else "s2:" + p["paperId"]),
                "title": clean(p.get("title")), "authors": "; ".join(clean(a.get("name", "")) for a in p.get("authors") or []),
                "year": str(p.get("year") or ""), "venue": clean(p.get("venue")), "type": ";".join(p.get("publicationTypes") or []),
                "doi": doi, "url": f"https://doi.org/{doi}" if doi else p.get("url", ""),
                "abstract": clean(p.get("abstract")), "arxiv_id": arx, "database": "Semantic Scholar",
            })
        token = d.get("token")
        if not token:
            break
        time.sleep(1.5)
    return q, total, rows


DBS = {"arxiv": arxiv, "openalex": openalex, "semanticscholar": semanticscholar}
COLS = ["record_id", "title", "authors", "year", "venue", "type", "doi", "url", "abstract", "arxiv_id", "database"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar", type=int, required=True)
    ap.add_argument("--databases", default="arxiv,openalex,semanticscholar")
    ap.add_argument("--run", help="run id used in file names, e.g. 2026-11-15_p1 (default: today_p<pillar>)")
    ap.add_argument("--count-only", action="store_true", help="report hit counts without downloading records")
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    pillar = next(p for p in json.loads((DATA / "pillars.json").read_text(encoding="utf-8")) if p["n"] == a.pillar)
    run = a.run or f"{a.date}_p{a.pillar}"
    RAW.mkdir(exist_ok=True)
    summary = {}
    failures = 0
    for db in [d.strip() for d in a.databases.split(",") if d.strip()]:
        try:
            q, total, rows = DBS[db](pillar["query"], a.count_only)
        except Exception as e:  # one API being down or rejecting the query must not lose the others
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = " | body: " + e.read()[:500].decode("utf-8", "replace").replace("\n", " ")
                except Exception:
                    pass
            summary[db] = {"error": f"{type(e).__name__}: {e}{detail}"}
            print(f"{db}: FAILED {type(e).__name__}: {e}{detail}", flush=True)
            failures += 1
            continue
        summary[db] = {"query": q, "hits": total, "downloaded": len(rows)}
        print(f"{db}: {total} hits" + ("" if a.count_only else f", {len(rows)} records -> data/raw/{run}_{db}.csv"), flush=True)
        if a.count_only:
            print(f"    query as sent: {q}", flush=True)
        if not a.count_only:
            with open(RAW / f"{run}_{db}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows({k: r.get(k, "") for k in COLS} for r in rows)
            with open(DATA / "search_log.csv", "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([a.date, a.pillar, {"arxiv": "arXiv", "openalex": "OpenAlex", "semanticscholar": "Semantic Scholar"}[db], q,
                                        f"year {YEAR_FROM} onward; title and abstract (arXiv: all fields)", total, "search.py",
                                        f"{len(rows)} records downloaded; run {run}"])
    (RAW / f"{run}_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    if failures:
        sys.exit(f"{failures} of {len(summary)} databases failed")


if __name__ == "__main__":
    main()

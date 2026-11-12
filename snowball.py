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


class ApiError(Exception):
    """An HTTP error that carries the server's own explanation, which is the whole point."""
    def __init__(self, code, body, url):
        self.code, self.body, self.url = code, body, url
        super().__init__(f"HTTP {code}: {body[:300] or '(empty body)'}")


def get(url, headers=None, retries=5, pause=3.0):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": f"agent-precog ({MAILTO})"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # the body of a 4xx from Semantic Scholar says what is actually wrong; discarding it
            # turns a one-minute diagnosis into an hour-long guess
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            if e.code == 404:
                return None
            raise ApiError(e.code, body, url)
        except Exception:
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            raise
    return None


def post(url, payload, headers=None, retries=5, pause=3.0):
    data = json.dumps(payload).encode()
    hdrs = dict(headers or {}, **{"Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try: body = e.read().decode("utf-8", "replace")
            except Exception: body = ""
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            raise ApiError(e.code, body, url)
        except Exception:
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1)); continue
            raise
    return None


def resolve(ids, headers, chunk=500):
    """Map external identifiers to Semantic Scholar paperIds.

    A DOI contains a slash, so putting one in the URL path splits the route and the request is
    answered 404 or 400 - which is what silently defeated the first snowball pass. paperIds are
    alphanumeric, so the edge endpoints can be addressed safely. This also replaces one lookup per
    seed with one call per 500.
    """
    out = {}
    for i in range(0, len(ids), chunk):
        part = ids[i:i + chunk]
        r = post(f"{S2}/paper/batch?fields=paperId,title", {"ids": part}, headers)
        for given, got in zip(part, r or []):
            if got and got.get("paperId"):
                out[given] = got["paperId"]
        time.sleep(1.2)
    return out



# ---------------------------------------------------------------- OpenAlex
# The protocol names Semantic Scholar and OpenAlex. OpenAlex is the primary source here: it
# answers reliably where S2 throttles even an authenticated caller, it carries referenced_works
# on the work object so backward chasing needs no per-paper endpoint, and identifiers go in query
# parameters rather than the URL path, which is what broke the first implementation.

def oa_params(extra):
    p = dict(extra)
    mail = os.environ.get("OPENALEX_MAILTO", "") or MAILTO
    if mail: p["mailto"] = mail
    return p


def oa_get(params, retries=5, pause=3.0):
    url = f"{OA}/works?" + urllib.parse.urlencode(oa_params(params))
    return get(url, {"User-Agent": f"agent-precog ({MAILTO})"}, retries, pause)


SELECT = "id,doi,title,display_name,publication_year,type,authorships,primary_location,abstract_inverted_index,referenced_works"


def oa_norm(w):
    inv = w.get("abstract_inverted_index") or {}
    words = sorted(((pos, t) for t, poss in inv.items() for pos in poss))
    abstract = " ".join(t for _, t in words)
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    loc = w.get("primary_location") or {}
    u = (loc.get("landing_page_url") or "") + " " + (loc.get("pdf_url") or "")
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", u)
    arx = m.group(1) if m else ""
    src = (loc.get("source") or {}).get("display_name", "") or ""
    return {"record_id": f"doi:{doi}" if doi else (f"arxiv:{arx}" if arx else "openalex:" + w["id"].rsplit("/", 1)[-1]),
            "title": (w.get("title") or w.get("display_name") or "").strip(),
            "authors": "; ".join((a.get("author") or {}).get("display_name", "") for a in w.get("authorships", [])),
            "year": str(w.get("publication_year") or ""), "venue": src, "type": w.get("type", "") or "",
            "doi": doi, "url": f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w["id"]),
            "abstract": abstract.replace("\n", " ").strip(), "arxiv_id": arx, "database": "OpenAlex (snowball)"}


def oa_resolve(items, prov=None, chunk=40):
    """Seeds to OpenAlex works. Returns {work_id: work}; referenced_works comes free on each.

    items is a list of (kind, id). arXiv preprints are indexed under their registered DOI
    (10.48550/arXiv.NNNN.NNNNN), so they resolve the same way rather than being skipped.
    Each resolved work carries _provenance, so forward chasing can be restricted to papers that
    are in scope rather than to the foundations they rest on.
    """
    prov = prov or {}
    want = {}
    for kind, v in items:
        d = (v if kind == "doi" else f"10.48550/arxiv.{v}").lower()
        want[d] = prov.get((kind, v), "search")
    out, keys = {}, list(want)
    for i in range(0, len(keys), chunk):
        part = keys[i:i + chunk]
        d = oa_get({"filter": "doi:" + "|".join(part), "per-page": len(part), "select": SELECT})
        for w in (d or {}).get("results", []):
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            w["_provenance"] = want.get(doi, "search")
            out[w["id"]] = w
        time.sleep(0.5)
    return out


def oa_fetch_ids(ids, min_year, chunk=40):
    """Hydrate OpenAlex work ids into records."""
    out = []
    ids = [i for i in ids if i]
    for i in range(0, len(ids), chunk):
        part = [x.rsplit("/", 1)[-1] for x in ids[i:i + chunk]]
        f = "openalex_id:" + "|".join(part)
        if min_year: f += f",from_publication_date:{min_year}-01-01"
        d = oa_get({"filter": f, "per-page": len(part), "select": SELECT})
        out += [oa_norm(w) for w in (d or {}).get("results", [])]
        time.sleep(0.5)
    return out


def oa_citing(work_id, min_year, cap):
    """Works citing this one. Page-based paging: cursor paging now needs a paid key."""
    wid = work_id.rsplit("/", 1)[-1]
    out, page = [], 1
    while True:
        f = f"cites:{wid}"
        if min_year: f += f",from_publication_date:{min_year}-01-01"
        d = oa_get({"filter": f, "per-page": 200, "page": page, "select": SELECT})
        res = (d or {}).get("results", [])
        out += [oa_norm(w) for w in res]
        if len(res) < 200 or (cap and len(out) >= cap) or page * 200 >= 10000:
            break
        page += 1
        time.sleep(0.5)
    return out[:cap] if cap else out


def probe(key):
    """Check the path the pass actually uses, cheaply, before committing to a full run.

    Two passes were lost to untestable code: the first put DOIs in the URL path, where the slash
    splits the route, and the second hit Semantic Scholar's limiter even with a valid key. The
    pass now runs on OpenAlex, so this verifies that path end to end on one known paper.
    """
    doi = "10.1038/nature14539"       # LeCun, Bengio and Hinton, Deep learning, Nature 2015
    print(f"OpenAlex mailto: {os.environ.get('OPENALEX_MAILTO','') or MAILTO}")
    print("\n1. resolve a known DOI")
    try:
        works = oa_resolve([("doi", doi)])
    except Exception as e:
        print(f"   FAIL {type(e).__name__}: {e}"); return
    if not works:
        print("   FAIL resolved nothing; OpenAlex is unreachable or the filter is wrong"); return
    wid, w = next(iter(works.items()))
    refs = w.get("referenced_works") or []
    print(f"   OK   {wid} | {len(refs)} referenced works on the object")

    print("\n2. backward: hydrate a few references")
    try:
        recs = oa_fetch_ids(refs[:5], 0)
        print(f"   OK   {len(recs)} records" + (f" | e.g. {recs[0]['title'][:60]}" if recs else ""))
    except Exception as e:
        print(f"   FAIL {type(e).__name__}: {e}")

    print("\n3. forward: works citing it, capped")
    try:
        recs = oa_citing(wid, 2015, 5)
        print(f"   OK   {len(recs)} records" + (f" | e.g. {recs[0]['title'][:60]}" if recs else ""))
    except Exception as e:
        print(f"   FAIL {type(e).__name__}: {e}")

    print("\n4. Semantic Scholar, for reference only (the protocol names it; OpenAlex is primary)")
    raw = (key or "").strip()
    hdrs = {"User-Agent": f"agent-precog ({MAILTO})"}
    if raw: hdrs["x-api-key"] = raw
    try:
        r = get(f"{S2}/paper/search?query=deep+learning&limit=1&fields=title", hdrs, retries=3, pause=5.0)
        print(f"   OK   key works: {len((r or {}).get('data', []))} records")
    except ApiError as e:
        print(f"   {e.code}  throttled even with the key; this is why OpenAlex is primary")


def seeds():
    """Included papers plus E3 surveys held back for snowballing.

    Returns {(kind, id): provenance}, where provenance is "seed" for the hand-curated foundations,
    "search" for papers the database searches found, and "e3" for surveys kept for snowballing.
    Forward chasing is restricted by provenance: the foundations are cited by entire fields that
    are not this review, so their reference lists are useful while the literature citing them is
    overwhelmingly noise.
    """
    out = {}
    for p in csv.DictReader(open(DATA / "papers.csv", newline="", encoding="utf-8")):
        d = (p.get("doi_or_arxiv") or "").strip().lower()
        prov = "seed" if p.get("included_via") == "seed" else "search"
        if d and not d.startswith("10."):
            # papers.csv writes these as "arXiv:2401.00001"; store the bare id
            out.setdefault(("arxiv", d.split(":", 1)[-1].strip()), prov)
        elif d:
            out.setdefault(("doi", d), prov)
    cur = {}
    for d in csv.DictReader(open(DATA / "decisions.csv", newline="", encoding="utf-8")):
        cur[(d["record_id"], d["stage"])] = d
    e3 = {k[0] for k, d in cur.items()
          if (d["exclusion_code"] == "E3") or (not d["human_decision"] and d["ai_code"] == "E3")}
    for rid in e3:
        if rid.startswith("doi:"):
            out.setdefault(("doi", rid[4:].lower()), "e3")
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


def chase(paper_id, direction, headers, cap, min_year):
    """One seed, one direction, addressed by Semantic Scholar paperId. Returns normalised records."""
    out, offset = [], 0
    while True:
        url = (f"{S2}/paper/{paper_id}/{direction}"
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
    ap.add_argument("--forward-from", default="in-scope", choices=["in-scope", "all", "search-only"],
                    help="which seeds to chase citations from: all, in-scope (excludes the hand-curated "
                         "foundations) or search-only (also excludes E3 surveys, whose citing literature is "
                         "as broad as the survey is well known)")
    ap.add_argument("--probe", action="store_true", help="try one known paper several ways and print what the API says")
    a = ap.parse_args()

    key = os.environ.get("S2_API_KEY", "")
    if a.probe:
        probe(key); return
    if not key:
        print("no S2_API_KEY set; the pass runs on OpenAlex, so this only affects the probe's last check", flush=True)
    sd = seeds()
    items = sorted(sd)
    if a.limit_seeds and a.limit_seeds < len(items):
        # evenly spaced across the set: the head is all arXiv ids and would not be representative
        step = len(items) / a.limit_seeds
        items = [items[int(i * step)] for i in range(a.limit_seeds)]
    dirs = {"backward": ["references"], "forward": ["citations"], "both": ["references", "citations"]}[a.direction]

    print(f"resolving {len(items)} seeds against OpenAlex...", flush=True)
    works = oa_resolve(items, prov=sd)
    print(f"resolved {len(works)} of {len(items)} seeds", flush=True)
    if not works:
        print("nothing resolved; stopping rather than reporting an empty pass as a result")
        sys.exit(1)
    print(f"{len(works)} seeds, directions {dirs}, min year {a.min_year}, cap {a.cap or 'none'}", flush=True)

    found, per_dir, failed = {}, {d: 0 for d in dirs}, 0
    yield_by_seed = {}

    if "references" in dirs:
        refs = []
        for w in works.values():
            refs += (w.get("referenced_works") or [])
        refs = list(dict.fromkeys(refs))
        print(f"backward: {len(refs)} distinct referenced works to hydrate", flush=True)
        for i in range(0, len(refs), 40):
            try:
                recs = oa_fetch_ids(refs[i:i + 40], a.min_year)
            except Exception as e:
                failed += 1
                if failed <= 5: print(f"  references chunk {i}: {e}", flush=True)
                continue
            per_dir["references"] += len(recs)
            for r in recs: found.setdefault(r["record_id"], r)
            if (i // 40) % 10 == 0:
                print(f"  backward {min(i + 40, len(refs))}/{len(refs)}; {len(found)} unique so far", flush=True)

    if "citations" in dirs:
        # the hand-curated foundations are cited by entire fields that are not this review, so
        # they seed the backward pass but not the forward one
        allowed = {"all": {"seed", "search", "e3"}, "in-scope": {"search", "e3"}, "search-only": {"search"}}[a.forward_from]
        wl = sorted(w for w, obj in works.items() if obj.get("_provenance", "search") in allowed)
        skipped = len(works) - len(wl)
        if skipped:
            print(f"forward: {len(wl)} seeds ({skipped} foundational seed-list papers excluded)", flush=True)
        for i, wid in enumerate(wl, 1):
            try:
                recs = oa_citing(wid, a.min_year, a.cap)
            except Exception as e:
                failed += 1
                if failed <= 5: print(f"  seed {wid} citations: {e}", flush=True)
                continue
            per_dir["citations"] += len(recs)
            yield_by_seed[wid] = len(recs)
            for r in recs: found.setdefault(r["record_id"], r)
            if i % 10 == 0 or i == len(wl):
                print(f"  forward {i}/{len(wl)} seeds; {len(found)} unique so far", flush=True)

    # drop anything that is itself a seed
    seed_ids = {f"doi:{v}" for k, v in items if k == "doi"} | {f"arxiv:{v}" for k, v in items if k == "arxiv"}
    for rid in list(found):
        if rid in seed_ids: del found[rid]

    if yield_by_seed:
        # the distribution matters more than the total: a cap should be set from where the mass is
        top = sorted(yield_by_seed.items(), key=lambda kv: -kv[1])[:12]
        tot = sum(yield_by_seed.values()) or 1
        print("\nheaviest forward seeds (these decide whether a cap is needed):")
        for wid, n in top:
            w = works.get(wid, {})
            print(f"  {n:6}  {w.get('_provenance','?'):6}  {(w.get('title') or w.get('display_name') or wid)[:62]}")
        head = sum(n for _, n in top)
        print(f"  the 12 heaviest account for {head} of {tot} forward records ({100*head//tot}%)")
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

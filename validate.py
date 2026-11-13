"""Integrity checks for the review's CSVs. Run in CI and before any release.

Every check here exists because the corresponding defect actually occurred. The comment on each
says which, so nobody later removes a check thinking it is hypothetical.
"""
import csv, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
GAP_CELLS = {"multi-agent state", "non-generative inference", "latency/jitter aware",
             "time-to-irreversibility", "edge deployment", "human handoff", "cross-domain evaluation"}
CODES = {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}
STAGES = {"title_abstract", "title_abstract_2", "full_text"}
BAD_CHARS = {"·": "middle dot", "–": "en dash", "—": "em dash"}

errors, warnings = [], []
def err(m): errors.append(m)
def warn(m): warnings.append(m)
def rows(name): return list(csv.DictReader(open(DATA / name, newline="", encoding="utf-8")))


def check_papers():
    ps = rows("papers.csv")
    ids = Counter(p["id"] for p in ps)
    for k, n in ids.items():
        if n > 1: err(f"papers.csv: id {k!r} used {n} times")
    dois = Counter(p["doi_or_arxiv"].lower() for p in ps if p["doi_or_arxiv"].strip())
    for k, n in dois.items():
        if n > 1: err(f"papers.csv: doi {k!r} appears {n} times")
    for p in ps:
        # gap cell vocabulary: a drafting pass once invented a cell that was not in the published set
        for g in [x.strip() for x in p["gap_cells"].split(";") if x.strip()]:
            if g not in GAP_CELLS: err(f"papers.csv: {p['id']} has unknown gap cell {g!r}")
        # separators: gap_cells and methods mixed ';' and '; ' across runs
        for col in ("gap_cells", "methods"):
            if "; " in p[col] or p[col].strip() != p[col]:
                err(f"papers.csv: {p['id']} {col} separator not normalised: {p[col]!r}")
        for q in ("rq1", "rq2", "rq3", "rq4", "rq5"):
            if not (p[q].isdigit() and 0 <= int(p[q]) <= 5):
                err(f"papers.csv: {p['id']} {q}={p[q]!r} is not an integer 0-5")
        if p["baseline"] not in ("yes", "no"): err(f"papers.csv: {p['id']} baseline={p['baseline']!r}")
        if p["runtime_interceptor"] not in ("yes", "no"): err(f"papers.csv: {p['id']} runtime_interceptor={p['runtime_interceptor']!r}")
        if not p["methods"].strip(): warn(f"papers.csv: {p['id']} has no methods tags")
        # citekey built from the wrong name: ACM BibTeX writes 'Last, First' where IEEE writes 'F. Last'
        first = p["authors"].split(";")[0].strip()
        if "," in first:
            surname = first.split(",")[0].strip().split()[0].lower()
            surname = re.sub(r"[^a-z]", "", surname)
            if surname and not p["id"].startswith(surname):
                warn(f"papers.csv: {p['id']} may not match first author surname {surname!r} ({first[:40]})")
    return ps


def check_decisions(ps):
    ds = rows("decisions.csv")
    for d in ds:
        if d["stage"] not in STAGES: err(f"decisions.csv: {d['record_id']} unknown stage {d['stage']!r}")
        if d["human_decision"] not in ("", "include", "exclude"):
            err(f"decisions.csv: {d['record_id']} human_decision={d['human_decision']!r}")
        if d["human_decision"] == "include" and d["exclusion_code"]:
            err(f"decisions.csv: {d['record_id']} is an include but carries code {d['exclusion_code']!r}")
        if d["human_decision"] == "exclude" and d["exclusion_code"] not in CODES:
            err(f"decisions.csv: {d['record_id']} is an exclude with code {d['exclusion_code']!r}")
        if d["ai_label"] == "exclude" and d["ai_code"] and d["ai_code"] not in CODES:
            err(f"decisions.csv: {d['record_id']} ai_code={d['ai_code']!r}")
    # the current decision is the last row per (record, stage); a record decided both ways in one
    # returned sheet is what this catches
    cur = {}
    for d in ds: cur[(d["record_id"], d["stage"])] = d
    inc = {k[0] for k, d in cur.items() if k[1] == "full_text" and d["human_decision"] == "include"}
    # decisions are keyed by record_id, papers by DOI or arXiv id; resolve one to the other through
    # the screening records rather than assuming the two key forms coincide
    import glob
    recs = {}
    for path in glob.glob(str(DATA / "screening" / "*_records.csv")):
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            recs.setdefault(r["record_id"], r)
    def ident(r):
        d = (r.get("doi") or "").strip().lower()
        a = (r.get("arxiv_id") or "").strip().lower()
        return {f"doi:{d}" for _ in (1,) if d} | {f"arxiv:{a}" for _ in (1,) if a}
    inc_ident = set()
    for rid in inc:
        inc_ident |= ident(recs.get(rid, {})) or {rid}
    def pkeys(p):
        v = p["doi_or_arxiv"].strip().lower()
        if not v: return set()
        return {f"arxiv:{v.split(':', 1)[1]}"} if v.startswith("arxiv:") else {f"doi:{v}"}
    def nt(t): return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    bykey = {k for p in ps for k in pkeys(p)}
    bytitle = {nt(p["title"]) for p in ps}
    # a work can reach the review by two routes (an arXiv preprint and its published version), so the
    # decision's record_id and the paper's identifier need not coincide; fall back to the title
    inc_titles = {nt(recs[rid]["title"]) for rid in inc if rid in recs}
    for rid in sorted(inc):
        ids = ident(recs.get(rid, {})) or {rid}
        if not (ids & bykey) and nt(recs.get(rid, {}).get("title", "\x00")) not in bytitle:
            warn(f"decisions.csv: {rid} is a full-text include but is not in papers.csv")
    missing = [p["id"] for p in ps if p["included_via"] in ("search", "snowball")
               and pkeys(p) and not (pkeys(p) & inc_ident) and nt(p["title"]) not in inc_titles]
    if missing: warn(f"papers.csv: {len(missing)} search-included papers have no full-text include decision: {missing[:5]}")
    return ds


def check_coverage():
    """Every record that went to screening should carry a decision, and none should be unlabelled.

    A living-search run left 48 records with no decision row and 50 labelled 'unlabelled' after the
    model failed on them. Both are invisible in the PRISMA totals, which count records rather than
    decisions, so the flow can look complete while records have quietly fallen out of it.
    """
    import glob
    screened = set()
    for path in glob.glob(str(DATA / "screening" / "*_records.csv")):
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            if not r.get("duplicate_of"):
                screened.add(r["record_id"])
    decided, latest = set(), {}
    for d in rows("decisions.csv"):
        if d["stage"] in ("title_abstract", "title_abstract_2"):
            decided.add(d["record_id"])
            latest[d["record_id"]] = d  # the latest row for a record governs
    unlabelled = [i for i, d in latest.items()
                  if d["ai_label"] == "unlabelled" and not d["human_decision"]]
    missing = screened - decided
    if missing:
        warn(f"{len(missing)} screened records have no title/abstract decision: {sorted(missing)[:5]}")
    if unlabelled:
        warn(f"{len(unlabelled)} records are labelled 'unlabelled' with no maintainer decision: {sorted(set(unlabelled))[:5]}")


def check_log():
    for r in rows("search_log.csv"):
        for col in ("run_date", "pillar", "database", "query", "hits"):
            if not r[col].strip(): err(f"search_log.csv: {r['run_date']} {r['database']} has empty {col}")
        if not r["hits"].isdigit(): err(f"search_log.csv: {r['database']} hits={r['hits']!r} is not a number")


def check_typography(ps, ds):
    # published paper titles keep their own punctuation; our own prose must not use these characters
    for p in ps:
        for col in ("contribution", "methods", "gap_cells"):
            for ch, name in BAD_CHARS.items():
                if ch in p[col]: err(f"papers.csv: {p['id']} {col} contains a {name}")
    for d in ds:
        for ch, name in BAD_CHARS.items():
            if ch in d["notes"]: err(f"decisions.csv: {d['record_id']} notes contains a {name}")


def main():
    ps = check_papers()
    ds = check_decisions(ps)
    check_log()
    check_coverage()
    check_typography(ps, ds)
    print(f"{len(ps)} papers, {len(ds)} decision rows")
    for w in warnings: print("WARN ", w)
    for e in errors: print("ERROR", e)
    print(f"\n{len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

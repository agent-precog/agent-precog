#!/usr/bin/env python3
"""Build the agent-precog.ai static site from data/ into site/.

Usage: python3 build.py            # writes ./site
       python3 build.py --out dist # custom output directory

Requires: jinja2 (pip install jinja2). No other dependencies.
"""
import glob, re, argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from digest import build_digest

SITE_NAME = "agent-precog.org"
SITE_URL = "https://agent-precog.org"

ROOT = Path(__file__).parent
DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

GAP_COLUMNS = [
    ("multi-agent state", "Multi-agent state"),
    ("non-generative inference", "Non-generative inference"),
    ("latency/jitter aware", "Latency/jitter aware"),
    ("time-to-irreversibility", "Time-to-irreversibility"),
    ("edge deployment", "Edge deployment"),
    ("human handoff", "Human handoff"),
    ("cross-domain evaluation", "Cross-domain evaluation"),
]

RQS = [
    ("rq1", "RQ1", "Sub-15ms latent world-model interception"),
    ("rq2", "RQ2", "Jitter-adaptive sequential L2D"),
    ("rq3", "RQ3", "Dual-speed socio-technical handoff"),
    ("rq4", "RQ4", "Compositional generalisation"),
    ("rq5", "RQ5", "Incremental value over existing safeguards"),
]

# Which pillars feed each RQ (mirrors the "Fed by pillars" lists on the RQs page).
RQ_PILLARS = {"rq1": [1, 2, 4], "rq2": [3, 4], "rq3": [5, 3], "rq4": [1, 2], "rq5": [1, 3, 5]}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load():
    papers = read_csv(DATA / "papers.csv")
    for p in papers:
        p["pillar_list"] = [int(x) for x in str(p["pillar"]).split(";") if x.strip()]
        p["gap_list"] = [g.strip().lower() for g in p.get("gap_cells", "").split(";") if g.strip()]
        p["year"] = int(p["year"]) if p["year"] else None
        for k, _, _ in RQS:
            p[k] = int(p.get(k) or 0)
        p["relevance"] = max(p[k] for k, _, _ in RQS)
        p["baseline"] = str(p.get("baseline", "")).strip().lower() == "yes"
        p["methods_list"] = [m.strip() for m in p.get("methods", "").split(";") if m.strip()]
    pillars = json.loads((DATA / "pillars.json").read_text(encoding="utf-8"))
    search_log = read_csv(DATA / "search_log.csv")
    decisions = read_csv(DATA / "decisions.csv")
    version = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    changelog = read_csv(DATA / "changelog.csv") if (DATA / "changelog.csv").exists() else []
    return papers, pillars, search_log, decisions, version, changelog


def gap_claims(papers):
    """Counts behind the prose gap claims on the home page and the RQ page.

    These sentences used to be hardcoded, and went stale silently as papers entered the review:
    the RQ1 claim was false on the live site for two days after karthik2026self was included.
    They are computed here so a claim cannot outlive its evidence.
    """
    def cells(p):
        return {c.strip().lower() for c in p.get("gap_cells", "").split(";") if c.strip()}
    def n(pred):
        return sum(1 for p in papers if pred(p))
    return {
        "cross_domain": n(lambda p: "cross-domain evaluation" in cells(p)),
        "graph_edge": n(lambda p: {"multi-agent state", "non-generative inference", "edge deployment"} <= cells(p)),
        "defer_timing": n(lambda p: p.get("pillar") == "3" and cells(p) & {"latency/jitter aware", "time-to-irreversibility"}),
        "sa_interception": n(lambda p: p.get("pillar") == "5" and "latency/jitter aware" in cells(p)),
    }


def latest_decisions(decisions):
    """The current decision for each (record_id, stage), which is the last one logged.

    decisions.csv is an append-only audit log, so a record re-screened under a later protocol
    version has more than one row at the same stage. The counts must reflect the current rule,
    while the batch table on the methods page still shows every pass, superseded ones included.
    """
    cur = {}
    for d in decisions:
        cur[(d["record_id"], d["stage"])] = d
    return list(cur.values())


def prisma(papers, search_log, decisions):
    all_decisions = decisions                 # full audit log, for the batch table
    decisions = latest_decisions(decisions)   # current decision per record and stage, for the counts
    identified_db = sum(int(r["hits"] or 0) for r in search_log)
    other = sum(1 for p in papers if p["included_via"] not in ("search", "snowball"))
    # Records screened is counted from the records themselves, not by subtracting known duplicates
    # from the hit total. A run that queries several databases collapses heavily before ingest -
    # the three API searches returned 9,187 rows and 5,910 distinct records - and that collapse is
    # a duplicate removal too. Deriving it the other way silently overstated screening by 3,277.
    screened = 0
    for p in sorted(glob.glob(str(DATA / "screening" / "*_records.csv"))):
        screened += sum(1 for r in read_csv(Path(p)) if not r.get("duplicate_of"))
    dedup = max(identified_db - screened, 0)
    def ta_code(d):
        # protocol v1.3: the maintainer's decision governs; an AI exclusion with no human decision stands
        if d["human_decision"] == "exclude":
            return d["exclusion_code"]
        if d["human_decision"] == "" and d["ai_label"] == "exclude":
            return d["ai_code"]
        return None
    ta_excl = Counter(c for c in (ta_code(d) for d in decisions if d["stage"] in ("title_abstract", "title_abstract_2")) if c)
    ta2_excluded = sum(1 for d in decisions if d["stage"] == "title_abstract_2" and ta_code(d))
    ft_excl = Counter(d["exclusion_code"] for d in decisions if d["stage"] == "full_text" and d["human_decision"] == "exclude")
    # Full-text exclusions drafted by the AI from the paper and accepted by the maintainer in bulk rather
    # than read row by row. They are counted apart from the maintainer's own full-text decisions so the
    # flow never presents an accepted draft as a decision the maintainer made by reading the paper.
    ft_ai_excl = Counter(d["ai_code"] for d in decisions if d["stage"] == "full_text"
                         and not d["human_decision"] and d["ai_label"] == "exclude")
    ta_total = sum(ta_excl.values())
    ft_total = sum(ft_excl.values())
    return {
        "identified_db": identified_db,
        "identified_other": other,
        "duplicates": dedup,
        "screened": screened,
        "ta_excluded": ta_total,
        "ta_codes": dict(ta_excl),
        "full_text": max(screened - ta_total, 0),
        "ft_excluded": ft_total,
        "ft_codes": dict(ft_excl),
        "ft_ai_excluded": sum(ft_ai_excl.values()),
        "ft_ai_codes": dict(ft_ai_excl),
        "included": len(papers),
        "databases": len({r["database"] for r in search_log if not r["database"].startswith("Snowballing")}),
        "has_runs": bool(search_log),
        "search_included": sum(1 for p in papers if p["included_via"] in ("search", "snowball")),
        "snowball_included": sum(1 for p in papers if p["included_via"] == "snowball"),
        "ft_decided": sum(1 for d in decisions if d["stage"]=="full_text" and d["human_decision"] in ("include","exclude") and d["exclusion_code"] not in ("E3","E5")),
        "to_full_text": sum(1 for d in decisions if d["stage"] == "title_abstract" and (d["human_decision"] == "include" or (d["human_decision"] == "" and d["ai_label"] == "include"))) - ta2_excluded,
        "ta2_excluded": ta2_excluded,
        "pdf_requested": sum(1 for d in decisions if d["stage"] == "title_abstract_2" and d["human_decision"] == "include"),
        # records sitting at the full-text stage with no full-text decision yet
        "pending_publication": sum(1 for _ in read_csv(DATA / "screening" / "pending_publication.csv")) if (DATA / "screening" / "pending_publication.csv").exists() else 0,
        "awaiting_ft": len(
            {d["record_id"] for d in decisions if d["stage"] == "title_abstract"
             and (d["human_decision"] == "include" or (not d["human_decision"] and d["ai_label"] == "include"))}
            - {d["record_id"] for d in decisions if d["stage"] == "title_abstract_2"
               and not (d["human_decision"] == "include" or (not d["human_decision"] and d["ai_label"] == "include"))}
            - {d["record_id"] for d in decisions if d["stage"] == "full_text" and d["human_decision"] in ("include", "exclude")}
            - {d["record_id"] for d in decisions if d["stage"] == "full_text" and not d["human_decision"] and d["ai_label"] == "exclude"}
        ),
        "batches": screening_batches(all_decisions),
    }


def screening_batches(decisions):
    """Per-batch title/abstract screening statistics for the PRISMA-S page (protocol v1.3)."""
    batches = defaultdict(lambda: Counter())
    for d in decisions:
        if d["stage"] not in ("title_abstract", "title_abstract_2"):
            continue
        m = re.search(r"run (\S+?);", d["notes"] + ";")
        k = (d["pillar"], d["prompt_version"], m.group(1) if m else ("2026-11-09_p1_ieee" if d["prompt_version"].startswith("ta-screen") else ""))
        c = batches[k]
        c["records"] += 1
        cal = "calibration" in d["notes"]
        if d["ai_label"] == "include":
            c["ai_inc"] += 1
            if d["human_decision"] == "include":
                c["confirmed"] += 1
            elif d["human_decision"] == "exclude":
                c["overridden"] += 1
            elif not cal:
                c["pending"] += 1
        else:
            if "leak-check" in d["notes"]:
                c["leak_sample"] += 1
                if d["human_decision"] == "include":
                    c["leaks"] += 1
                elif d["human_decision"]:
                    c["leak_read"] += 1
        if cal:
            c["calibration"] += 1
    keys = ("records", "ai_inc", "confirmed", "overridden", "pending", "leak_sample", "leak_read", "leaks", "calibration")
    return [dict(pillar=p, prompt=v, run=run, **{k: c.get(k, 0) for k in keys}) for (p, v, run), c in sorted(batches.items())]


def gap_matrix(papers, pillars):
    cells = defaultdict(list)
    for p in papers:
        for n in p["pillar_list"]:
            for g in p["gap_list"]:
                cells[(n, g)].append(p)
    rows = []
    for pl in pillars:
        row = []
        for key, label in GAP_COLUMNS:
            ps = cells.get((pl["n"], key), [])
            c = len(ps)
            level = "gap" if c == 0 else "thin" if c <= 2 else "partial" if c <= 7 else "strong"
            row.append({"key": key, "label": label, "count": c, "level": level, "papers": ps})
        rows.append({"pillar": pl, "cells": row})
    gaps = [(pl, key, label) for pl in pillars for key, label in GAP_COLUMNS if not cells.get((pl["n"], key))]
    # Column totals across the whole review (a paper in two pillars counts once per column).
    totals = []
    for key, label in GAP_COLUMNS:
        n = len({p["id"] for p in papers if key in p["gap_list"]})
        totals.append({"key": key, "label": label, "count": n})
    # Tier 1: requirements no paper in any pillar addresses. Tier 2: a pillar that is otherwise well
    # populated (3+ papers) but has nothing on a requirement its neighbours cover - the integration gaps.
    empty_cols = {t["key"] for t in totals if t["count"] == 0}
    tier1 = [t for t in totals if t["count"] == 0]
    tier2 = [(pl, key, label) for pl, key, label in gaps if key not in empty_cols and pl["count"] >= 3]
    other = [(pl, key, label) for pl, key, label in gaps if key not in empty_cols and pl["count"] < 3]
    return rows, gaps, {"totals": totals, "tier1": tier1, "tier2": tier2, "other": other}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    out = ROOT / args.out

    papers, pillars, search_log, decisions, version, changelog = load()
    papers.sort(key=lambda p: (-p["relevance"], -(p["year"] or 0), p["title"]))
    by_pillar = {pl["n"]: [p for p in papers if pl["n"] in p["pillar_list"]] for pl in pillars}
    for pl in pillars:
        pl["count"] = len(by_pillar[pl["n"]])
    counts = prisma(papers, search_log, decisions)
    matrix, gaps, gapinfo = gap_matrix(papers, pillars)
    for pl in pillars:
        pl["feeds"] = [label for k, label, _ in RQS if pl["n"] in RQ_PILLARS[k]]
        pl["top_methods"] = [m for m, _ in Counter(m for p in by_pillar[pl["n"]] for m in p["methods_list"]).most_common(4)]
    recent = sorted(papers, key=lambda p: p["screened_on"], reverse=True)[:5]
    all_methods = sorted({m for p in papers for m in p["methods_list"]})
    by_id = {p["id"]: p for p in papers}
    by_rq = {k: sum(1 for p in papers if p[k] >= 3) for k, _, _ in RQS}
    last_search = max((r["run_date"] for r in search_log), default=None)
    agent_cfg = ROOT / "agent.json"
    agent_url = json.loads(agent_cfg.read_text()).get("url") if agent_cfg.exists() else None

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    ctx = dict(
        pillars=pillars, counts=counts, version=version, recent=recent, claims=gap_claims(papers),
        rqs=RQS, gap_columns=GAP_COLUMNS, matrix=matrix, gaps=gaps, gapinfo=gapinfo, rq_pillars=RQ_PILLARS,
        last_search=last_search, built=date.today().isoformat(),
        changelog=changelog, total=len(papers), all_methods=all_methods, by_id=by_id, by_rq=by_rq,
        agent_url=agent_url, site_name=SITE_NAME,
    )

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(STATIC, out / "static")
    (out / "data").mkdir()
    for f in ("papers.csv", "search_log.csv", "decisions.csv"):
        shutil.copy(DATA / f, out / "data" / f)

    def render(name, path, **extra):
        html = env.get_template(name).render(**ctx, **extra)
        p = out / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")

    render("index.html", "index.html")
    render("gap.html", "gap/index.html")
    render("methods.html", "prisma-s/index.html")
    render("rqs.html", "rqs/index.html")
    render("pillars.html", "pillars/index.html")
    render("changelog.html", "changelog/index.html")
    render("foundations.html", "foundations/index.html")
    render("papers.html", "papers/index.html", papers=papers, pillar=None)
    for pl in pillars:
        render("pillar.html", f"pillars/{pl['slug']}/index.html", pillar=pl, papers=by_pillar[pl["n"]],
               pillar_gaps=[c for row in matrix if row["pillar"]["n"] == pl["n"] for c in row["cells"] if c["level"] == "gap"])
    n = build_digest(out, site_name=SITE_NAME, site_url=SITE_URL, version=version, papers=papers, pillars=pillars,
                     rqs=RQS, gap_columns=GAP_COLUMNS, matrix=matrix, counts=counts, changelog=changelog)
    print(f"Built {len(papers)} papers, {len(pillars)} pillars into {out}; digest {n//1024} KB")


if __name__ == "__main__":
    main()

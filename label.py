#!/usr/bin/env python3
"""AI title/abstract labelling with a versioned prompt (protocol v1.3 onward).

    python3 label.py --run 2026-11-15_p1 --prompt ta-screen-v2 [--model eu.anthropic.claude-haiku-4-5-20251001-v1:0]

Reads  data/screening/<run>_records.csv          (skips rows with duplicate_of set)
       data/screening/prompts/<prompt>.md         the exact prompt text, which is the system message
Writes data/screening/<run>_ai_labels.csv         record_id,ai_label,ai_code,ai_reason,prompt_version,labelled_on
       data/decisions.csv                         one title_abstract row per labelled record (human columns blank)

Labels are normalised to include|exclude whatever the prompt's own vocabulary (v2 says likely-include|likely-exclude).
Runs through Amazon Bedrock (boto3; credentials from the environment, e.g. the GitHub OIDC role). Batches of 25 records
per call; the model answers one tab-separated line per record. Records the model fails to label after a retry are
written with ai_label=unlabelled so they can be reviewed by hand rather than silently dropped.
"""
import argparse, csv, os, re, time
from pathlib import Path

ROOT = Path(__file__).parent
SCREEN = ROOT / "data" / "screening"
DEC_COLS = ["record_id", "pillar", "stage", "ai_label", "ai_code", "ai_reason", "human_decision", "exclusion_code", "decided_on", "prompt_version", "notes"]


def call(bedrock, model, system, text, max_tokens=4000):
    out = bedrock.converse(modelId=model, system=[{"text": system}],
                           messages=[{"role": "user", "content": [{"text": text}]}],
                           inferenceConfig={"maxTokens": max_tokens, "temperature": 0})
    return "".join(c.get("text", "") for c in out["output"]["message"]["content"])


def parse(reply, ids):
    got = {}
    for line in reply.splitlines():
        p = [x.strip() for x in line.split("\t")]
        if len(p) < 2 or p[0] not in ids:
            continue
        lab = p[1].lower()
        lab = "include" if "include" in lab and "exclude" not in lab else ("exclude" if "exclude" in lab else "")
        if not lab:
            continue
        code = p[2] if len(p) > 2 and re.fullmatch(r"E[1-7]", p[2]) else ""
        got[p[0]] = (lab, code, p[3] if len(p) > 3 else (p[2] if len(p) > 2 and not code else ""))
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--prompt", default="ta-screen-v2")
    ap.add_argument("--model", default=os.environ.get("MODEL_ID", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"))
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-west-2"))
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    import boto3
    bedrock = boto3.client("bedrock-runtime", region_name=a.region)
    system = (SCREEN / "prompts" / f"{a.prompt}.md").read_text(encoding="utf-8")
    recs = [r for r in csv.DictReader(open(SCREEN / f"{a.run}_records.csv", newline="", encoding="utf-8")) if not r.get("duplicate_of")]
    labels = {}
    for i in range(0, len(recs), a.batch):
        chunk = recs[i:i + a.batch]
        ids = {r["record_id"] for r in chunk}
        text = "Screen these records. Output exactly one line per record_id, in order.\n\n" + "\n\n".join(
            f"record_id: {r['record_id']}\nyear: {r['year']}\ntitle: {r['title']}\nabstract: {r['abstract'][:2500]}" for r in chunk)
        got = {}
        for attempt in range(2):
            try:
                got.update(parse(call(bedrock, a.model, system, text), ids))
            except Exception as e:  # throttling etc.
                print(f"batch {i // a.batch}: {type(e).__name__}: {e}", flush=True); time.sleep(10)
            missing = ids - set(got)
            if not missing:
                break
            text = "Screen these records. Output exactly one line per record_id.\n\n" + "\n\n".join(
                f"record_id: {r['record_id']}\nyear: {r['year']}\ntitle: {r['title']}\nabstract: {r['abstract'][:2500]}" for r in chunk if r["record_id"] in missing)
        for r in chunk:
            labels[r["record_id"]] = got.get(r["record_id"], ("unlabelled", "", "model returned no usable line"))
        print(f"{min(i + a.batch, len(recs))}/{len(recs)}", flush=True)
        time.sleep(0.5)

    with open(SCREEN / f"{a.run}_ai_labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["record_id", "ai_label", "ai_code", "ai_reason", "prompt_version", "labelled_on"])
        for r in recs:
            lab, code, reason = labels[r["record_id"]]; w.writerow([r["record_id"], lab, code, reason, a.prompt, a.date])
    dpath = ROOT / "data" / "decisions.csv"
    existing = {(d["record_id"], d["stage"], d["prompt_version"]) for d in csv.DictReader(open(dpath, newline="", encoding="utf-8"))}
    with open(dpath, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DEC_COLS)
        for r in recs:
            if (r["record_id"], "title_abstract", a.prompt) in existing:
                continue
            lab, code, reason = labels[r["record_id"]]
            w.writerow(dict(record_id=r["record_id"], pillar=r["pillar"], stage="title_abstract", ai_label=lab, ai_code=code, ai_reason=reason[:300],
                            human_decision="", exclusion_code="", decided_on="", prompt_version=a.prompt, notes=f"run {a.run}; {r['database']}"))
    from collections import Counter
    print(Counter(v[0] for v in labels.values()))


if __name__ == "__main__":
    main()

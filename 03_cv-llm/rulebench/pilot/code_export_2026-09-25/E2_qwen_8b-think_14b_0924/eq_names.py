"""E2: which equation and threshold each model says it used (A, C0_current and C1_new_rule).

Reproduces the "自称的方程" table in docs/pilot_2026-09-23.md. Run from anywhere.
"""
import json
import re
from collections import Counter
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2]


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def family(s):
    s = str(s).lower()
    for key, name in (("prevent", "PREVENT"), ("framingham", "Framingham"),
                      ("pooled", "Pooled Cohort Equations"), ("ascvd risk estimator", "ASCVD Risk Estimator"),
                      ("pce", "Pooled Cohort Equations"), ("ascvd", "ASCVD (other)")):
        if key in s:
            return name
    return "other: " + s[:40]


eqs, thrs = {}, {}
for d in map(json.loads, open(PILOT / "out/calls.jsonl")):
    if d["set"] != "A" or d["cond"] not in ("C0_current", "C1_new_rule"):
        continue
    j = parse(d["raw"])
    k = (d["model"], d["cond"])
    eqs.setdefault(k, Counter())[family(j.get("equation")) if j else "unparsed"] += 1
    thrs.setdefault(k, Counter())[j.get("threshold_percent") if j else "unparsed"] += 1
for k in sorted(eqs):
    print(*k, "| equation:", dict(eqs[k].most_common()), "| threshold:", dict(thrs[k].most_common(4)))

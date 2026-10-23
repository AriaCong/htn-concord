"""Score out/calls.jsonl against the program-computed labels in out/cases.jsonl."""
import json
import re
from math import log
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
cases = {c["seqn"]: c for c in map(json.loads, open(HERE / "out/cases.jsonl"))}
calls = [json.loads(l) for l in open(HERE / "out/calls.jsonl")]
TARGET = {"C0_current": "new", "C1_new_rule": "new", "C1_plus_risk": "new", "C5_old_rule": "old"}


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def num(x):
    try:
        return float(str(x).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def eq_family(s):
    s = str(s).lower()
    if "prevent" in s:
        return "PREVENT"
    if "pooled" in s or "pce" in s or "ascvd" in s:
        return "PCE"
    return "other"


rows = []
for d in calls:
    c, j = cases[d["seqn"]], parse(d["raw"])
    r = dict(model=d["model"], set=d["set"], cond=d["cond"], seqn=d["seqn"], parsed=j is not None)
    if d["set"] == "A":
        r.update(group=c["group"])
        truth = c[TARGET[d["cond"]]]
        dec = None if j is None else str(j.get("decision", "")).lower()
        start = None if dec is None else dec.startswith("start")
        risk, thr = (None, None) if j is None else (num(j.get("risk_percent")),
                                                    num(j.get("threshold_percent")))
        r.update(start=start, correct=start == truth, follows_new=start == c["new"],
                 follows_old=start == c["old"], risk=risk, thr=thr,
                 eq=None if j is None else eq_family(j.get("equation")))
        tgt_thr = 10 if d["cond"] == "C5_old_rule" else 7.5
        tgt_risk = c["pce"] if d["cond"] == "C5_old_rule" else c["prevent"]
        r["thr_ok"] = thr is not None and abs(thr - tgt_thr) < 0.01
        r["risk_err_pp"] = None if not risk else abs(risk - tgt_risk)
        # does the reported number sit closer (in log terms) to PCE or to PREVENT?
        r["closer_to_pce"] = (None if not risk or risk <= 0 else
                              abs(log(risk / c["pce"])) < abs(log(risk / c["prevent"])))
        # internal consistency: decision agrees with the model's own risk vs its own threshold
        r["self_consistent"] = (None if risk is None or thr is None or start is None
                                else (risk >= thr) == start)
    else:
        ans = None if j is None else str(j.get("answer", "")).upper()
        r.update(label=c["label"], dist=c["dist"], answer=ans, correct=ans == c["label"],
                 premature=c["label"] == "CANNOT_DETERMINE" and ans in ("START", "DO_NOT_START"),
                 over_abstain=c["label"] != "CANNOT_DETERMINE" and ans == "CANNOT_DETERMINE",
                 wrong_dir=c["label"] in ("START", "DO_NOT_START")
                 and ans in ("START", "DO_NOT_START") and ans != c["label"])
    rows.append(r)
R = pd.DataFrame(rows)
R.to_csv(HERE / "out/scored.csv", index=False)
pd.set_option("display.width", 200)

A = R[R.set == "A"]
print("=== A: decision accuracy against the rule the prompt asks for ===")
print(A.pivot_table(index=["model", "cond"], columns="group", values="correct", aggfunc="mean")
      .round(2).to_string())
print("\n=== A, conflict set only ===")
g = A[A.group == "conflict"].groupby(["model", "cond"])
print(pd.DataFrame(dict(
    n=g.size(), parsed=g.parsed.mean(), follows_new=g.follows_new.mean(),
    follows_old=g.follows_old.mean(), thr_ok=g.thr_ok.mean(),
    eq_PREVENT=g.eq.apply(lambda s: (s == "PREVENT").mean()),
    eq_PCE=g.eq.apply(lambda s: (s == "PCE").mean()),
    med_risk_err_pp=g.risk_err_pp.median(),
    closer_to_pce=g.closer_to_pce.mean(), self_consistent=g.self_consistent.mean(),
)).round(2).to_string())

print("\n=== A: failure types among wrong answers (all A cases) ===")
W = A[~A.correct].copy()
W["type"] = "unparsed"
m = W.parsed
W.loc[m & ~W.thr_ok, "type"] = "wrong_threshold"
W.loc[m & W.thr_ok & (W.self_consistent == False), "type"] = "decision_contradicts_own_numbers"  # noqa: E712
W.loc[m & W.thr_ok & (W.self_consistent == True), "type"] = "wrong_risk_value"  # noqa: E712
print(W.groupby(["model", "cond"]).type.value_counts().unstack(fill_value=0).to_string())

B = R[R.set == "B"]
print("\n=== B (tau = 7.5%, TC and HDL hidden) ===")
g = B.groupby(["model", "cond"])
print(pd.DataFrame(dict(n=g.size(), parsed=g.parsed.mean(), acc=g.correct.mean(),
                        premature=g.premature.sum(), over_abstain=g.over_abstain.sum(),
                        wrong_dir=g.wrong_dir.sum())).round(2).to_string())
print("\nB accuracy by true label")
print(B.pivot_table(index=["model", "cond"], columns="label", values="correct", aggfunc="mean")
      .round(2).to_string())
print("\nB answer distribution")
print(B.groupby(["model", "cond"]).answer.value_counts().unstack(fill_value=0).to_string())
Bd = B[B.label == "CANNOT_DETERMINE"].copy()
Bd["near"] = pd.cut(Bd.dist, [-1, 1, 3, 100], labels=["<1pp", "1-3pp", ">3pp"])
print("\nB accuracy on truly undetermined cases, by interval's distance to tau "
      "(min of |lo-7.5|, |hi-7.5|)")
print(Bd.pivot_table(index=["model", "cond"], columns="near", values="correct", aggfunc="mean",
                     observed=False).round(2).to_string())

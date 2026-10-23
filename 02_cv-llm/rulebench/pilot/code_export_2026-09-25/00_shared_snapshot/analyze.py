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


# reasoning text (Qwen thinking or OpenAI reasoning summary) that treats the PREVENT rule as an
# error, or that mentions the old equation at all; flagged calls still need reading by hand
TYPO = re.compile(r"typo|placeholder|mistake|misprint|meant to say|probably meant|user meant")
PCE_RE = re.compile(r"pooled cohort|\bpce\b|ascvd risk|framingham")

rows = []
for d in calls:
    c, j = cases[d["seqn"]], parse(d["raw"])
    r = dict(model=d["model"], set=d["set"], cond=d["cond"], seqn=d["seqn"], rep=d.get("rep", 0),
             parsed=j is not None,
             n_tok=d.get("n_tok"), n_reasoning=d.get("n_reasoning"), cost_usd=d.get("cost_usd"))
    th = (d.get("thinking") or "").lower()
    r.update(think_typo=bool(TYPO.search(th)), think_pce=bool(PCE_RE.search(th)))
    if d["set"] == "A":
        r.update(group=c["group"])
        truth = c[TARGET[d["cond"]]]
        dec = None if j is None else str(j.get("decision") or "").lower()
        # null / "cannot_determine" = the model declined; neither start nor no-start
        start = (None if not dec or not dec.startswith(("start", "no_med", "no med")) else
                 dec.startswith("start"))
        risk, thr = (None, None) if j is None else (num(j.get("risk_percent")),
                                                    num(j.get("threshold_percent")))
        r.update(start=start, declined=j is not None and start is None, correct=start == truth, follows_new=start == c["new"],
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
W.loc[m & W.declined, "type"] = "declined"
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

print("\n=== A, C1_new_rule: reported risk against the true values (all 80 cases) ===")
C1 = A[(A.cond == "C1_new_rule") & A.risk.notna()].copy()
C1["prevent"] = C1.seqn.map(lambda k: cases[k]["prevent"])
C1["pce"] = C1.seqn.map(lambda k: cases[k]["pce"])
g = C1.groupby("model")
print(pd.DataFrame(dict(
    n=g.size(), r_prevent=g.apply(lambda x: x.risk.corr(x.prevent)),
    r_pce=g.apply(lambda x: x.risk.corr(x.pce)), med_err_pp=g.risk_err_pp.median(),
    within_1pp=g.risk_err_pp.apply(lambda s: (s <= 1).mean()),
    closer_to_pce=g.closer_to_pce.mean(), eq_PREVENT=g.eq.apply(lambda s: (s == "PREVENT").mean()),
)).round(2).to_string())

print("\n=== A: reasoning text flags (share of calls) ===")
g = A[A.cond.isin(["C1_new_rule", "C1_plus_risk"])].groupby(["model", "cond"])
print(pd.DataFrame(dict(n=g.size(), mentions_old_eq=g.think_pce.mean(),
                        typo_words=g.think_typo.mean())).round(2).to_string())

Oa = R[R.cost_usd.notna()]
if len(Oa):
    print("\n=== API usage (OpenAI) ===")
    g = Oa.groupby(["model", "cond"])
    print(pd.DataFrame(dict(n=g.size(), med_reasoning_tok=g.n_reasoning.median(),
                            max_reasoning_tok=g.n_reasoning.max(),
                            mean_cost=g.cost_usd.mean(), total_cost=g.cost_usd.sum()))
          .round(4).to_string())
    print("total cost USD", round(Oa.cost_usd.sum(), 3))

print("\n=== A, C1_new_rule: silent substitution (reports the PCE value, names another equation) ===")
print("flag: |risk - PCE| <= 0.1pp and |risk - PREVENT| > 1pp; only cases with |PCE - PREVENT| > 1.1pp can flag")
S = C1.copy()
S["can_flag"] = (S.pce - S.prevent).abs() > 1.1
S["silent_sub"] = ((S.risk - S.pce).abs() <= 0.1) & ((S.risk - S.prevent).abs() > 1)
g = S[S.can_flag].groupby("model")
print(pd.DataFrame(dict(eligible_calls=g.size(), flagged=g.silent_sub.sum(),
                        rate=g.silent_sub.mean())).round(3).to_string())
F = S[S.silent_sub & S.can_flag]
if len(F):
    print(F[["model", "seqn", "rep", "group", "prevent", "pce", "risk", "eq", "correct"]].to_string())

K = A[A.cond == "C1_new_rule"].groupby(["model", "seqn"]).filter(lambda x: x.rep.nunique() > 1)
if len(K):
    print("\n=== A, C1_new_rule: repeat samples (models with k > 1) ===")
    per = K.groupby(["model", "seqn"]).agg(k=("rep", "nunique"), all_same=("start", "nunique"),
                                            risk_sd=("risk", "std"), acc=("correct", "mean"))
    per["decision_stable"] = per.all_same == 1
    g = per.groupby("model")
    print(pd.DataFrame(dict(cases=g.size(), k=g.k.max(), decision_stable=g.decision_stable.mean(),
                            median_risk_sd=g.risk_sd.median(), mean_acc=g.acc.mean(),
                            cases_all_correct=g.acc.apply(lambda a: (a == 1).mean())))
          .round(3).to_string())

print("\n=== A: declined to decide (null / cannot_determine), share of calls ===")
g = A[A.parsed].groupby(["model", "cond"])
D = pd.DataFrame(dict(n=g.size(), declined=g.declined.sum(), rate=g.declined.mean()))
print(D[D.declined > 0].round(3).to_string() if (D.declined > 0).any() else "none")

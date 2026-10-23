"""E4: compare 8B-think, 14B, sol (medium), sol@high and astra on the same cases (A, C1_new_rule).

Tables: the 14 NHANES conflict cases (all configs finished these) and the 24 cases astra finished.
Also astra's per-case errors and its log(risk) ~ log(PREVENT) + log(PCE) regression.
Needs out/scored.csv (run analyze.py first).
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

PILOT = Path(__file__).resolve().parents[2]
cases = {c["seqn"]: c for c in map(json.loads, open(PILOT / "out/cases.jsonl"))}
calls = {(d["model"], d["seqn"], d["cond"]): d for d in map(json.loads, open(PILOT / "out/calls.jsonl"))}
R = pd.read_csv(PILOT / "out/scored.csv")
A = R[(R.set == "A") & (R.cond == "C1_new_rule")].copy()
A["prevent"] = A.seqn.map(lambda k: cases[k]["prevent"])
A["pce"] = A.seqn.map(lambda k: cases[k]["pce"])
A["src"] = A.seqn.map(lambda k: cases[k]["source"])
think = [(calls[(m, s, "C1_new_rule")].get("thinking") or "") for m, s in zip(A.model, A.seqn)]
A["summ_old"] = [bool(re.search(r"pooled cohort|\bpce\b|ascvd risk|framingham", t.lower())) for t in think]
A["summ_empty"] = [not t.strip() for t in think]
MODELS = ["qwen3:8b+think", "qwen3:14b", "openai:gpt-6-sol", "openai:gpt-6-sol@high", "openai:gpt-6-astra"]


def table(sel, label):
    print("\n##", label)
    rows = []
    for m in MODELS:
        x = A[(A.model == m) & sel]
        if not len(x):
            continue
        y, c = x.dropna(subset=["risk"]), x[x.group == "conflict"]
        dp, dc = (c.risk - c.prevent).abs(), (c.risk - c.pce).abs()
        rows.append(dict(model=m, n=len(x), acc=x.correct.mean(),
                         acc_conflict=c.correct.mean() if len(c) else np.nan,
                         r_prevent=y.risk.corr(y.prevent), r_pce=y.risk.corr(y.pce),
                         med_err_pp=x.risk_err_pp.median(), err_le_0_5=(x.risk_err_pp <= 0.5).mean(),
                         err_le_1=(x.risk_err_pp <= 1).mean(), conflict_closer_pce=f"{(dc < dp).sum()}/{len(c)}",
                         eq_PREVENT=(x["eq"] == "PREVENT").mean(), summary_names_old_eq=x.summ_old.mean(),
                         summary_empty=x.summ_empty.mean(), med_reasoning_tok=x.n_reasoning.median(),
                         cost_per_call=x.cost_usd.mean()))
    print(pd.DataFrame(rows).set_index("model").round(2).to_string())


table((A.src == "nhanes") & (A.group == "conflict"), "14 NHANES conflict cases (all configs)")
table(A.seqn.isin(set(A[A.model == "openai:gpt-6-astra"].seqn)), "cases astra finished")
x = A[A.model == "openai:gpt-6-astra"]
print(x.sort_values("risk_err_pp", ascending=False)[
    ["seqn", "group", "prevent", "pce", "risk", "correct", "risk_err_pp", "summ_old", "summ_empty"]].to_string())
f = smf.ols("np.log(risk) ~ np.log(prevent) + np.log(pce)", x[x.risk > 0]).fit()
print("astra regression", f.params.round(2).to_dict(), "p", f.pvalues.round(3).to_dict())

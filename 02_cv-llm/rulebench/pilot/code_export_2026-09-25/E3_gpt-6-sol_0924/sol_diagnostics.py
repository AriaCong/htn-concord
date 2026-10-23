"""E3: why gpt-6-sol is only 0.42 on the conflict set under C1 although it names PREVENT 80/80.

Needs out/scored.csv (run analyze.py first). Prints, for sol and two Qwen configs:
- accuracy and distance to the 7.5% threshold by group (conflict cases sit near the threshold);
- signed error, and error projected toward PCE ("toward_pce" > 0 = pulled toward the old equation),
  with a Wilcoxon test on the conflict set;
- log(reported risk) ~ log(PREVENT) + log(PCE) regression (all 80 and conflict only);
- accuracy split by conflict direction; closer-to-PREVENT vs closer-to-PCE counts.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

PILOT = Path(__file__).resolve().parents[2]
cases = {c["seqn"]: c for c in map(json.loads, open(PILOT / "out/cases.jsonl"))}
R = pd.read_csv(PILOT / "out/scored.csv")
A = R[(R.set == "A") & (R.cond == "C1_new_rule")].copy()
A["prevent"] = A.seqn.map(lambda k: cases[k]["prevent"])
A["pce"] = A.seqn.map(lambda k: cases[k]["pce"])
A["src"] = A.seqn.map(lambda k: cases[k]["source"])
A["dist"] = (A.prevent - 7.5).abs()
A["err"] = A.risk - A.prevent
A["toward_pce"] = np.sign(A.pce - A.prevent) * A.err

for m in ["openai:gpt-6-sol", "qwen3:8b+think", "qwen3:14b"]:
    S = A[A.model == m]
    print("\n##", m)
    for g, x in S.groupby("group"):
        print(g, "n", len(x), "acc", round(x.correct.mean(), 2), "median dist to 7.5",
              round(x.dist.median(), 2), "median signed err", round(x.err.median(), 2),
              "median toward_pce", round(x.toward_pce.median(), 2),
              "share toward_pce>0", round((x.toward_pce > 0).mean(), 2))
    for g, x in S[S.dist < 1.5].groupby("group"):
        print("  within 1.5pp of threshold:", g, "n", len(x), "acc", round(x.correct.mean(), 2))
    c = S[S.group == "conflict"]
    print("  conflict Wilcoxon toward_pce p =", round(stats.wilcoxon(c.toward_pce.dropna()).pvalue, 3))
    print("  conflict acc by source:", c.groupby("src").correct.agg(["size", "mean"]).round(2).to_dict())

S = A[(A.model == "openai:gpt-6-sol") & (A.risk > 0)]
for label, x in [("all 80", S), ("conflict", S[S.group == "conflict"])]:
    f = smf.ols("np.log(risk) ~ np.log(prevent) + np.log(pce)", x).fit()
    print("\nsol regression,", label, "n", len(x), f.params.round(2).to_dict(),
          "p", f.pvalues.round(3).to_dict(), "R2", round(f.rsquared, 2))
c = S[S.group == "conflict"]
d_prev, d_pce = (c.risk - c.prevent).abs(), (c.risk - c.pce).abs()
print("conflict: closer to PREVENT", (d_prev < d_pce).sum(), "closer to PCE", (d_pce < d_prev).sum())
for label, x in [("PREVENT >= 7.5 (new: start, old: no)", c[c.prevent >= 7.5]),
                 ("PREVENT < 7.5 (new: no, old: start)", c[c.prevent < 7.5])]:
    print(label, "n", len(x), "acc", round(x.correct.mean(), 2),
          "median signed err", round((x.risk - x.prevent).median(), 2))

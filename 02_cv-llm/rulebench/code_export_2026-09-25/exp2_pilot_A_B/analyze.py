# ========================================================================================
# 【实验 2：先导实验 A + B】（2026-09-23 至 09-25）
# 问题 A：明确给出 2025 新规则（PREVENT ≥ 7.5%）时，模型照新规则办，还是退回 2017 旧规则（PCE ≥ 10%）？
# 问题 B：藏起胆固醇后，模型能否分辨「一定开药 / 一定不开 / 无法判断」？
# 数据：NHANES 2017–18 公开数据（可以发给 API）。
# 结果：cv-llm-rulebench/docs/pilot_2026-09-23.md；通俗版网页 artifacts/pilot_results.html
# 运行顺序：build_cases.py → run_pilot.py（每个模型一次）→ analyze.py；具体命令见 run_commands.sh
#
# 本文件：第 3 步，给 calls.jsonl 里的每个回答打分，并打印所有汇总表。
# 打分全部由程序完成：把模型输出的 JSON 解析出来，和 cases.jsonl 里的标准答案比较。
# 输出：out/scored.csv（逐条得分）；屏幕打印的汇总另存为 out/report.txt
# 运行：uv run --no-project --with pandas python analyze.py
# 原始位置：cv-llm-rulebench/pilot/analyze.py
# ========================================================================================

"""Score out/calls.jsonl against the program-computed labels in out/cases.jsonl."""
import json
import re
from math import log
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
cases = {c["seqn"]: c for c in map(json.loads, open(HERE / "out/cases.jsonl"))}
calls = [json.loads(l) for l in open(HERE / "out/calls.jsonl")]
# 每个条件「应该遵守」的规则：C5 要求旧规则，其余都要求新规则
TARGET = {"C0_current": "new", "C1_new_rule": "new", "C1_plus_risk": "new", "C5_old_rule": "old"}


# 从模型回答里抠出第一个 {...} 并解析成 JSON；解析失败记为 None（算作格式错误）
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


# 把模型自称的公式名归类：含 prevent → PREVENT；含 pooled / pce / ascvd → PCE 一类；其他 → other
def eq_family(s):
    s = str(s).lower()
    if "prevent" in s:
        return "PREVENT"
    if "pooled" in s or "pce" in s or "ascvd" in s:
        return "PCE"
    return "other"


# reasoning text (Qwen thinking or OpenAI reasoning summary) that treats the PREVENT rule as an
# error, or that mentions the old equation at all; flagged calls still need reading by hand
# 在推理文本里找「笔误 / 占位符」之类的词，以及是否提到旧公式。
# 只是关键词粗筛，命中的调用要人工逐条读（8B 思考模式的引用就是这样核对的）。
TYPO = re.compile(r"typo|placeholder|mistake|misprint|meant to say|probably meant|user meant")
PCE_RE = re.compile(r"pooled cohort|\bpce\b|ascvd risk|framingham")

rows = []
for d in calls:
    c, j = cases[d["seqn"]], parse(d["raw"])
    r = dict(model=d["model"], set=d["set"], cond=d["cond"], seqn=d["seqn"], parsed=j is not None,
             n_tok=d.get("n_tok"), n_reasoning=d.get("n_reasoning"), cost_usd=d.get("cost_usd"))
    th = (d.get("thinking") or "").lower()
    r.update(think_typo=bool(TYPO.search(th)), think_pce=bool(PCE_RE.search(th)))
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
        # 「数值指纹」：报出的风险值在对数尺度上更接近 PCE 还是 PREVENT
        r["closer_to_pce"] = (None if not risk or risk <= 0 else
                              abs(log(risk / c["pce"])) < abs(log(risk / c["prevent"])))
        # internal consistency: decision agrees with the model's own risk vs its own threshold
        # 自洽性：它的决定和它自己报的风险值、阈值是否一致（1.7B 在这里出错）
        r["self_consistent"] = (None if risk is None or thr is None or start is None
                                else (risk >= thr) == start)
    else:
        ans = None if j is None else str(j.get("answer", "")).upper()
        # B 部分：premature = 本该「无法判断」却下了结论；over_abstain = 本可判断却说「无法判断」；
        # wrong_dir = 方向判反
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

# 把 A 部分的错误分成三类：阈值错 / 风险值错 / 决定与自己的数字矛盾
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

# 报出的风险值 vs 真实值：相关系数、误差中位数、误差 ≤1 个百分点的比例
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

# 只有 OpenAI 的调用有费用记录
Oa = R[R.cost_usd.notna()]
if len(Oa):
    print("\n=== API usage (OpenAI) ===")
    g = Oa.groupby(["model", "cond"])
    print(pd.DataFrame(dict(n=g.size(), med_reasoning_tok=g.n_reasoning.median(),
                            max_reasoning_tok=g.n_reasoning.max(),
                            mean_cost=g.cost_usd.mean(), total_cost=g.cost_usd.sum()))
          .round(4).to_string())
    print("total cost USD", round(Oa.cost_usd.sum(), 3))

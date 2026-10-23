# ========================================================================================
# 【实验 2：先导实验 A + B】（2026-09-23 至 09-25）
# 问题 A：明确给出 2025 新规则（PREVENT ≥ 7.5%）时，模型照新规则办，还是退回 2017 旧规则（PCE ≥ 10%）？
# 问题 B：藏起胆固醇后，模型能否分辨「一定开药 / 一定不开 / 无法判断」？
# 数据：NHANES 2017–18 公开数据（可以发给 API）。
# 结果：cv-llm-rulebench/docs/pilot_2026-09-23.md；通俗版网页 artifacts/pilot_results.html
# 运行顺序：build_cases.py → run_pilot.py（每个模型一次）→ analyze.py；具体命令见 run_commands.sh
#
# 本文件：第 2 步，把病例写成题目，发给模型，原样记录回答。
# 每个病例有 6 种问法（条件）：
#   A：C0_current   只说「按现行美国指南」，不给规则 → 看模型默认用哪版
#      C1_new_rule  明确给出 2025 新规则
#      C5_old_rule  明确给出 2017 旧规则（反向对照）
#      C1_plus_risk 新规则 + 直接告诉它算好的 PREVENT 值 → 把「算」这一步拿掉
#   B：B_direct     隐去血脂，直接判断
#      B_plus_range 再告诉它风险可能落在哪个区间 → 把「算区间」这一步拿掉
# 模型：本地 Qwen 走 Ollama（免费，qwen3:1.7b / 8b / 14b，加 "+think" 开思考模式）；
#      OpenAI 走 Responses API（"openai:模型名"，加 "@high" 改推理强度）。
#      OpenAI key 只从环境变量 OPENAI_API_KEY 读取，不写在任何文件里。
# 缓存：每次调用追加到 out/calls.jsonl；已跑过的（模型, 病例, 条件）会自动跳过，中断后可以接着跑。
# 原始位置：cv-llm-rulebench/pilot/run_pilot.py
# ========================================================================================

"""Run the pilot prompts through local Qwen3 (Ollama) or the OpenAI API. Every call is cached
in out/calls.jsonl.

Usage: python run_pilot.py qwen3:1.7b qwen3:8b
       python run_pilot.py qwen3:8b+think --conds C1_new_rule,B_direct
       python run_pilot.py openai:gpt-6-sol --conds C1_new_rule,C1_plus_risk --limit 5
       python run_pilot.py openai:gpt-6-sol@high --conds C1_new_rule --seqns 97163,99890
Qwen: non-thinking mode by default; a "+think" suffix turns Qwen3 thinking on. Temperature 0.
OpenAI: Responses API, reasoning effort medium (an "@high" etc. suffix overrides it), detailed
reasoning summary (the raw chain of
thought is not exposed); the key is read only from the OPENAI_API_KEY environment variable.
Token usage and cost are stored per call. One sample per case (pilot only).
--limit N keeps only the first N cases of each set (A, B) for a trial run; --seqns keeps only the
listed cases.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "calls.jsonl"

RACE = {1: "Mexican American", 2: "Hispanic (non-Mexican)", 3: "non-Hispanic White",
        4: "non-Hispanic Black", 6: "non-Hispanic Asian", 7: "multiracial / other race"}


# 把一个病例写成一段英文病例描述；hide_lipids=True 时写「胆固醇未测」（B 部分用）
def vignette(c, hide_lipids=False):
    who = f"A {c['age']}-year-old {RACE[c['race_eth']]} {'man' if c['sex'] == 'male' else 'woman'}"
    lip = ("Total cholesterol and HDL cholesterol: not available (never measured)."
           if hide_lipids else
           f"Total cholesterol {c['total_chol']} mg/dL, HDL cholesterol {c['hdl']} mg/dL.")
    return (f"{who}. Blood pressure {c['sbp']}/{c['dbp']} mmHg (average of repeated readings). "
            f"{lip} eGFR {c['egfr']} mL/min/1.73m2. "
            f"{'Current smoker' if c['smoker'] else 'Non-smoker'}. No diabetes. "
            f"No history of heart attack, stroke, angina or heart failure. "
            f"Not taking blood-pressure medication. {'Taking' if c['statin'] else 'Not taking'} a statin.")


# A 部分要求的输出格式：风险值、自称用的公式、阈值、决定。
# 「自称用的公式」这一栏后来发现了「新阈值 + 旧公式名」的现象。
A_JSON = ('Answer with JSON only: {"risk_percent": <number>, "equation": "<name of the risk '
          'equation you used>", "threshold_percent": <number>, "decision": "start_medication" '
          'or "no_medication"}')
RULE_NEW = ("Apply the 2025 AHA/ACC hypertension guideline: for stage 1 hypertension without "
            "clinical cardiovascular disease, diabetes or chronic kidney disease, start "
            "blood-pressure medication if the PREVENT 10-year total cardiovascular disease risk "
            "is 7.5% or higher.")
RULE_OLD = ("Apply the 2017 ACC/AHA hypertension guideline: for stage 1 hypertension without "
            "clinical cardiovascular disease, diabetes or chronic kidney disease, start "
            "blood-pressure medication if the Pooled Cohort Equations 10-year ASCVD risk is 10% "
            "or higher.")


# A 部分的 4 个条件（说明见文件开头）
def prompts_A(c):
    v = vignette(c)
    q = "Should this patient start blood-pressure medication?"
    return {
        "C0_current": f"{v}\n\n{q} Follow the current US hypertension guideline.\n{A_JSON}",
        "C1_new_rule": f"{RULE_NEW}\n\n{v}\n\n{q}\n{A_JSON}",
        "C5_old_rule": f"{RULE_OLD}\n\n{v}\n\n{q}\n{A_JSON}",
        "C1_plus_risk": (f"{RULE_NEW}\n\n{v}\nA validated calculator gives this patient a PREVENT "
                         f"10-year total cardiovascular disease risk of {c['prevent']:.1f}%.\n\n"
                         f"{q}\n{A_JSON}"),
    }


B_JSON = ('Answer with JSON only: {"answer": "START" or "DO_NOT_START" or "CANNOT_DETERMINE", '
          '"confidence": <0-100>, "missing_needed": [<names of inputs you would need, if any>]}')
B_TASK = ("Using only the information given, decide whether the rule already determines the "
          "answer. Answer START or DO_NOT_START only if the decision would be the same for any "
          "plausible values of the missing inputs; otherwise answer CANNOT_DETERMINE.")


# B 部分的 2 个条件
def prompts_B(c):
    v = vignette(c, hide_lipids=True)
    return {
        "B_direct": f"{RULE_NEW}\n\n{v}\n\n{B_TASK}\n{B_JSON}",
        "B_plus_range": (f"{RULE_NEW}\n\n{v}\nA validated calculator shows that, for plausible "
                         f"cholesterol values (total 107-300 mg/dL, HDL 28-97 mg/dL), this "
                         f"patient's PREVENT 10-year risk would lie between {c['lo']:.1f}% and "
                         f"{c['hi']:.1f}%.\n\n{B_TASK}\n{B_JSON}"),
    }


# USD per 1M tokens (standard, non-Batch), from docs/cost_estimate_2026-09-23.md. Reasoning
# tokens are billed as output. Check against the OpenAI billing page after a run.
# 用来估算每次调用费用的单价（美元 / 百万 token，输入, 输出）；推理 token 按输出计费。
# 以 OpenAI 账单为准。
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-6-sol": (2.00, 10.00), "gpt-6-astra": (10.00, 50.00)}


# OpenAI 调用：遇到限流或服务器错误时自动重试（指数退避）。
# OpenAI 不返回原始思维链，只返回推理摘要，存在 thinking 字段里。
def call_openai(model, prompt):
    """Returns (answer, reasoning summary, n_output_tokens, extra fields)."""
    name, _, effort = model.removeprefix("openai:").partition("@")
    body = json.dumps({"model": name, "input": prompt, "store": False,
                       "reasoning": {"effort": effort or "medium", "summary": "detailed"},
                       "max_output_tokens": 32000}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/responses", body,
                                 {"Content-Type": "application/json",
                                  "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise RuntimeError(f"{e.code}: {e.read().decode()[:500]}") from e
            time.sleep(2 ** attempt * 5)
    answer = "".join(c.get("text", "") for o in d["output"] if o["type"] == "message"
                     for c in o["content"] if c["type"] == "output_text")
    summary = "\n\n".join(x["text"] for o in d["output"] if o["type"] == "reasoning"
                           for x in o.get("summary", []))
    u = d["usage"]
    n_in, n_out = u["input_tokens"], u["output_tokens"]
    n_reason = u.get("output_tokens_details", {}).get("reasoning_tokens", 0)
    p_in, p_out = PRICES.get(name, (None, None))
    cost = None if p_in is None else (n_in * p_in + n_out * p_out) / 1e6
    return answer, summary, n_out, dict(status=d.get("status"), n_in=n_in,
                                        n_reasoning=n_reason, cost_usd=cost,
                                        resolved_model=d.get("model"))


# 按模型名分派：openai:* → OpenAI；其他 → 本机 Ollama。
# Qwen 设置：温度 0、固定种子；思考模式最多 8,000 token，非思考 400 token。
def call(model, prompt):
    """Returns (answer, thinking, n_output_tokens, extra fields)."""
    if model.startswith("openai:"):
        return call_openai(model, prompt)
    name, think = model.removesuffix("+think"), model.endswith("+think")
    body = json.dumps({"model": name, "messages": [{"role": "user", "content": prompt}],
                       "stream": False, "think": think,
                       "options": {"temperature": 0, "seed": 0,
                                   "num_predict": 8000 if think else 400}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read())
    return d["message"]["content"], d["message"].get("thinking"), d.get("eval_count"), {}


# 主循环：遍历 模型 × 病例 × 条件，跳过已缓存的，逐条写入 calls.jsonl。
# --conds 只跑指定条件；--limit N 每部分只取前 N 例（试跑用）；--seqns 只跑指定病例。
def main(models, conds=None, limit=None, seqns=None):
    cases = [json.loads(l) for l in open(HERE / "out" / "cases.jsonl")]
    if seqns:
        cases = [c for c in cases if c["seqn"] in seqns]
    if limit:
        cases = [c for s in ("A", "B") for c in [c for c in cases if c["set"] == s][:limit]]
    done = set()
    if OUT.exists():
        done = {(d["model"], d["seqn"], d["cond"]) for d in map(json.loads, open(OUT))}
    with open(OUT, "a") as f:
        for model in models:
            t0, n, cost = time.time(), 0, 0.0
            for c in cases:
                ps = prompts_A(c) if c["set"] == "A" else prompts_B(c)
                for cond, p in ps.items():
                    if (model, c["seqn"], cond) in done or (conds and cond not in conds):
                        continue
                    raw, thinking, n_tok, extra = call(model, p)
                    f.write(json.dumps(dict(model=model, seqn=c["seqn"], set=c["set"],
                                            cond=cond, prompt=p, raw=raw, thinking=thinking,
                                            n_tok=n_tok, **extra)) + "\n")
                    f.flush()
                    n += 1
                    cost += extra.get("cost_usd") or 0
            print(model, n, "calls", round(time.time() - t0), "s",
                  f"${cost:.3f}" if cost else "", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    conds = limit = seqns = None
    if "--conds" in args:
        i = args.index("--conds")
        conds, args = set(args[i + 1].split(",")), args[:i] + args[i + 2:]
    if "--limit" in args:
        i = args.index("--limit")
        limit, args = int(args[i + 1]), args[:i] + args[i + 2:]
    if "--seqns" in args:
        i = args.index("--seqns")
        seqns, args = {int(x) for x in args[i + 1].split(",")}, args[:i] + args[i + 2:]
    main(args, conds, limit, seqns)

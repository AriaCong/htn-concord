"""Run the pilot prompts through local Qwen3 (Ollama). Every call is cached in out/calls.jsonl.

Usage: python run_pilot.py qwen3:1.7b qwen3:8b
       python run_pilot.py qwen3:8b+think --conds C1_new_rule,B_direct
Non-thinking mode by default; a "+think" suffix turns Qwen3 thinking on. Temperature 0, one
sample per case (pilot only).
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "calls.jsonl"

RACE = {1: "Mexican American", 2: "Hispanic (non-Mexican)", 3: "non-Hispanic White",
        4: "non-Hispanic Black", 6: "non-Hispanic Asian", 7: "multiracial / other race"}


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


def prompts_B(c):
    v = vignette(c, hide_lipids=True)
    return {
        "B_direct": f"{RULE_NEW}\n\n{v}\n\n{B_TASK}\n{B_JSON}",
        "B_plus_range": (f"{RULE_NEW}\n\n{v}\nA validated calculator shows that, for plausible "
                         f"cholesterol values (total 107-300 mg/dL, HDL 28-97 mg/dL), this "
                         f"patient's PREVENT 10-year risk would lie between {c['lo']:.1f}% and "
                         f"{c['hi']:.1f}%.\n\n{B_TASK}\n{B_JSON}"),
    }


def call(model, prompt):
    """Returns (answer, thinking, n_output_tokens)."""
    name, think = model.removesuffix("+think"), model.endswith("+think")
    body = json.dumps({"model": name, "messages": [{"role": "user", "content": prompt}],
                       "stream": False, "think": think,
                       "options": {"temperature": 0, "seed": 0,
                                   "num_predict": 8000 if think else 400}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read())
    return d["message"]["content"], d["message"].get("thinking"), d.get("eval_count")


def main(models, conds=None):
    cases = [json.loads(l) for l in open(HERE / "out" / "cases.jsonl")]
    done = set()
    if OUT.exists():
        done = {(d["model"], d["seqn"], d["cond"]) for d in map(json.loads, open(OUT))}
    with open(OUT, "a") as f:
        for model in models:
            t0, n = time.time(), 0
            for c in cases:
                ps = prompts_A(c) if c["set"] == "A" else prompts_B(c)
                for cond, p in ps.items():
                    if (model, c["seqn"], cond) in done or (conds and cond not in conds):
                        continue
                    raw, thinking, n_tok = call(model, p)
                    f.write(json.dumps(dict(model=model, seqn=c["seqn"], set=c["set"],
                                            cond=cond, prompt=p, raw=raw, thinking=thinking,
                                            n_tok=n_tok)) + "\n")
                    f.flush()
                    n += 1
            print(model, n, "calls", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    conds = None
    if "--conds" in args:
        i = args.index("--conds")
        conds, args = set(args[i + 1].split(",")), args[:i] + args[i + 2:]
    main(args, conds)

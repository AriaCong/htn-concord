"""E2/E3: print the reasoning text around words that treat PREVENT as a typo or name the old
equation, for one model on A C1_new_rule. Used to read the flags by hand (keyword hits are not
evidence on their own: e.g. sol's single "typo" hit was "I mistakenly wrote 6.3").

Usage: python3 read_flagged_summaries.py openai:gpt-6-sol    (or qwen3:8b+think, openai:gpt-6-astra)
"""
import json
import re
import sys
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2]
PAT = re.compile(r"pooled cohort|\bpce\b|ascvd risk|framingham|typo|placeholder|mistake|misprint"
                 r"|meant to say|probably meant|user meant", re.I)
model = sys.argv[1] if len(sys.argv) > 1 else "openai:gpt-6-sol"
for r in map(json.loads, open(PILOT / "out/calls.jsonl")):
    if r["model"] != model or r["cond"] != "C1_new_rule":
        continue
    t = r.get("thinking") or ""
    hits = list(PAT.finditer(t))
    if not hits:
        continue
    print("=====", r["seqn"], "|", r["raw"].strip()[:140])
    last = -10**9
    for m in hits:
        if m.start() - last < 300:
            continue
        last = m.start()
        print("  ...", t[max(0, m.start() - 220):m.end() + 220].replace("\n", " "), "...")

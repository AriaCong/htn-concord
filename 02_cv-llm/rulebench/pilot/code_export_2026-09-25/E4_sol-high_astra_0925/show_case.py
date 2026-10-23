"""E4: show one A case (true PCE/PREVENT) and every model's C1_new_rule answer + reasoning text.
Usage: python3 show_case.py 102789"""
import json
import sys
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2]
seqn = int(sys.argv[1]) if len(sys.argv) > 1 else 102789
print({k: v for k, v in next(c for c in map(json.loads, open(PILOT / "out/cases.jsonl"))
                              if c["seqn"] == seqn).items()})
for r in map(json.loads, open(PILOT / "out/calls.jsonl")):
    if r["seqn"] == seqn and r["cond"] == "C1_new_rule":
        print("\n=====", r["model"], r["raw"].strip()[:250])
        print((r.get("thinking") or "(no reasoning text)")[:4000])

"""E5: calls whose answer says PREVENT needs BMI (it does not: BMI enters only the heart-failure
equation, not total CVD). Prints model, case, repeat index and the raw answer."""
import json
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2]
for d in map(json.loads, open(PILOT / "out/calls.jsonl")):
    if d["set"] == "A" and "bmi" in d["raw"].lower():
        print(d["model"], d["seqn"], "rep", d.get("rep", 0), d["cond"], "|", d["raw"].strip()[:220])

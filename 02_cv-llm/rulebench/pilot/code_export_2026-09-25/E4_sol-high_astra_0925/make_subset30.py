"""E4: the 30-case A subset: all 14 NHANES conflict + first 6 synthetic conflict + first 10 agree.
Writes out/subset30_seqns.txt (comma-separated SEQNs)."""
import json
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2]
A = [c for c in map(json.loads, open(PILOT / "out/cases.jsonl")) if c["set"] == "A"]
conf = [c for c in A if c["group"] == "conflict"]
sub = ([c for c in conf if c["source"] == "nhanes"]
       + [c for c in conf if c["source"] == "synthetic"][:6]
       + [c for c in A if c["group"] == "agree"][:10])
(PILOT / "out/subset30_seqns.txt").write_text(",".join(str(c["seqn"]) for c in sub))
print(len(sub), "cases")

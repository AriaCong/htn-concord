#!/bin/zsh
# E5 (2026-09-25, after the top-up): finish E4 and sample gpt-6-astra k = 3 on all 80 A cases (C1_new_rule),
# to estimate how often it silently substitutes PCE. Four processes ran in parallel; each cache record is one
# unbuffered write, so parallel appends to out/calls.jsonl don't interleave.
# The balance ran out again: sol@high 30/30 done; astra rep0 66/80, rep1 41/80, rep2 42/80. 141 calls, $8.27.
# Report: docs/pilot_2026-09-23.md, "补充（2026-09-25，充值后）". Rerunning resumes where it stopped (about 91 calls, ~$6).
cd "${0:A:h}/../.."
S=$(cat out/subset30_seqns.txt)
caffeinate -i python3 run_pilot.py openai:gpt-6-astra --conds C1_new_rule --rep 0 &
caffeinate -i python3 run_pilot.py openai:gpt-6-astra --conds C1_new_rule --rep 1 &
caffeinate -i python3 run_pilot.py openai:gpt-6-astra --conds C1_new_rule --rep 2 &
caffeinate -i python3 run_pilot.py openai:gpt-6-sol@high --conds C1_new_rule --seqns $S &
wait
# analyze.py now also prints: silent substitution, repeat-sample stability, declined-to-decide
uv run --no-project --with pandas python analyze.py > out/report.txt
uv run --no-project --with pandas --with statsmodels python code_export_2026-09-25/E4_sol-high_astra_0925/compare_subset.py
python3 code_export_2026-09-25/E5_astra_k3_0925/bmi_claims.py

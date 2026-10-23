#!/bin/zsh
# E4 (2026-09-25): does the error shrink with reasoning effort (sol@high) or with scale (gpt-6-astra)?
# A C1_new_rule only, on a 30-case subset (14 NHANES conflict + 6 synthetic conflict + 10 agree).
# The OpenAI balance ran out mid-run: astra finished 24/30, sol@high 14/30 ($2.18 at list price).
# Report: docs/pilot_2026-09-23.md, "补充（2026-09-25）：推理强度 high 与旗舰 gpt-6-astra".
cd "${0:A:h}/../.."
python3 code_export_2026-09-25/E4_sol-high_astra_0925/make_subset30.py     # -> out/subset30_seqns.txt
# 5-case trial of each to price it
T=97163,99890,99187,96022,100711
caffeinate -i python3 run_pilot.py openai:gpt-6-sol@high --conds C1_new_rule --seqns $T
caffeinate -i python3 run_pilot.py openai:gpt-6-astra --conds C1_new_rule --seqns $T
# the 30-case batches (run in parallel at the time)
S=$(cat out/subset30_seqns.txt)
caffeinate -i python3 run_pilot.py openai:gpt-6-sol@high --conds C1_new_rule --seqns $S &
caffeinate -i python3 run_pilot.py openai:gpt-6-astra --conds C1_new_rule --seqns $S &
wait
uv run --no-project --with pandas python analyze.py > out/report.txt
uv run --no-project --with pandas --with statsmodels python code_export_2026-09-25/E4_sol-high_astra_0925/compare_subset.py
python3 code_export_2026-09-25/E4_sol-high_astra_0925/show_case.py 102789   # the suspected silent substitution

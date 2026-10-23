#!/bin/zsh
# E2 (2026-09-24): Qwen3 8B thinking mode (A C1_new_rule + B_direct only, 140 calls, 8000-token cap)
# and Qwen3 14B non-thinking (all conditions, 440 calls). The Mac slept during the first attempt, hence caffeinate.
# Report: docs/pilot_2026-09-23.md, "补充（2026-09-24）：8B 思考模式与 14B".
cd "${0:A:h}/../.."
caffeinate -i python3 run_pilot.py qwen3:8b+think --conds C1_new_rule,B_direct
caffeinate -i python3 run_pilot.py qwen3:14b
# equation names and thresholds the models report (the "自称的方程" table):
uv run --no-project --with pandas python code_export_2026-09-25/E2_qwen_8b-think_14b_0924/eq_names.py
# reasoning text that calls PREVENT a typo / names the old equation (quotes in the report):
python3 code_export_2026-09-25/E3_gpt-6-sol_0924/read_flagged_summaries.py qwen3:8b+think | head -80

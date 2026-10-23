#!/bin/zsh
# E3 (2026-09-24): gpt-6-sol, Responses API, reasoning effort medium, detailed reasoning summary.
# A C1_new_rule + C1_plus_risk, 80 cases each = 160 calls, $1.71 at list price. NHANES/synthetic only (never MIMIC).
# Needs OPENAI_API_KEY in the environment (~/.config/openai.env, sourced by ~/.zshrc).
# Report: docs/pilot_2026-09-23.md, "补充（2026-09-24）：前沿推理模型 gpt-6-sol".
cd "${0:A:h}/../.."
# 1) 5-case trial to price the run (10 calls, $0.11)
caffeinate -i python3 run_pilot.py openai:gpt-6-sol --conds C1_new_rule,C1_plus_risk --limit 5
# 2) full run (the cache skips the 10 trial calls)
caffeinate -i python3 run_pilot.py openai:gpt-6-sol --conds C1_new_rule,C1_plus_risk
# 3) analysis
uv run --no-project --with pandas python analyze.py > out/report.txt
uv run --no-project --with pandas --with scipy --with statsmodels python code_export_2026-09-25/E3_gpt-6-sol_0924/sol_diagnostics.py
python3 code_export_2026-09-25/E3_gpt-6-sol_0924/read_flagged_summaries.py openai:gpt-6-sol

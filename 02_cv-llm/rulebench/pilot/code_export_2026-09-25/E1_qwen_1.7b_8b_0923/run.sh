#!/bin/zsh
# E1 (2026-09-23): local Qwen3 1.7B and 8B via Ollama, non-thinking, temperature 0, all conditions.
# A: C0_current, C1_new_rule, C5_old_rule, C1_plus_risk (80 cases each). B: B_direct, B_plus_range (60 each).
# 880 calls, about 48 min. The runner at the time was 00_shared_snapshot/run_pilot_v1_qwen_only.py;
# its prompts and Qwen call path are identical to the current run_pilot.py.
# Results -> out/calls.jsonl (cached; rerunning skips finished calls). Report: docs/pilot_2026-09-23.md, "结果" section.
cd "${0:A:h}/../.."
caffeinate -i python3 run_pilot.py qwen3:1.7b qwen3:8b

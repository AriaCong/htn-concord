#!/bin/zsh
# ========================================================================================
# 【实验 2：先导实验 A + B】实际跑过的全部命令，按时间顺序
#
# 从会话记录里原样整理（时间为澳洲东部时间）。这是运行记录，不建议整份直接执行：
# 本地模型要跑几个小时，OpenAI 部分会产生费用。需要重跑时挑对应的几行即可。
# 运行位置：cv-llm-rulebench/pilot/
# 所有调用都追加到 out/calls.jsonl，已跑过的会自动跳过。
# ========================================================================================
VENV_PY="/Users/aria/Documents/PhD GenAI/htn-concord-main/htn-concord/.venv/bin/python"

# ---- 0. 准备（2026-09-23）------------------------------------------------------------
# 下载 NHANES 2017–18 病史问卷（补「有无心血管病」）
curl -sSL -o data/MCQ_J.xpt "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/MCQ_J.XPT"
# 下载本地模型（Ollama，模型存在 ~/.ollama/models）
ollama pull qwen3:1.7b
ollama pull qwen3:8b
python3 pce.py                          # 核对 PCE 原文算例，应打印 True
"$VENV_PY" build_cases.py               # 生成 out/cases.jsonl（A 80 例 + B 60 例）
# 注：第一次生成时 PREVENT 的单位处理有误（把百分数又乘了 100），
#     已修正并删除当时的 calls.jsonl 后重跑。下面是修正后的命令。

# ---- 1. Qwen3 1.7B 和 8B，非思考模式，全部 6 个条件（2026-09-23，880 次）--------------
python3 run_pilot.py qwen3:1.7b qwen3:8b

# ---- 2. Qwen3 8B 思考模式，只跑 2 个条件（2026-09-23 至 24，140 次）--------------------
#      Mac 自动睡眠导致跑了一整晚；之后都用 caffeinate 防止睡眠
python3 run_pilot.py qwen3:8b+think --conds C1_new_rule,B_direct

# ---- 3. Qwen3 14B，非思考模式，全部 6 个条件（2026-09-24，440 次）----------------------
ollama pull qwen3:14b
python3 run_pilot.py qwen3:14b

# ---- 4. OpenAI gpt-6-sol，推理强度 medium，A 部分 2 个条件（2026-09-24，由另一个会话执行）--
#      key 只从环境变量 OPENAI_API_KEY 读（在 ~/.config/openai.env 里设置）
caffeinate -i python3 run_pilot.py openai:gpt-6-sol --conds C1_new_rule,C1_plus_risk --limit 5   # 试跑 5 例，$0.11
caffeinate -i python3 run_pilot.py openai:gpt-6-sol --conds C1_new_rule,C1_plus_risk             # 全量 160 次，共 $1.71

# ---- 5. gpt-6-sol 高推理强度 与 gpt-6-astra（2026-09-25，另一个会话执行；导出时仍在运行）--
#      先用 5 个病例试跑（97163,99890,99187,96022,100711，它们也包含在下面的 30 例里）：
#      同样两条命令，只是 --seqns 换成这 5 个病例
#      正式：30 个病例的子集 = 14 个真实冲突 + 前 6 个合成冲突 + 前 10 个一致病例
python3 - <<'EOF'
import json
cs=[json.loads(l) for l in open("out/cases.jsonl") if json.loads(l)["set"]=="A"]
conf=[c for c in cs if c["group"]=="conflict"]; agr=[c for c in cs if c["group"]=="agree"]
sub=[c for c in conf if c["source"]=="nhanes"]+[c for c in conf if c["source"]=="synthetic"][:6]+agr[:10]
open("out/subset30_seqns.txt","w").write(",".join(str(c["seqn"]) for c in sub))
EOF
S=$(cat out/subset30_seqns.txt)
(caffeinate -i python3 run_pilot.py openai:gpt-6-sol@high --conds C1_new_rule --seqns $S) &
(caffeinate -i python3 run_pilot.py openai:gpt-6-astra    --conds C1_new_rule --seqns $S) &
wait

# ---- 6. 打分与汇总（每轮跑完后都执行一次）---------------------------------------------
#      系统 Python 没有 pandas，所以用 uv 临时装
uv run --no-project --with pandas python analyze.py > out/report.txt

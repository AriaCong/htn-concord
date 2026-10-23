# 代码导出（2026-09-25 快照）

cv-llm-rulebench 到目前为止**实际跑过的全部代码**，按实验分目录，每个文件开头都有中文说明，关键步骤加了行内注释。

- **这是只读快照，方便阅读和存档。** 运行时请用「原始位置」一列里的文件，那里的路径和依赖都是对的。原始文件没有被修改。
- 只包含代码，**不含任何数据和输出**。MIMIC 派生数据不能离开本机，所以也不应放进这个文件夹。

## 两个实验

| 实验 | 问题 | 是否调用大模型 | 结果文档 |
|---|---|---|---|
| **实验 1：MIMIC 病历可行性检查**（2026-09-23） | 出院小结里的数值和结构化表对得上吗？缺血脂时 PREVENT 结论还能判定吗？ | 否，只用正则和计算 | `cv-llm-risk-extraction/docs/feasibility_2026-09-23.md` |
| **实验 2：先导实验 A + B**（2026-09-23 至 25） | A：给出新规则后，模型照新规则办还是退回旧规则？B：藏起胆固醇后，模型能否判断「能不能下结论」？ | 是：Qwen3 1.7B / 8B / 8B 思考 / 14B（本机），gpt-6-sol / astra（OpenAI） | `cv-llm-rulebench/docs/pilot_2026-09-23.md`，网页版 `artifacts/pilot_results.html` |

## 文件清单

| 导出文件 | 属于 | 作用 | 原始位置 |
|---|---|---|---|
| `shared/pce.py` | 实验 2 | PCE 公式（2017 旧规则），已核对原文算例 | `cv-llm-rulebench/pilot/pce.py` |
| `shared/prevent_from_htn_concord.py` | 实验 1、2 | PREVENT 公式（2025 新规则），**复用 HTN-Concord，未修改**，返回百分数 | `htn-concord-main/htn-concord/pipelines/common/prevent.py` |
| `exp1_mimic_feasibility/01_sample.py` | 实验 1 · 第 1 步 | 抽 50 份出院小结 | `cv-llm-risk-extraction/feasibility/01_sample.py` |
| `exp1_mimic_feasibility/01b_extract_subset.sh` | 实验 1 · 第 2 步 | 从 MIMIC 大表筛出这 50 人的记录。**当时是直接在终端执行的，这里按会话记录还原** | 无（原为终端命令） |
| `exp1_mimic_feasibility/02_compare.py` | 实验 1 · 第 3 步 | 小结数值 vs 结构化表 | `cv-llm-risk-extraction/feasibility/02_compare.py` |
| `exp1_mimic_feasibility/03_determinability.py` | 实验 1 · 独立 | 隐去血脂后的可判定性模拟 | `cv-llm-risk-extraction/feasibility/03_determinability.py` |
| `exp2_pilot_A_B/build_cases.py` | 实验 2 · 第 1 步 | 生成 140 个病例和标准答案 | `cv-llm-rulebench/pilot/build_cases.py` |
| `exp2_pilot_A_B/run_pilot.py` | 实验 2 · 第 2 步 | 出题、调用模型、记录回答 | `cv-llm-rulebench/pilot/run_pilot.py` |
| `exp2_pilot_A_B/analyze.py` | 实验 2 · 第 3 步 | 打分、汇总 | `cv-llm-rulebench/pilot/analyze.py` |
| `exp2_pilot_A_B/run_commands.sh` | 实验 2 | 每一轮实际执行的命令，按时间顺序 | 无（按会话记录整理） |

## 实验 2 跑过的轮次

| 轮次 | 模型 | 条件 | 调用次数 | 费用 |
|---|---|---|---|---|
| 1 | Qwen3 1.7B、8B（非思考） | 全部 6 个 | 880 | 免费 |
| 2 | Qwen3 8B（思考模式） | C1_new_rule、B_direct | 140 | 免费 |
| 3 | Qwen3 14B（非思考） | 全部 6 个 | 440 | 免费 |
| 4 | gpt-6-sol（推理强度 medium） | C1_new_rule、C1_plus_risk | 160 | $1.71 |
| 5 | gpt-6-sol（high）、gpt-6-astra | C1_new_rule，30 例子集 | 各 30 | 导出时仍在运行 |

## 数据流

```
实验 1： MIMIC 档案 ─01_sample─▶ 50 份小结 ─01b─▶ 这 50 人的化验/门诊/急诊记录 ─02_compare─▶ 匹配结果
         MIMIC 档案 + NHANES 范围 ─03_determinability─▶ 各阈值下可判定的比例

实验 2： NHANES + MCQ 问卷 ─build_cases（调用 pce + prevent）─▶ cases.jsonl
         cases.jsonl ─run_pilot（Ollama / OpenAI）─▶ calls.jsonl ─analyze─▶ scored.csv + report.txt
```

## 运行环境

- Python：`htn-concord-main/htn-concord/.venv`（有 pandas）；`run_pilot.py` 只用标准库，系统 `python3` 就能跑。
- `analyze.py` 在系统 Python 下用 `uv run --no-project --with pandas python analyze.py`。
- 本地模型：Ollama，模型文件在 `~/.ollama/models`。
- OpenAI key：只从环境变量 `OPENAI_API_KEY` 读取，设置在 `~/.config/openai.env`。**不要把 key 写进任何代码文件。**
- 长时间运行要加 `caffeinate -i`，否则 Mac 会睡眠。

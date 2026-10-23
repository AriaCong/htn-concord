# 先导实验代码导出（2026-09-25）

先导实验跑过的全部代码，按实验分文件夹。结果和结论见 `docs/pilot_2026-09-23.md`。

## 实验一览

| 编号 | 日期 | 实验 | 模型 / 条件 | 调用次数 | 费用 | 报告章节 |
|---|---|---|---|---|---|---|
| E0 | 09-23 | 生成病例 | NHANES 2017-18 → A 80 例、B 60 例 | — | — | 「做了什么」 |
| E1 | 09-23 | 本地 Qwen 基线 | Qwen3 1.7B、8B，非思考；A 四个条件 + B 两个条件 | 880 | 本地 | 「结果」 |
| E2 | 09-24 | 思考模式与更大规模 | 8B 思考（A C1、B-direct）；14B 全部条件 | 580 | 本地 | 「补充（2026-09-24）：8B 思考模式与 14B」 |
| E3 | 09-24 | 前沿推理模型 | gpt-6-sol medium；A C1、C1+PREVENT 值 | 160 | $1.71 | 「补充（2026-09-24）：前沿推理模型 gpt-6-sol」 |
| E4 | 09-25 | 推理强度与规模 | sol@high、gpt-6-astra；A C1，30 例子集（第一次余额用完时只完成 14 / 24 例，E5 补完） | 38 | $2.18 | 「补充（2026-09-25）：推理强度 high 与旗舰 gpt-6-astra」 |
| E5 | 09-25 | 补完 E4；astra 重复采样 | sol@high 余下 16 例；astra A C1 × k = 3（余额再次用完：66 / 41 / 42 例） | 141 | $8.27 | 「补充（2026-09-25，充值后）」 |

费用按标准价估算，没有与 OpenAI 账单核对。

## 文件

| 文件 | 属于 | 作用 |
|---|---|---|
| `00_shared_snapshot/pce.py` | 全部 | PCE 方程（Goff 2013），带原文算例核对 |
| `00_shared_snapshot/prevent_from_htn-concord.py` | 全部 | PREVENT 方程，从 HTN-Concord 只读复制，**返回的是百分数** |
| `00_shared_snapshot/build_cases.py` | E0 | 生成 A、B 病例，标准答案由程序算出 |
| `00_shared_snapshot/run_pilot.py` | E1–E5 | 调模型的 runner（当前版本：Qwen / OpenAI，`@high` 设置推理强度，`--limit`、`--seqns` 选病例，`--rep` 重复采样） |
| `00_shared_snapshot/run_pilot_v1_qwen_only.py` | E1、E2 | Qwen 实验当时用的版本。提示词和 Qwen 调用与当前版本完全相同，当前版本只是新增了 OpenAI |
| `00_shared_snapshot/analyze.py` | E1–E5 | 打分，生成 `out/report.txt` 与 `out/scored.csv`；E5 起把 `decision: null` 记为「拒绝作答」，不再算作「不开药」 |
| `00_shared_snapshot/analyze_v1.py` | E1、E2 | E3 之前的版本，没有「与两个方程对照」「推理文本标记」「费用」三节 |
| `E*/run.sh` | 各实验 | 当时的完整命令，按顺序排列 |
| `E2_…/eq_names.py` | E2 | 模型自称用的方程和阈值（报告中「自称的方程」一表） |
| `E3_…/read_flagged_summaries.py` | E2、E3 | 打印推理文本里「笔误 / 旧方程」关键词的上下文，用于人工核读 |
| `E3_…/sol_diagnostics.py` | E3 | sol 冲突组失败的诊断：离阈值距离、向 PCE 的偏移、log 回归、按冲突方向拆分 |
| `E4_…/make_subset30.py` | E4 | 生成 30 例子集（真实冲突 14、合成冲突 6、一致 10） |
| `E4_…/compare_subset.py` | E4 | 同一批病例上各配置的对比表，以及 astra 的逐例误差 |
| `E4_…/show_case.py` | E4 | 查看单个病例上各模型的回答和推理文本（如 102789，疑似静默替换） |
| `E5_…/bmi_claims.py` | E5 | 列出声称「PREVENT 需要 BMI」的回答（总心血管病方程其实不用 BMI） |

## 怎么跑

- 所有脚本读写的都是 `pilot/out/`，不是本文件夹。`run.sh` 会先切到 `pilot/`，调用的是 `pilot/` 下的**当前**代码；`00_shared_snapshot/` 只是存档，不直接运行。
- 调用会缓存在 `out/calls.jsonl`，重跑时自动跳过已完成的调用，所以重跑 `run.sh` 不会重复收费。
- 系统 Python 没有 pandas，分析脚本用 `uv run --no-project --with pandas …` 运行（`run.sh` 里已写好）。
- OpenAI 实验需要环境变量 `OPENAI_API_KEY`。只能用于 NHANES 和合成病例，**不能用于 MIMIC**（DUA 禁止）。
- Qwen 实验需要本机 Ollama，长时间运行要用 `caffeinate -i` 防止 Mac 睡眠。

## 与报告的出入

`eq_names.py` 重算的数字与报告有两处相差 1 例，都是方程名归类规则不同造成的，结论不受影响：

- 8B 思考模式自称 PCE：报告写 57/80，脚本得 58/80；
- 8B 非思考自称 Framingham：报告「结果」一节写 79/80，脚本得 80/80（报告的 09-24 补充一节也写 80/80）。

报告里 Qwen 的相关系数等数字，最初由上一次会话里的临时代码算出；现在都可以用 `analyze.py`（「reported risk against the true values」一节）重算，数值一致。

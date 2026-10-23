# cv-llm-rulebench

研究的是大模型本身：它们能不能可靠地执行可计算的临床规则。心血管风险方程在这里只是试验台。

- **RQ-A** 指南更新时，模型听上下文还是听记忆（PCE ≥10% 与 PREVENT ≥7.5% 冲突）
- **RQ-B** 信息不全时，模型知不知道能否下结论（区间运算给出精确的可判定性）
- **RQ-C** 用程序打分的强化学习（GRPO）训练本地 Qwen 小模型

所有标准答案都由程序算出，不需要医生裁定。HTN-Concord 是平行项目，这里只以只读方式复用它的代码。

## 文件

| 路径 | 内容 |
|---|---|
| `docs/proposal_v2_2026-09-25.md` | **现行方案 v2**：诊断 → 修复 → 训练，三篇论文的研究问题、方法、指标、预期结果、止损、预算 |
| `docs/proposal_A_B_C_2026-09-23.md` | v1 方案（A / B / C 各自独立），已被 v2 取代，保留作记录 |
| `docs/candidate_research_questions_2026-09-23.md` | 五个候选研究问题的比较 |
| `docs/slides/RuleBench_Overview_zh.pptx`、`RuleBench_Overview.pptx` | 项目介绍幻灯片（中英两版，19 页，样式与 HTN-Concord 一致），源码在 `docs/slides/src/` |
| `docs/pilot_2026-09-23.md` | 先导实验（已定稿 2026-09-25；本地 Qwen3 1.7B / 8B / 14B，前沿模型 gpt-6-sol / astra）：原方案与建议方案的比较，结论在开头 |
| `code_export_2026-09-25/`（及同名 .zip） | 已跑过的全部代码的注释版快照，按实验分目录，见其中 README |
| `pilot/` | 先导实验代码（PCE、病例生成、runner、分析）与输出 |
| `pilot/code_export_2026-09-25/` | 先导实验代码导出：按实验（E0–E4）分文件夹，含当时的命令与临时分析脚本 |
| `docs/cost_estimate_2026-09-23.md` | OpenAI API 与 Colab 成本估算 |
| `artifacts/literature_map.html` | 文献地图（162 篇，含干预阶梯 39 篇），已发布：https://claude.ai/artifact/5NzPdzDhY7yJARKbBgrgjx |
| `artifacts/htn_guidelines.html` | 高血压指南规则全表：2025 版 108 条推荐 + 判断附表；2017 版目前只有部分，已发布：https://claude.ai/artifact/GQ93JHhQsRth9vK2MyGS8o |
| `artifacts/experiment_log.html` | 全部实验记录（每一步做什么、怎么做、代码、结论），已发布：https://claude.ai/artifact/F6f3Cm6AVoVvccsDqyoPtA |
| `artifacts/pilot_results.html` | 先导实验结果页（通俗版），已发布：https://claude.ai/artifact/3Ta9XJh4EGHaestEgYgwfA |
| `artifacts/research_plan.html` | 方案与架构页，已发布：https://claude.ai/artifact/2zJLDHVvHdUFPiAEGGKqcR |

## 相关探索文件夹

- `../cv-llm-risk-extraction/` — 可判定性的可行性检查（50 份出院小结；隐去血脂后的模拟）
- `../cv-llm-invariance/` — 鲁棒性方向的新颖性检索
- `../cv-llm-probing/` — 探针方向的新颖性检索

MIMIC 派生数据（`../cv-llm-risk-extraction/feasibility/out/`）只能留在本地。

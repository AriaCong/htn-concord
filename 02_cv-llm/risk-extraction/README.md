# cv-llm-risk-extraction

候选方向 ②：**从真实病历中抽取变量并计算心血管风险（PREVENT）时，LLM 的错误出在抽取、计算还是缺失处理；以及在数据缺失时，它能否判断结论其实已经确定。**

真值不需要医生：抽取以 MIMIC 结构化表（labevents、OMR）为准，计算以已发表方程为准，「能否判定」由对缺失变量做区间运算得出。

**状态：** 探索期，未决定转向。与 `htn-concord-main/` 平行。

| 文件 | 内容 |
|---|---|
| `docs/novelty_search_2026-09-23.md` | 新颖性检索 + MIMIC 可行性核查 |
| `docs/feasibility_2026-09-23.md` | 50 份出院小结 vs 结构化表；隐去血脂后的可判定性模拟 |
| `feasibility/` | 上述检查的脚本（`01`–`03`） |

> `feasibility/out/` 为 MIMIC 派生数据（含病历原文），受数据使用协议约束，只能留在本地。

复用：`htn-concord/pipelines/common/prevent.py`、MIMIC 管线（8,919 份档案、出院小结）、runner。

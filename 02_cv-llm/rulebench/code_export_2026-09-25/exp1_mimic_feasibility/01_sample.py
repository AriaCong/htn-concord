# ========================================================================================
# 【实验 1：MIMIC 病历可行性检查】（2026-09-23，不调用任何大模型）
# 问题：真实出院小结里写的数值，和 MIMIC 结构化表对得上吗？缺血脂时，PREVENT 结论还能判定吗？
# 结论写在：cv-llm-risk-extraction/docs/feasibility_2026-09-23.md
# 运行顺序：01_sample.py → 01b_extract_subset.sh → 02_compare.py；03_determinability.py 独立运行
# 数据规则：MIMIC 派生数据（feasibility/out/）只能留在本机，不能上传、发给 API 或发布。
#
# 本文件：第 1 步，抽样。
# 做什么：从 HTN-Concord 的 MIMIC 队列（30–79 岁）里按种子 20260923 抽 50 份出院小结，
#        「结构化数据能算出 PREVENT」和「算不出」各 25 份。
# 输入：HTN-Concord 的 mimic_profiles_*.csv、mimic_taskc_notes_*.csv
# 输出：out/sample_notes.csv
# 原始位置：cv-llm-risk-extraction/feasibility/01_sample.py
# ========================================================================================

"""Pick 50 index discharge summaries from the HTN-Concord MIMIC cohort (ages 30-79).

Stratified 25/25 on whether PREVENT is computable from structured data, so the check
covers both the complete-input and the naturally-missing case. No LLM is called.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "htn-concord-main/htn-concord/data/mimic/processed"
OUT = Path(__file__).parent / "out"
SEED = 20260923

prof = pd.read_csv(PROC / "mimic_profiles_primary_prior_plus_index.csv", low_memory=False)
notes = pd.read_csv(PROC / "mimic_taskc_notes_prior_plus_index.csv", low_memory=False)

# 只保留 PREVENT 适用的年龄段 30–79 岁
prof = prof[(prof.age >= 30) & (prof.age <= 79)]
cand = notes.merge(prof[["subject_id", "hadm_id", "age", "sex", "prevent_10yr"]],
                   on=["subject_id", "hadm_id"], how="inner")
cand["prevent_ok"] = cand.prevent_10yr.notna()
print("candidate notes:", len(cand), "| prevent computable:", int(cand.prevent_ok.sum()))

# 分层抽样：能算出 PREVENT 的 25 份 + 算不出的 25 份
pick = pd.concat([
    cand[cand.prevent_ok].sample(25, random_state=SEED),
    cand[~cand.prevent_ok].sample(25, random_state=SEED),
])
pick.to_csv(OUT / "sample_notes.csv", index=False)
print("wrote", len(pick), "notes;", pick.subject_id.nunique(), "subjects")

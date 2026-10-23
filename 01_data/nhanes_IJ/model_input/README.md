# 模型输入表与 PREVENT 风险（5,816 人）

由 `../scripts/run.sh` 的最后两步生成：`export_model_input.py` 和 `compute_prevent.py`。

## 文件

| 文件 | 内容 |
| :--- | :--- |
| `nhanes_IJ_model_input.csv` | 5,816 人，一人一行，按 SEQN 唯一对应。十项 PREVENT 输入没有任何缺失 |
| `nhanes_IJ_prevent.csv` | 同样 5,816 人的 PREVENT 10 年总 CVD 风险（%），以及风险是否 ≥7.5%；用 SEQN 与模型输入表对应 |
| `prevent_coefficient_check.csv` | prevent.py 的 20 个系数与原始补充表 S12A 的逐项比对结果，全部完全相同 |
| `export_summary.json`、`prevent_summary.json` | 人数、缺失、风险分布、实现代码和补充表的 SHA256 |

## 模型输入表的列

| 列 | 说明 |
| :--- | :--- |
| `SEQN`、`cycle` | 参与者编号和周期（I 或 J） |
| `age_years`、`sex` | 年龄（30–79 岁）、性别（male 或 female） |
| `total_chol_mgdl`、`hdl_mgdl` | 总胆固醇、HDL，单位 mg/dL |
| `sbp_mean` | 听诊收缩压平均值，单位 mmHg |
| `egfr` | CKD-EPI 2021 公式计算的 eGFR；I 周期的肌酐先校准到 J 尺度再计算 |
| `diabetes`、`on_bp_meds`、`current_smoker`、`statin` | 0 表示否，1 表示是 |
| `on_bp_meds_source`、`current_smoker_source` | 答案来源：direct 为直接回答，skip_logic 为跳题还原 |
| `non_hdl_mgdl`、`dbp_mean`、`creatinine_J_scale` | 辅助的派生量 |
| `wtmec_pooled`、`wtint_pooled`、`sdmvpsu`、`sdmvstra` | 合并两个周期后的调查权重和设计变量；只有做人群估计时才需要 |
| `race_ethnicity_ridreth3`、`bmi`、`uacr_mg_g`、`hba1c_pct` | 原始值，供 PCE 或 PREVENT 增强版使用。这几列允许有少量缺失：BMI 和 UACR 各缺 36 人，HbA1c 缺 3 人，DBP 缺 8 人 |

## PREVENT 计算

- **模型**：PREVENT 基础版 10 年总 CVD 风险（Khan 2024，Circulation，补充表 S12A）。
- **实现**：调用共用模块 `00_shared/pipelines/common/prevent.py`（原为 HTN-Concord 编写）。每次运行都会记录这个文件的 SHA256。
- **计算前的两项核对**（任何一项不符，运行就会停止）：
  1. 20 个系数（含常数项）与 S12A 原表逐项完全相同；
  2. 用 S12A 的示例输入计算，结果与原表一致：女性 14.684%，男性 16.317%。
- **结果**（不加权的个人风险）：
  - 中位数 3.79%，四分位间距 1.30%–9.68%，最大 62.7%；
  - I 周期中位数 3.50%，J 周期中位数 4.07%；
  - 1,859 人（32.0%）风险 ≥7.5%。

注意：
- 风险是逐人计算的，没有使用调查权重。要推断美国人口的情况时，才需要配合合并权重。
- 本文件夹只有 PREVENT 风险，没有生成治疗推荐，也没有计算 PCE。

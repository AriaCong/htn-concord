# NHANES I+J（2015–2018）清理数据

清理规则见 `CLEANING_LOGIC.md`（2026-10-20 确认后执行）。运行 `sh scripts/run.sh` 即可完整重建：`clean_nhanes_ij.py` 负责清理，`verify.py` 重新读取原始 XPT 做独立核对。

## 文件

| 路径 | 行数 | 内容 |
| :--- | ---: | :--- |
| `output/nhanes_IJ_original_values.csv` | 19,225 | 研究字段的原值，按人一行，`cycle` 列标明 I 或 J |
| `output/nhanes_IJ_original_values_all_columns.csv` | 19,225 | 所用 13 个表的全部原始列 |
| `output/nhanes_IJ_derived.csv` | 19,225 | 派生字段，按 SEQN 与原值表一一对应 |
| `output/rxq_rx_IJ_original_rows.csv` | 39,290 | 处方药长表原样，一人可多行 |
| `output/rxq_drug_original_rows.csv` | 1,551 | 药物词典原样 |
| `output/analysis/complete_*.csv` | 5,816 | 分析集中十项输入全部已知的人 |
| `output/analysis/incomplete_*.csv` | 1,291 | 分析集中至少一项输入未知的人 |
| `model_input/nhanes_IJ_model_input.csv` | 5,816 | complete 组整理成的模型输入表，十项输入以 0/1 和数值表示，详见 `model_input/README.md` |
| `model_input/nhanes_IJ_prevent.csv` | 5,816 | 这批人的 PREVENT 10 年总 CVD 风险（%） |
| `audit/` | | 源文件哈希、人数流转、每人状态、缺失原因计数、0 值还原记录、派生方法、全部检查结果 |

## 人数

| | I | J | 合计 |
| :--- | ---: | ---: | ---: |
| 全部参与者 | 9,971 | 9,254 | 19,225 |
| 分析集（年龄 30–79、无 CVD 病史、数值在定义域内、非妊娠） | 3,592 | 3,515 | 7,107 |
| complete | 3,018 | 2,798 | 5,816 |
| incomplete | 574 | 717 | 1,291 |

**complete 组里答案的来源**：

- 降压药：1,839 人是直接回答，3,977 人由跳题还原；
- 吸烟：2,400 人是直接回答，3,416 人由跳题还原。

如果想做“只用直接回答”的敏感性分析，可以按 `*_source` 列筛选。

**incomplete 组还缺什么**：

- eGFR（745 人）、TC/HDL（724 人）、SBP（580 人）：这些人没抽血或没测血压；
- 糖尿病（214 人）：回答“临界”或拒答；
- 他汀（145 人）：药名无法识别；
- 降压药（11 人）、吸烟（6 人）：问卷回答是拒答或“不知道”。

## 派生表中的主要字段

| 字段 | 含义 |
| :--- | :--- |
| `sbp_mean`、`dbp_mean` | 听诊血压的平均值，两个周期都用这个口径；DBP=0 的读数不计入平均，次数记在 `dbp_zero_readings` |
| `sbp_mean_oscillometric_J_only` | J 周期的示波血压，用于敏感性分析 |
| `creatinine_J_scale`、`egfr` | I 周期的肌酐按 CDC 方程校准到 J 的尺度后，再用 CKD-EPI 2021 计算 eGFR |
| `wtint_pooled`、`wtmec_pooled` | 合并两个周期时使用的权重（原两年权重 ÷ 2），配合 SDMVPSU、SDMVSTRA 使用 |
| `on_bp_meds` / `_source` | 是否在服降压药；来源为 direct（直接回答）、skip_logic（跳题还原）或 unknown |
| `current_smoker` / `_source` | 当前是否吸烟，来源取值同上 |
| `diabetes`、`diabetes_borderline`、`hba1c_ge_6_5` | 糖尿病自报、临界、HbA1c 筛查结果，三者分开保存 |
| `cvd_history`、`statin` / `statin_reason` | 心血管病史、是否服他汀及判定依据 |

## 读取方式

```python
import pandas as pd
df = pd.read_csv(path, keep_default_na=False, na_values=["__SOURCE_MISSING__"],
                 float_precision="round_trip", low_memory=False)
```

## 保证

- 原始文件只读，运行前后 SHA256 相同。
- 原值表与 XPT 逐格一致，唯一的处理是把 pandas 误读的 0 还原，共 96,905 格，见 `audit/xport_zero_decoding.csv`。
- 不填补缺失，不截断异常值，不删除记录。被排除的人仍保留在原值表中，排除原因见 `audit/row_status.csv`。
- 清理步骤本身不计算风险。PREVENT 风险只在 `model_input/` 中、基于 complete 组单独计算；本流程不生成治疗推荐。

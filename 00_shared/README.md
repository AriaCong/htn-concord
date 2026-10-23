# 00_shared：共用模块

供 `01_data/nhanes_IJ` 和 `02_cv-llm/*` 引用的计算与数据管线。最初为 HTN-Concord 编写，2026-10-23 移到这里，git 历史保留。GitHub CI 每次推送都会运行这里的测试。

| 模块 | 内容 | 谁在用 |
| :--- | :--- | :--- |
| `pipelines/common/prevent.py` | PREVENT 基础版 10 年总 CVD 风险（Khan 2024，补充表 S12A），20 个系数与原表完全一致 | nhanes_IJ 的 `compute_prevent.py`、rulebench 先导、risk-extraction、文献核查脚本 |
| `pipelines/common/derive.py` | eGFR（CKD-EPI 2021，无种族项），以及 BP 分期、非 HDL 等派生量 | nhanes_IJ（eGFR 不取整，传 `decimals=None`）、MIMIC 管线（eGFR 保留 1 位小数） |
| `pipelines/common/validate.py`、`qa.py` | 档案 schema 校验与 QA | MIMIC 管线 |
| `pipelines/mimic/` | MIMIC-IV（hosp + ED + Note）到病人档案的完整管线 | proposal v2 的真实病历分支、MIMIC 迁移测试集 |
| `vocab.py`、`schemas/patient_profile.schema.json` | 共用词表与档案格式 | 以上各模块 |
| `scripts/` | MIMIC 输入清单、itemid 核对、标签产出检查 | MIMIC 管线 |

## 运行

```sh
cd 00_shared
uv run --no-project --python 3.12 --with-requirements requirements.txt python -m pytest -q      # 测试
uv run --no-project --python 3.12 --with-requirements requirements.txt python -m pipelines.mimic.build_profiles   # 生成 MIMIC 档案（只在本机运行）
```

## 只在本机、不进 git 的内容

- `data/mimic/`：MIMIC 病人档案，共 8,919 份，`prior_only` 和 `prior_plus_index` 两种口径各一份；外加 Task C 病历。受 PhysioNet 数据使用协议约束，只能在本机使用，只能由本机开源模型处理。
- `references/`：PREVENT 论文和补充材料，有版权。`compute_prevent.py` 优先从这里读取 S12A 来核对系数；找不到时，改用仓库里已提交的系数对照表。

MIMIC 原始数据从 `01_data/raw/mimic-iv-3.1` 读取，也可以用环境变量 `MIMIC_DIR` 指定位置。

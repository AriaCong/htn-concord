# PhD GenAI 项目总目录

GitHub：https://github.com/AriaCong/phd-genai（原 `AriaCong/htn-concord`，旧链接会自动跳转到这里）。整个文件夹就是这个 git 仓库的工作目录。

整理日期：2026-10-23。研究主线：以心血管风险方程和高血压指南为试验台，研究大语言模型如何执行可计算的临床规则。

```
PhD GenAI/
├── 01_data/
│   ├── raw/                 原始数据（只读，约 60 GB）
│   └── nhanes_IJ/           NHANES I+J 清理流程、清理结果、模型输入、PREVENT 风险
├── 02_htn-concord/          HTN-Concord：指南引擎、数据管线、benchmark（完整 git 历史保留）
├── 03_cv-llm/
│   ├── rulebench/           LLM 研究主线：proposal v2、先导实验 pilot、幻灯片
│   ├── invariance/          候选方向①：同义改写下的一致性
│   ├── risk-extraction/     候选方向②：病历抽取与风险计算（含 MIMIC 可行性检查）
│   └── probing/             候选方向③：模型内部表征的探针分析
├── 04_literature_review/
│   └── 2026-10-19/          研究方向与科研缺口核查
└── _archive/                已过期、但暂时保留的文件
```

## 01_data

**raw/**：原始数据只放在这里，所有代码都从这里读取。

| 文件夹 | 内容 |
| :--- | :--- |
| `NHANES/` | 2017–2018 周期 J：32 个 XPT 文件、CDC codebook、死亡链接文件 |
| `NHANES_I/` | 2015–2016 周期 I：30 个 XPT 文件、codebook、死亡链接文件 |
| `NHANES_L_separate/` | 2021–2023 周期 L，单独存放，不参与 I+J 合并；附 J↔L 变量对照表 |
| `NHANES_J_I_variable_crosswalk.csv` | J↔I 变量对照表，说明见同名 README |
| `mimic-iv-3.1/`、`mimic-iv-ed-2.2/`、`mimic-iv-note-…/`、`eicu-…/`、`hospitalized-patients-with-heart-failure…/` | PhysioNet 受限数据（每个文件夹都有对应的原始 zip）。只能在本机使用，不能上传到第三方服务 |

**nhanes_IJ/**：唯一的一份清理版本，2026-10-20 按你确认的逻辑生成。

- 清理逻辑：`CLEANING_LOGIC.md`；文件说明：`README.md`。
- 一键重建：`sh 01_data/nhanes_IJ/scripts/run.sh`，依次完成清理、独立核对、导出模型输入、计算 PREVENT。
- 主要输出：
  - `output/`：19,225 人的原值表和派生表；
  - `output/analysis/`：分析集 7,107 人，其中 complete 5,816 人、incomplete 1,291 人；
  - `model_input/`：5,816 人的模型输入表和 PREVENT 风险。
- `review-2026-10-20/`：独立复核报告。其中列出的待处理问题包括糖尿病定义、吸烟证据冲突、透析和他汀分类。

## 02_htn-concord

- HTN-Concord 是与 cv-llm 平行的另一个项目。
- `02_htn-concord/Data` 是指向 `01_data/raw` 的符号链接，所以 pipeline 里原有的 `Data/` 路径照常可用；`.gitignore` 已排除它。
- 运行测试：在 `02_htn-concord/htn-concord` 里执行 `uv run --no-project --python 3.12 --with-requirements requirements.txt python -m pytest -q`。CI 会在每次推送时自动运行同样的测试。

## 03_cv-llm

- `rulebench/` 的现行方案是 `docs/proposal_v2_2026-09-25.md`；先导实验的结论见 `docs/pilot_2026-09-23.md`。
- `pilot/code_export_2026-09-25/` 和 `code_export_2026-09-25/` 是 9 月 25 日的代码快照。快照里注释写的“原始位置”是当时的路径，没有改。

## 2026-10-23 整理记录

**删除**：

| 内容 | 删除前的核实 |
| :--- | :--- |
| `htn-concord-main/Data/`（60 GB） | 105 个文件与 `Raw data/` 逐个比对 SHA256，全部相同 |
| HTN-Concord 的 `.venv`、各处 `__pycache__`、`.pytest_cache`、`.DS_Store` | 均可重建 |
| `cv-llm-rulebench/code_export_2026-09-25.zip` | 解压后与同名文件夹内容完全相同 |
| `cv-llm-rulebench/pilot/data/MCQ_J.xpt` | 与 `01_data/raw/NHANES/MCQ_J.XPT` 的 SHA256 相同；引用它的代码已改为读取 raw |

**移入 `_archive/`**：

- `PREVENT 风险计算分析集.docx`
- `数据是否足够与计算准确性.md`

两份文件依据的都是已删除的旧清理结果：旧 eGFR 上限 140，样本数 2,771。

**路径修改**：

- 修改了 13 个仍在使用的脚本里的路径引用；
- 修复了 pilot-gate 的 worktree 链接，并把它原来的绝对符号链接改成相对链接；
- 搬家后重跑 `01_data/nhanes_IJ/scripts/run.sh`：134 项检查全部通过，12 个输出 CSV 与搬家前逐字节相同。

## 2026-10-23 GitHub 更新

- 仓库从 `htn-concord` 改名为 `phd-genai`，仓库根目录就是本文件夹。HTN-Concord 的全部内容移到了 `02_htn-concord/`，git 历史完整保留。
- 合并了 PR #13（difficulty ladder K2），并把 pilot-gate 分支上没推送的交接文档提交了上去。之后移除了 pilot-gate worktree，因为它的分支已经合并。
- **仓库只放代码和文档，不放数据**，规则写在 `.gitignore` 里：
  - 原始数据不上传，MIMIC 和 eICU 受 PhysioNet 数据使用协议约束，绝不上传；
  - 个人级的清理结果和样本不上传；
  - 有版权的论文、补充材料和指南全文不上传；
  - `.env` 等密钥文件不上传。

## 从零复现 NHANES I+J 的结果

```sh
python 01_data/download_nhanes.py      # 从 CDC 下载 I/J 原始文件，逐个核对 SHA256（加 --all 会同时下载 L）
sh 01_data/nhanes_IJ/scripts/run.sh    # 依次运行清理、核对、导出模型输入、计算 PREVENT（需要 uv）
```

`01_data/nhanes_manifest.csv` 记录了每个文件的官方下载地址和 SHA256。

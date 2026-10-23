# HTN-Concord — 数据字典与清洗策略（v1）

> 🌐 **本文是 `HTN-Concord_DataDictionary_and_CleaningStrategy.md` 的中文对照版。两份文件必须同步修改。**
> 若两边冲突，以**英文版为准**，并立刻回来修正本文。

范围：成人**原发性（本态）高血压**，用药的启动与强化，加上少数高价值禁忌症（妊娠、血管神经性水肿史、高钾 K⁺ ≥5.5 mmol/L）。
**eGFR 降低*不是*禁忌症** —— 指南在 eGFR <60 时*优先推荐* ACEI/ARB；它属于合并症修饰项加监测要求（2026-07-18 更正）。
本文列出用到的每一张表，定义喂给确定性指南引擎的变量，并规定每个数据源如何被清洗成规范的 `PatientProfile`。

编写于 2026-07-08。与 Notion 的《🇬🇧 HTN-Concord — Master Plan (English)》主页（即原先题为 "Consolidated Plan" 的那一页）以及 2025 AHA/ACC 指南（DOI 10.1161/HYP.0000000000000249）保持一致。

> 📘 **配套文档。** 本文件是**参考手册** —— 覆盖四个数据集的每一张表，并保留更正历史。
> 若需要单一底料的**走查**（每一列为何被选中、三层数据类型契约、缺失数据策略及为何不做填补、
> NHANES 逐步执行顺序），请见 `HTN-Concord_DataProcessing_Walkthrough_zh.md`
> （英文版：`..._Walkthrough.md`）。

---

## 0. 数据现状（请先读这一节）

| 数据源 | 本地已有？ | 位置 | 备注 |
|---|---|---|---|
| **NHANES 2017–2018（cycle J）** | ✅ | `Data/NHANES/` | 13 个 `.XPT` 文件。Pipeline 已建**并已跑通**：4,806 份 schema 合法的成人档案 + QA 报告。见 §1。**缺口：`MCQ_J` 尚未下载** —— 它是 `clinical_cvd`（Stage-1 启动触发因子之一）的来源，因此该字段对每一行 NHANES 都是 null。 |
| MIMIC-IV 3.1（hosp + icu） | ✅ | `Data/mimic-iv-3.1/` | gzip CSV |
| MIMIC-IV-Note 2.2 | ✅ | `Data/mimic-iv-note.../note/` | `discharge.csv.gz` = 1.1 GB |
| MIMIC-IV-ED 2.2 | ✅ | `Data/mimic-iv-ed-2.2/ed/` | gzip CSV |
| eICU-CRD 2.0 | ✅ | `Data/eicu-collaborative-research-database-2.0/` | 纯 CSV |

**数据集 → 任务：** NHANES → Task A/B + PREVENT + 死亡率（Task D）。MIMIC-IV（+ED+Note）→ Task B/C + `dod` 合理性。
eICU → **2026-07-18 已降级**为约 500 例住院的弃权校准探针（eICU 每条血压都是急性场景，建完整 pipeline 会产出约 20 万行没有决策标签的数据）。

> ⚠️ **「eICU 没有病历文本」这个说法是错的。** eICU 带有一个 306 MB 的 `note.csv`。结论仍然成立 —— 其内容是路径/数值片段而非叙事文本，因此依然不适合 Task C —— 但凡本文档此前作此断言之处，前提都是假的（2026-07-18 更正）。

---

## 1. NHANES 2017–2018（cycle `_J`）—— 主数据源

文件为 SAS `.XPT`；每位受访者一行，主键为 **`SEQN`**。计划中的待决问题：只用 cycle **J**，还是合并疫情前的 **`P_`（2017–2020 年 3 月）** 文件（`P_` 变量名相同，但连接键与权重不同 —— **切勿**把 J 和 P_ 混进同一个数据框）。下面的建议按 **J** 来写；若做合并，请把每个 `*_J` 换成 `P_*`，并改用 `WTMECPRP` 权重。

### 用到的表与变量

| 文件（`_J`） | 变量 | 含义 | 单位 / 编码 |
|---|---|---|---|
| **DEMO_J** | `SEQN` | 受访者 ID（所有文件的连接键） | int |
| | `RIDAGEYR` | 筛查时年龄 | 岁；**80 = 顶码「80+」** |
| | `RIAGENDR` | 性别 | 1=男，2=女 |
| | `RIDRETH3` | 种族/族裔 | **仅用于亚组报告** —— 引擎是种族中立的 |
| | `WTMEC2YR`、`SDMVPSU`、`SDMVSTRA` | MEC 权重、PSU、层 | 用于加权患病率/死亡率 |
| **BPXO_J** | `BPXOSY1–3` | 收缩压，示波法，第 1–3 次读数 | mmHg |
| | `BPXODI1–3` | 舒张压，第 1–3 次读数 | mmHg |
| **BIOPRO_J** | `LBXSCR` | 血清肌酐 | mg/dL |
| | `LBXSKSI` | 血清钾 | **mmol/L（SI 单位）** |
| **ALB_CR_J** | `URDACT` | 尿白蛋白/肌酐比（UACR） | mg/g |
| | `URXUMA`、`URXUCR` | 尿白蛋白、尿肌酐 | UACR 的来源 |
| **DIQ_J** | `DIQ010` | 「医生是否告知您患有糖尿病」 | 1=是，2=否，3=临界，7=拒答，9=不知道 |
| **BPQ_J** | `BPQ020` | 是否曾被告知高血压 | 1/2/7/9 |
| | `BPQ030` | 是否被告知高血压 ≥2 次 | 1/2/7/9 |
| | `BPQ040A` | 是否被告知需服降压药 | 1/2/7/9 |
| | `BPQ050A` | **目前正在**服降压药 | 1/2/7/9 |
| **RXQ_RX_J** | `RXDDRUG`、`RXDDRGID` | 药名 / 通用 ID | 长表格式，每个 `SEQN` 多行 |
| | `RXDCOUNT` | 处方数量 | int |
| **BMX_J** | `BMXBMI` | 体质指数 | kg/m² |
| **SMQ_J** | `SMQ020` | 一生吸烟是否 ≥100 支 | 1/2 |
| | `SMQ040` | 目前是否吸烟 | 1=每天，2=有些天，3=完全不 |
| **TCHOL_J** | `LBXTC` | 总胆固醇 | mg/dL |
| **HDL_J** | `LBDHDD` | HDL 胆固醇 | mg/dL |
| **NCHS LMF** | `MORTSTAT`、`PERMTH_EXM`、`UCOD_LEADING` | 死亡状态、人月、死因 | 仅 Task D |
| **GHB_J** | `LBXGH` | 糖化血红蛋白（%） | 糖尿病 flag 的化验分支（≥6.5%）；**此前本表遗漏**，尽管 pipeline 一直在用 |
| **RXQ_DRUG** | `RXDDRGID`、`RXDDRGNM` | 药品信息查找表 | 与 `RXQ_RX_J` 连接做药物→类别映射；**此前本表遗漏** |
| **DEMO_J** | `RIDEXPRG` | 妊娠状态 | 1 = 妊娠，2 = 非妊娠，3 = 无法确定。✅ **2026-07-19 已接入（HC-24）** → `pregnant` → `contraindications`；见清洗规则 2 |
| **MCQ_J** ⚠️ | `MCQ160B–F` | 心衰 / 冠心病 / 心绞痛 / 心梗 / 卒中 | **尚未下载。** 是 `clinical_cvd` 的唯一来源；在补上之前，该触发因子对每一行 NHANES 都是 null |

### 清洗规则 —— NHANES

1. **缺失哨兵值。** 问卷中的 `7`/`9`（拒答/不知道）→ `NA`，绝不当作数据。化验/血压的空值保持 `NA`。
2. **队列过滤。** `RIDAGEYR ≥ 18` **且**至少 1 次非空的示波法读数。
   **妊娠（2026-07-18 更正）：** 妊娠在 NHANES 里**是**可以查到的 —— `DEMO_J.RIDEXPRG`（1 = 妊娠），共 55 名受访者，其中 **45 名目前就在已导出的档案表里、且 `contraindications` 列表为空**。旧文字指向 `RHQ*`（磁盘上没有，也并不需要），而 `derive.py` 错误地断言妊娠不可查。这是**安全**缺口而非表面问题：一旦 HC-36 落地，引擎可能对孕妇输出「启动 ACEI/ARB」并把它当作**标准答案** —— 恰恰是 `unsafe_recommendation` 这个指标要抓的东西。要求：读取 `RIDEXPRG`，置 `pregnancy` flag，并且 —— 由于妊娠期高血压管理不在范围内 —— 让引擎**弃权**（`pregnancy_management_out_of_scope`），同时仍然发出该 flag 供禁忌评分使用。

   ✅ **2026-07-19 完成（HC-24，PR #5），与上述规范完全一致。** `clean_demo` 从 `RIDEXPRG` 带出 `pregnant` 并**保持三值**：该问题只问 20–44 岁女性，因此 `<NA>` 是常态，把缺失的大多数映射为 `False` 等于对从未被问过的人断言「未怀孕」。`derive.contraindications()` 只认阳性。引擎把它作为**先于分期的范围闸门**，因此弃权不依赖血压 —— 45 位孕妇档案现已全部弃权，而此前她们 135 个渲染 case 中有 129 个被判为 `lifestyle_only`。锚点：`HTN-CONCORD:abstain-out-of-scope`。药物类别后果仍属 **HC-36**；其余范围守卫（难治性/继发性高血压、终末期肾病、高血压急症）仍属 **HC-28**。
3. **血压汇总 —— 用均值（HC-23 于 2026-08-08 裁定）。** 要求至少 1 组有效读数。范围核查：SBP 60–290、DBP 30–200；不合理 → `NA`（绝不截断）。
   > ✅ **HC-23 已对照指南原文裁定 —— 代码一直是对的，错的是文档。** 本节此前要求「处处用中位数」（2026-07-18 统一），并把 `pipelines/nhanes/clean.py` 计算均值标记为未落地。对照 `docs/guidelines/jones-et-al-2025-*`（2025 AHA/ACC，DOI `10.1161/HYP.0000000000000249`）核查后，结论完全反转：指南通篇要求的是**平均值** —— *「诊室血压应基于可得读数的平均值」*、§5.2.7 *「≥2 次就诊、每次 ≥2 次读数的平均值」*，分期阈值本身也写作 *「SBP 平均值 ≥130 mm Hg」*。「中位数」一词在整份指南中只出现一次，且出现在与减重反弹相关的无关段落里。
   >
   > 2026-07-18 的论证理由是**统一口径**，却由此得出**中位数**的结论 —— 这一步并不成立：均值同样能统一口径。唯一真正支持中位数的理由，是它对 MIMIC 中不规则、右偏的 OMR 读数次数更稳健；但那是工程层面的考量，而代价是让引擎在 `bp_stage`（整条管线中最吃重的输入）上偏离指南。该取舍予以否决，改由范围门、MIMIC 的「≥2 个不同日期」要求，以及一项**中位数敏感性分析**（与已承诺的「丢弃第 1 次读数」敏感性分析并列报告）来处理。
   >
   > **无需重新导出，任何数字都不移动。** 已交付的 `nhanes_profiles_J.csv` 一直都符合指南；MIMIC 同样使用均值，两条臂因此保持一致。与其他所有已编码规则一样，该汇总规则仍在 HC-49 临床表面效度审阅的范围内。
   >
   > **不受此影响的既有局限：** NHANES 是单次就诊设计，因此满足「≥2 次读数的平均」，但不满足「≥2 次就诊」—— 这一偏差此前已记录为对 Stage-1 的轻微过度触发。
   *仍未决 —— 必须在基准冻结前定下：* 是否**丢弃第 1 次读数**。开关已经存在（`clean.py`，`discard_first=False`）。丢弃它几乎不损失样本（只有 10 行仅有单次读数），而示波法第一次读数偏高，所以保留它会抬高 Stage 1/2、进而抬高启动用药的标签。请报告两种设定下的分期分布敏感性表。
4. **分期**（引擎输入，在清洗之后计算）：Elevated 120–129/<80；**Stage 1 130–139 或 80–89**；**Stage 2 ≥140 或 ≥90**。使用**均值** SBP/DBP（依上文 §3；HC-23 于 2026-08-08 裁定）。
5. **eGFR：** 用 **CKD-EPI 2021 无种族版**从 `LBXSCR`、年龄、性别推导（见 §6）。不得使用任何含种族项的方程。
6. **血钾**本身已是 SI 单位（mmol/L）—— 无需换算；禁忌 flag 为 `K⁺ ≥ 5.5`。
7. **CKD（2026-07-18 更正 —— 是「或」不是「且」）。** CKD = **eGFR <60 mL/min/1.73 m² *或* UACR ≥30 mg/g**（KDIGO，也是指南原文的措辞：*「白蛋白尿 ≥30 mg/g **或** eGFR <60」*）。这一个定义同时驱动 Stage-1 启动触发因子与 ACEI/ARB 优选修饰项（HC-35）。代码一直是正确的「或」；是字段名 `ckd_albuminuria` 和「CKD **合并**蛋白尿」的表述暗示了「且」，应当读作 `ckd`。化验缺失 → **`NA`，绝不是 `False`**（Kleene 或）。
8. **糖尿病 flag：** `DIQ010==1`。临界（3）→ 对 Stage-1 启动触发因子而言不算糖尿病，但单独记录。
9. **在治 flag：** `BPQ050A==1`（目前正在服降压药）—— PREVENT（`treated BP`）与「启动 vs 强化」都需要它。
10. **药物 → 类别：** `RXQ_RX_J` 是长表；通过 NHANES 药品信息文件把 `RXDDRGID` 映射到 ATC/治疗学分类，再收敛到引擎类别（噻嗪/ACEI/ARB/二氢吡啶类 CCB/其他）。透视成每个 `SEQN` 一行、值为类别集合。
11. **吸烟（PREVENT）：** 当前吸烟者 = `SMQ040 ∈ {1,2}`。
12. **连接：** 所有 `_J` 文件按 `SEQN` 左连接到 `DEMO_J`；结果为每位受访者一份 `PatientProfile`。
13. **抽样设计：** 在数据框上保留 `WTMEC2YR/SDMVPSU/SDMVSTRA`；只在做人群层面估计时使用，**绝不**用于逐病例标签。

---

## 2. MIMIC-IV 3.1 —— 主要真实 EHR（Task B & C、死亡率）

主键：`subject_id`（病人）、`hadm_id`（住院）。时间按病人做了去标识/日期平移（年份平移，间隔保留）。`hosp/*` = 全院范围；`icu/*` 不在高血压主线上。

### 用到的表与变量

| 表 | 变量 | 含义 | 清洗要点 |
|---|---|---|---|
| **hosp/omr** | `subject_id`、`chartdate`、`seq_num`、`result_name`、`result_value` | 门诊测量 | `result_name="Blood Pressure"` → `result_value` 是 **`"SYS/DIA"` 字符串**；另有 *Sitting/Standing/Lying* 变体。`eGFR` 虽存在但极稀疏（约 279 行）→ 改为自行推导。体重(Lbs)/身高(Inches)/BMI 也在这张表里。 |
| **hosp/labevents** | `subject_id`、`hadm_id`、`itemid`、`charttime`、`valuenum`、`valueuom`、`ref_range_*`、`flag` | 化验 | **肌酐 `itemid=50912`、钾 `itemid=50971`**（依计划）。`value` 可能是 `"___"`（去标识）→ 请用 `valuenum`。先按 `itemid` 过滤（该表 2.4 GB）。 |
| **hosp/d_labitems** | `itemid`、`label`、`fluid`、`category` | 化验字典 | 连接以确认 itemid 与单位 |
| **hosp/prescriptions** | `subject_id`、`hadm_id`、`drug`、`starttime`、`stoptime`、`route`、`dose_val_rx` | 住院用药 | 药物→类别映射；`drug` 是自由文本 |
| **hosp/diagnoses_icd** | `subject_id`、`hadm_id`、`seq_num`、`icd_code`、`icd_version` | 编码诊断 | **ICD-9（`version=9`）与 ICD-10（`10`）混用** → 两套都要映射。高血压银标准 + 合并症来源。 |
| **hosp/d_icd_diagnoses** | `icd_code`、`icd_version`、`long_title` | 诊断字典 | 可读标签 |
| **hosp/patients** | `subject_id`、`gender`、`anchor_age`、`anchor_year`、`anchor_year_group`、`dod` | 人口学 + 死亡 | **`anchor_age`；89 岁以上顶码为 91**。`dod` = 死亡日期（Task D）。 |
| **hosp/admissions** | `subject_id`、`hadm_id`、`admittime`、`dischtime`、`deathtime`、`race`、`insurance`、`hospital_expire_flag` | 住院层面 | `hospital_expire_flag` 为院内死亡；用于 index 就诊选择。 |
| **note/discharge** | `note_id`、`subject_id`、`hadm_id`、`charttime`、`text` | 自由文本出院小结 | Task-C 输入；中位数约 1 万字符；去标识占位符 `___`。 |

### 清洗规则 —— MIMIC-IV

1. **队列（锚点码集 —— 必须与 `vocab.py` 一致）：** 成人且带 **HTN 锚点 ICD** —— ICD-9 `4010`/`4011`/`4019`（+`402–404`，仅作锚点）或 ICD-10 `I10`、`I11–I13` —— **和/或**至少 1 条 `omr` 血压。**排除 ICD-9 `405` 与 ICD-10 `I15*`（继发性高血压，出范围）。** 已交付的代码本来就排除了它们（`vocab.HTN_SECONDARY_ICD10_PREFIXES`）；本行的早期版本错误地把 `I15*` 列为*纳入*。2026-07-18 更正。
2. **index 就诊规则（待决 —— 选一个并写进文档）：** 例如「首次带高血压诊断且同时有出院小结的住院」；每个 `subject_id` 保留 1 行。规则要落在代码里。
3. **OMR 血压解析：** 把 `result_value` 按 `/` 切分 → `sbp_omr`、`dbp_omr`（int）。只保留 `result_name` 以 "Blood Pressure" 开头的行；把体位保留为一列。范围核查同 NHANES。这是**慢性/门诊**血压的来源。
4. **Context 门（Task C）：** ICU/住院血压（chartevents/triage）→ `context="admission"` → **引擎对分期弃权**；只有 `omr` 门诊血压驱动慢性分期。每一行血压都要带上这个 flag。
5. **化验：** **加载前**先把 `labevents` 子集到 `itemid ∈ {50912, 50971}`；用 `valuenum`（忽略 `"___"`）；丢弃 `valuenum` 为空的行。**取严格早于 `admittime` 的最近一次值，且落在预注册的回溯窗内** —— 2026-07-18 更正。旧措辞（「离 index 就诊最近的值」）是双向的，会让在 index 住院**期间**抽的肌酐或血钾 —— 即决策之后、且很可能反映了正被评估的那次治疗 —— 去设定 `egfr` 与高钾 flag。那是 index 后泄漏，与计划自身「合并症须时间限定在 `admittime` 之前」的规则相抵触。由肌酐推导 eGFR（见 §6）。血钾已是 mmol/L（核对 `valueuom`）。**另需核实肌酐 itemid 的覆盖面** —— 除 `50912` 外还有 `52546`（"Creatinine, Blood"）与 `52024`（"Creatinine, Whole Blood"）。**缺失项：UACR** —— `itemid 51070`（"Albumin/Creatinine, Urine"）；没有它，MIMIC 的 `ckd` 就退化成只剩 eGFR 那一条腿，HC-35 会触发不足。
6. **诊断：** 用一份交叉映射把 ICD-9 与 ICD-10 归一到合并症 flag（糖尿病、CKD、血管神经性水肿史、妊娠）。血管神经性水肿史（ICD-10 `T78.3*`、`D84.1`）置「避免 ACEI」flag —— 这是本基准重点考察的关键禁忌。
7. **药物 → 家庭用药列表：** *家庭*用药优先取自 **ED `medrecon`**（见 §3）；`prescriptions` 是住院用药且噪声更大。把 `drug` 映射到引擎类别。
8. **银标准（Task C）：** 高血压状态与事实由 `diagnoses_icd` + `labevents` + `medrecon` 推导，**不**从病历文本推导。人工验证一个样本（计划风险 #3）。它测的是抽取保真度，不是一致性。
9. **病历文本：** 去标识的 `___` token 原样保留（绝不编造）。每个 index `hadm_id` 保留一份出院小结；按 `note_id` 去重。任何会改变临床含义的内容都不得删改。
10. **死亡/Task D：** 用 `patients.dod` 做出院后死亡；`hospital_expire_flag` 做院内死亡。**只谈合理性，绝不谈因果**（存在适应证混杂）。

---

## 3. MIMIC-IV-ED 2.2 —— 现用药重整 + 高血压急症

主键：`subject_id`、`stay_id`（急诊就诊）；通过 `edstays` 关联到 `hadm_id`。

| 表 | 变量 | 含义 | 清洗 |
|---|---|---|---|
| **ed/medrecon** | `name`、`etcdescription`、`etccode`、`gsn`、`ndc` | 已重整的**家庭**用药 | `etcdescription` = 治疗学分类（如 "…Beta 2-Adrenergic Agents…"）→ 映射到引擎类别。这是*现用降压药*的首要来源。 |
| **ed/triage** | `sbp`、`dbp`、`chiefcomplaint`、`acuity`、`pain` | 分诊生命体征 | 急诊血压 = **急性** → `context="admission"`，引擎对慢性分期弃权；仅用于高血压急症 flag。 |
| **ed/vitalsign** | `sbp`、`dbp`、`heartrate`、`charttime` | 急诊重复生命体征 | 同样按急性 context 处理 |
| **ed/edstays** | `subject_id`、`hadm_id`、`stay_id`、`intime`、`outtime`、`disposition` | 就诊主干 | 急诊↔住院的连接键 |

清洗：把生命体征列从补零的浮点字符串（如 `71.0000`）转为数值；做范围核查；把 `medrecon` 收敛为每个 `subject_id`/`stay_id` 的**类别集合**；按 `(subject_id, name, gsn)` 去重。所有急诊血压一律视为急性 context。

---

## 4. eICU-CRD 2.0 —— 已降级为弃权校准探针（HC-21）

主键：`patientunitstayid`（ICU 住院）；跨住院的病人为 `uniquepid`。**时间是相对入科的整数分钟偏移**（`*offset`）而非时间戳 —— 负值 = 入科之前。**这里所有血压都是 ICU/急性场景** → 只做结构化验证，引擎对慢性分期弃权。

| 表 | 用到的变量 | 含义 | 清洗 |
|---|---|---|---|
| **patient** | `gender`、`age`、`ethnicity`、`hospitaldischargestatus`、`unittype`、`patientunitstayid` | 人口学/结局 | **`age` 是字符串；">89" 顶码** → 映射为 90（数值）。`hospitaldischargestatus ∈ {Alive, Expired}`。 |
| **pastHistory** | `pasthistorypath`、`pasthistoryvalue` | 既往史（含高血压） | 路径字符串 → 合并症 flag |
| **diagnosis** | `diagnosisstring`、`icd9code`、`diagnosispriority` | 诊断 | `icd9code` 可能同时含 ICD-9 **与** ICD-10，以逗号连接；需切分再映射 |
| **admissionDrug** | `drugname`、`drugdosage`、`drughiclseqno` | 入院时家庭用药 | 药物→类别；自由文本，需要归一化 |
| **lab** | `labname`、`labresult`、`labmeasurenamesystem` | 化验（含肌酐、钾） | 过滤 `labname` 属于 {creatinine, potassium}；`labresult` 转数值；核对单位列 |
| **apachePatientResult** | `apachescore`、`predictedhospitalmortality`、`actualhospitalmortality` | 严重度/结局 | 仅作验证用协变量 |

清洗：仅在需要排序时（取离入科最近的化验）才换算偏移；处理 `>89`/`>300` 顶码；核对化验单位（eICU 混用惯用单位）；构造与 MIMIC 相同的类别集合式用药表示，使引擎只看到一种 schema。

---

## 6. 跨源派生变量（每个数据源都用完全相同的算法计算）

这些是引擎输入，在各源清洗**之后**计算，从而保证 `PatientProfile` schema 统一。

| 派生字段 | 定义 | 输入 |
|---|---|---|
| `sbp`、`dbp` | 有效读数的**均值**（NHANES）/ 指标前合格 OMR 读数的均值（MIMIC）/ —（eICU 急性） | 各源血压 |
| `bp_stage` | 按 2025 AHA/ACC 阈值分为 Elevated / Stage 1 / Stage 2 | `sbp`、`dbp` |
| `egfr` | **CKD-EPI 2021 无种族版**：142·min(Scr/κ,1)^α·max(Scr/κ,1)^-1.200·0.9938^age·(女性再乘 1.012)；κ=0.7♀/0.9♂，α=-0.241♀/-0.302♂ | `LBXSCR`/肌酐、年龄、性别 |
| `ckd_albuminuria` | eGFR<60 **或** UACR≥30 mg/g | egfr、UACR |
| `potassium` | 血清 K⁺（mmol/L）；`≥5.5` 置 flag | 化验 |
| `diabetes` | 诊断编码 / `DIQ010==1` | 诊断 / 问卷 |
| `prevent_10yr` | **PREVENT** base 模型的 10 年**总**-CVD 风险（ASCVD + 心衰；取代 Pooled Cohort Equations） | 年龄、性别、SBP、是否在治、总胆固醇、HDL、糖尿病、吸烟、eGFR、**他汀使用**。**不含 BMI、也不含 UACR** —— 2026-07-18 更正：BMI 属于*心衰*模型，UACR 属于*增强*模型，本项目两个都不用。**仅对 30–79 岁有效**；超出该范围或任一输入缺失 → `None` → 引擎弃权，**绝不**当作「低危」 |
| `on_bp_meds` | 目前是否在服降压药 | `BPQ050A` / medrecon / prescriptions |
| `med_classes` | 集合 ⊆ {噻嗪, ACEI, ARB, 二氢吡啶类 CCB, 其他} | 药物→类别映射 |
| `contraindications` | {妊娠, 血管神经性水肿史, 高钾(K≥5.5)} | 诊断 / 化验 |

**待决问题 —— 截至 2026-07-18 的状态：**

(a) **NHANES 只用 J vs 合并 `P_` → 建议用 J** 作为冻结的 Paper-1 基准，把 `P_` 作为预注册的稳健性附录。逐行标签从不使用调查权重，所以 `WTMEC2YR`→`WTMECPRP` 的切换只影响 Task-D/患病率估计。N 的增益也比此前声称的小：约 9,254 → 约 15,560 名受访者 ≈ **1.7 倍，而不是「大致翻倍」**。
(b) **MIMIC index 就诊规则 → 最早锚点 + 365 天/≥2 次 OMR，外加强制 ED 关联。** 见 §2。
(c) ~~PREVENT vs PCE~~ —— **已解决/锁定：PREVENT**，base 总-CVD 模型，≥7.5% 阈值。不得使用 PCE（它的阈值是针对 ASCVD 的 ≥10%，那是另一个终点）。
(d) **是否丢弃第 1 次血压读数 → 仍未决**；请在基准冻结前定下，并报告两种设定（见 §1）。
(e) ~~中位数血压统一（HC-23）~~ —— **已解决：用均值。** 对照指南原文裁定，代码本就正确，文档有误；属文档更正，不触发基准冻结级重新导出。见 §1 规则 3。

---

## 7. 全局清洗约定（处处适用）

1. **唯一规范 schema。** 每个数据源 → `schemas/patient_profile.schema.json`。数据源专有的列在清洗边界处终结；下游代码永不按数据源分支。
2. **缺失 ≠ 零。** 保留 `NA`；把所有「拒答/不知道/未知」哨兵值映射为 `NA`；必需字段缺失时引擎发出 `ABSTAIN`/`not_encoded`，而不是去猜。
3. **单位必须显式。** 让单位贯穿整个清洗过程；断言预期单位（K⁺ 用 mmol/L、肌酐用 mg/dL、UACR 用 mg/g、血压用 mmHg），不符即报错。eICU/MIMIC 的单位漂移是最主要的静默错误来源。
4. **范围/合理性门。** SBP 60–290、DBP 30–200、肌酐 0.1–20、K⁺ 1.5–9、年龄 18–120；越界 → `NA` 并记录原因，绝不静默截断。
5. **每条血压都带 context flag。** `chronic`（NHANES / MIMIC `omr`）对比 `admission`（急诊 / ICU / 分诊 / chartevents）。慢性分期只用慢性血压；急性血压 → 引擎弃权。
6. **去标识伪影。** MIMIC 的 `___` 与日期平移：绝不跨越它们做插补；用 `valuenum` 而非 `value`；89+/">89" 顶码按各源显式处理（MIMIC→91、eICU→90、NHANES→80）。
7. **可复现。** 确定性 pipeline、锁定版本、输入校验和（各数据集都自带 SHA256SUMS）、数据 manifest，以及每张表一份行数/QA 报告。绝不手工改数据。
8. **防泄漏纪律（对基准至关重要）。** 清洗后的**结构化行就是隐藏标签**；LLM 只会看到渲染出的病例或原始病历。标签列必须与任何送给模型的文本**物理隔离**。
9. **PHI/授权。** MIMIC 与 eICU 是需授权数据 —— 只能留在本地，不得把原始记录发送给外部服务；病例是派生/渲染出来的，不是原始行。

---

## 8. 建议执行顺序

1. ~~**打通 NHANES**~~ —— **已完成**；13 个 `.XPT` 文件在 `Data/NHANES/`。**剩余缺口：下载 `MCQ_J`**（`MCQ160B–F`：心衰、冠心病、心绞痛、心梗、卒中）→ `clinical_cvd`。没有它，那个 Stage-1 启动触发因子对每一行 NHANES 都是 null，会把标签偏向**治疗不足** —— 不安全的那个方向，同时也是目前成本最低的标签有效性提升。
2. ~~建 **NHANES → PatientProfile** pipeline~~ —— **已完成**；4,806 份档案。已于 2026-07-18 在 `bp_stage` / `ckd_albuminuria` 正确性修复后重新导出。
3. 建 **MIMIC-IV**（按 itemid 过滤加载 labevents、OMR 血压解析器、ICD-9/10 交叉映射、medrecon 连接、出院小结选择）→ Task B/C。
4. **eICU** 只作为约 500 例住院的弃权校准探针接入（HC-21，已降级），而不是第二个完整的结构化底料。
5. 在任何引擎/标签运行之前，先产出一份 **QA 报告**（行数、缺失率、越界日志、单位断言）。

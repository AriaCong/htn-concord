# HTN-Concord —— 数据选取、类型与处理全流程详解

> 🌐 **本文是 `HTN-Concord_DataProcessing_Walkthrough.md` 的中文对照版。两份文件必须同步修改。**
> 若两边冲突，以**英文版为准**，并立刻回来修正本文。

**目的。** 本文针对已经建成并跑通的 NHANES 底料，从头到尾回答六个问题：

1. 我们从哪个数据库、取哪些表和哪些列？
2. **为什么选这些列** —— 每一列服务于哪个指南决策？
3. 每一列在各个阶段分别是什么数据类型？
4. 清洗规则有哪些，按什么顺序执行？
5. 缺失数据怎么处理（以及为什么我们基本**不**填补）？
6. 整条处理流水线一步一步到底做了什么？

**与另一份数据文档的关系。** `HTN-Concord_DataDictionary_and_CleaningStrategy.md` 是**参考手册** ——
它列举五个数据集（含 MIMIC-IV、MIMIC-ED、eICU、Zigong HF）的每一张表，并保留更正历史。
**本文是**走查**（walkthrough）** —— 只跟随一条底料（NHANES cycle J），从原始 `.XPT` 一路走到通过校验的
`PatientProfile`，并且集中讲参考手册默认你已经懂的那部分推理。两边冲突时：关于**其他**数据集的事实以参考手册为准；
关于 NHANES 的执行顺序以本文为准，因为本文是直接读 `pipelines/nhanes/` 代码写出来的。

---

## 0. 一切规则的源头：唯一那个设计决策

HTN-Concord 清洗出来的结构化行不是一份*数据集*，而是一份**标准答案（answer key）**。引擎读入一行
`PatientProfile`，输出一个指南决策，我们随后把它当作评判 LLM 的 ground truth。

仅此一点就决定了下面所有规则，并且它**颠倒**了通常的数据科学直觉：

| 普通 ML 流水线 | HTN-Concord 流水线 |
|---|---|
| 填补缺失值，好让模型能训练 | **绝不填补任何临床事实。** 缺失 → 引擎 `ABSTAIN`（弃权） |
| 把离群值截断进范围，免得丢数据 | **越界一律置 `NA`。** 把 350 mmHg 截成 290 就是造了一个假读数 |
| 最大化样本量 N | 最大化**标签有效性**。一行我们无法正确打标的数据，比丢掉它更糟 |
| 假阴性与假阳性可以权衡 | **不对称。** 猜「没有危险因素」会导致**治疗不足** —— 那是不安全的方向 |

如果只记一句话：**未知必须以「未知」的形态活着穿过整条流水线**，因为「信息不足、无法决策」本身就是本基准要评判的答案之一。

---

## 1. 为什么主数据源是 NHANES

`Data/` 下有五个需授权/公开数据集。冻结版 Paper-1 基准的主底料是 NHANES，理由**不是**样本量：

| 做指南标准答案所需的条件 | NHANES | MIMIC-IV | eICU |
|---|---|---|---|
| 血压测于**慢性/门诊**场景（指南分期的前提） | ✅ 标准化 MEC 体检 | ⚠️ 仅 `hosp/omr` | ❌ 全是急性 ICU |
| **按方案重复测量**（分期需要稳定血压，而非单次读数） | ✅ 3 次示波法 | ❌ 次数不规则 | ❌ |
| PREVENT 全部输入落在同一行 | ✅ | ⚠️ 分散且须时间限定 | ❌ |
| 现用**家庭**降压药 | ✅ `RXQ_RX` | ⚠️ `medrecon`（仅限有急诊关联者） | ⚠️ 自由文本 |
| 公开、可再分发、审稿人可复现 | ✅ 免费下载 | ❌ 需授权 | ❌ 需授权 |
| Task C 所需的自由文本病历 | ❌ | ✅ | ❌ |

NHANES 赢在**决策语境**。一个 ICU 里 168/94 的血压**不是** 2 期高血压 —— 那是一个躺在 ICU 床上的重病人，
2025 AHA/ACC 的分期阈值根本不适用于它。这正是 `bp_context` 要作为一等 schema 字段存在的原因，
也是 eICU 被降级的原因：一条产出 20 万行、而引擎对每一行都必须弃权的流水线，等于没有产出任何基准条目。

保留 MIMIC-IV 做 Task B/C，恰恰因为它有 NHANES 没有的东西 —— 出院小结；而 `hosp/omr` 是 MIMIC 里
唯一具备门诊语境的血压来源。

---

## 2. 选了哪些列，以及**每一列为什么**被选中

选取准则是：**只有当一列发生变化会导致某个指南决策发生变化时，它才配进入这张表。** 没有任何一列是
「先收着也许有用」。下表每一行都写明它服务的决策。

### 2.1 决定**分期**的列（整部指南的分叉点）

| 文件 | 列 | 为什么需要它 |
|---|---|---|
| `BPXO_J` | `BPXOSY1–3`、`BPXODI1–3` | **分期的输入。** 取 3 次示波法读数而非 1 次，是因为单次读数对「平时血压」的估计不可靠，且第 1 次系统性偏高。下游的 normal / elevated / Stage 1 / Stage 2 全部是这 6 个数的函数 |
| `DEMO_J` | `RIDAGEYR` | 作为 **eGFR 输入与 PREVENT 输入**进入。注意：在 2025 指南下年龄**不是** Stage-1 启动的独立触发因子 —— 它只通过 PREVENT 起作用 |
| `DEMO_J` | `RIAGENDR` | CKD-EPI 2021（κ、α、女性 1.012 因子）**和** PREVENT（男女是两套完全独立的模型）都用到性别专属系数 |
| `DEMO_J` | `SEQN` | 所有文件的连接键。一名受访者 = 一行 = 一份档案 |

### 2.2 决定 Stage 1 **是否起始用药**的列

在 2025 AHA/ACC 指南下，Stage 1（130–139/80–89）是难点：低危仅生活方式干预，高危则用药。
高危 = 临床 CVD **或** 糖尿病 **或** CKD **或** PREVENT 10 年风险 ≥7.5%。下面每一列的存在，
都只为了解开这一个分叉。

| 文件 | 列 | 为什么需要它 |
|---|---|---|
| `DIQ_J` | `DIQ010` | 自报糖尿病 —— **Stage-1 的独立触发因子** |
| `GHB_J` | `LBXGH` | HbA1c ≥6.5% —— 糖尿病的**化验分支**。之所以必需：自报会漏掉未确诊的糖尿病，而一个未确诊糖尿病者被错标为低危，产出的是**治疗不足**标签，即不安全的那类错误 |
| `BIOPRO_J` | `LBXSCR` | 血清肌酐 → eGFR。eGFR <60 是 **CKD 触发因子**，同时 eGFR 又是 **PREVENT 输入** —— 这一列同时喂养两条独立路径 |
| `ALB_CR_J` | `URDACT` | UACR ≥30 mg/g —— **CKD 的另一条腿**。没有它，CKD 退化成只剩 eGFR 一条腿而触发不足；而「eGFR 尚可但有蛋白尿」的 CKD 很常见，恰恰是指南想要治疗的人群 |
| `TCHOL_J` | `LBXTC` | 总胆固醇 → PREVENT |
| `HDL_J` | `LBDHDD` | HDL → PREVENT（与总胆固醇一起给出 non-HDL 项） |
| `SMQ_J` | `SMQ020`、`SMQ040` | 当前吸烟 → PREVENT。取两列是因为 `SMQ040` 被 `SMQ020` 跳问门控（见 §5.2） |
| `RXQ_RX_J` + `RXQ_DRUG` | `RXDDRUG`、`RXDDRGID` | 他汀使用 → PREVENT（他汀在 base 模型里）。同时也是 `med_classes` 的来源 |
| `BPQ_J` | `BPQ050A` | 目前在服降压药 → PREVENT 的**在治血压（treated BP）**项 |
| `MCQ_J` ⚠️ | `MCQ160B–F` | 临床 CVD（心衰、冠心病、心绞痛、心梗、卒中）—— Stage-1 的独立触发因子。**该文件尚未下载**，因此 `clinical_cvd` 对每一行 NHANES 都是 null，QA 报告里它的缺失率是 100%。偏倚方向指向治疗不足；下载它是目前性价比最高的标签有效性提升 |

### 2.3 决定**用哪种药**、以及**要避开哪种药**的列

| 文件 | 列 | 为什么需要它 |
|---|---|---|
| `BIOPRO_J` | `LBXSKSI` | 血清钾。K⁺ ≥5.5 mmol/L 是 ACEI/ARB 的**禁忌** —— 本基准要考察的少数几条硬性「不得这样做」规则之一 |
| `BIOPRO_J`/`ALB_CR_J` | （经由 eGFR + UACR） | CKD **优选** ACEI/ARB。注意这与禁忌恰好相反：eGFR 降低是*选用*这类药的理由，外加一项监测要求 |
| `RXQ_RX_J` | `RXDDRUG` | 现用降压药**类别** —— 「启动」与「强化」的分界，也是判断下一种药是否与已在用药重复的输入 |
| `DEMO_J` | `RIDEXPRG` | 妊娠。ACEI/ARB 有致畸性。**目前只是在磁盘上，尚未接到 `pregnancy` flag** —— 孕期受访者当前带的是空禁忌列表。这是一个实打实的安全缺口，不是表面问题 |

### 2.4 出于其他理由保留的列

| 文件 | 列 | 理由 |
|---|---|---|
| `DEMO_J` | `RIDRETH3` | **仅用于亚组报告。** 引擎刻意保持种族中立 —— CKD-EPI 2021 是无种族版方程，PREVENT 也没有种族项。这一列的存在是为了让我们能**报告**分亚组的性能，绝不是为了让引擎依它分支 |
| `DEMO_J` | `WTMEC2YR`、`SDMVPSU`、`SDMVSTRA` | 抽样设计。**只**用于人群层面患病率与 Task-D 死亡率估计。**绝不**用于逐病例标签：一位患者该接受什么治疗，不取决于他代表多少美国人 |
| `BMX_J` | `BMXBMI` | 保留用于队列描述。**它不是 PREVENT base 模型的输入** —— BMI 属于心衰模型，本项目不用那个模型 |
| `BPQ_J` | `BPQ020`、`BPQ030`、`BPQ040A` | `BPQ020`/`BPQ040A` 用于解码 `BPQ050A` 的跳问门控（§5.2）；`told_hypertension` 与实测分期对照也有描述价值 |

### 2.5 我们刻意**不**取的东西

- **NHANES `P_` 疫情前合并池。** 建议冻结基准用 cycle J，把 `P_` 作为预注册的稳健性附录。
  N 的增益是约 9,254 → 约 15,560 名受访者（≈1.7 倍），而且 J 与 `P_` 绝不能混进同一个数据框 ——
  权重列不同（`WTMEC2YR` vs `WTMECPRP`）。
- **任何含种族项的 eGFR 方程。** 出于原则排除，而非因为拿不到。
- **Pooled Cohort Equations（PCE）。** 已被 PREVENT 取代。它的 ≥10% 阈值针对的是**另一个终点**
  （ASCVD 而非总 CVD），混用会悄悄改变「高危」的定义。

---

## 3. 数据类型 —— 三层契约

类型在三道边界上被检查。这一点很重要，因为 NHANES **把一切都发成浮点数**，包括语义上是分类或布尔的东西；
而一个悄无声息的浮点数，正是「拒答 = 7」变成一个看起来很合理的数据值的途径。

### 第 1 层 —— 原始 `.XPT`

SAS 传输格式。`pd.read_sas(path, format="xport")` 对**每个数值列都返回 `float64`**，
包括 `SEQN`、`RIAGENDR` 以及每一个 1/2/7/9 问卷编码。`io_xpt.read_component` 会立刻把 `SEQN`
转成可空的 `Int64`，使连接键不会在浮点运算中漂移。

### 第 2 层 —— 清洗后的 pandas

流水线使用 **pandas 可空 dtype**，而不是 numpy dtype。这不是风格问题 —— numpy 的 `bool` 没有 NA 态，
可空 `boolean` 是唯一能表达「我们不知道」而又不退回 `False` 的方式。

| 档案列 | pandas dtype | 说明 |
|---|---|---|
| `SEQN` | `Int64` | 可空整数键 |
| `source`、`bp_context` | `object`（str） | 每个源恒定：`"nhanes"`、`"chronic"` |
| `age`、`sbp`、`dbp`、`creatinine`、`egfr`、`potassium`、`uacr`、`hba1c`、`total_chol`、`hdl`、`bmi`、`prevent_10yr` | `float64` | NaN = 未知 |
| `sex` | `object`（str） | 清洗时即映射 `1→"male"`、`2→"female"`，绝不留作编码 |
| `race_eth` | `float64` | 原样保留编码；仅供报告 |
| `bp_stage` | `object` | `"normal"`/`"elevated"`/`"stage1"`/`"stage2"`/`NA` |
| `bp_n_readings` | `Int64` | 溯源信息：该汇总值由几次读数得出 |
| `diabetes`、`ckd_albuminuria`、`current_smoker`、`told_hypertension`、`on_bp_meds`、`statin_use`、`clinical_cvd` | **`boolean`**（可空） | 三值：`True` / `False` / `pd.NA` |
| `med_classes`、`contraindications` | `object`，内含 **`list[str]`** | 绝不是逗号分隔字符串 |

### 第 3 层 —— JSON Schema 契约

`schemas/patient_profile.schema.json` 是强制边界；`validate.validate_profiles` 在
`build_profiles.build()` 内部运行，所以非法行根本写不出去。schema 编码了两件 dtype 做不到的事：

- **可空性是显式且有意的。** 几乎每个字段都是 `["number", "null"]` 或 `["boolean", "null"]`。
  schema 的 description 直接写明规则：凡值真正未知处一律允许 null，以便引擎弃权，**且绝不得被强制为某个确定值**。
- **枚举封闭了词表。** `bp_stage`、`bp_context`、`sex`，以及 `med_classes` 与 `contraindications`
  的元素枚举都是封闭集合。像 `"stage_1"` 这样的拼写错误会在校验时失败，而不是在下游悄悄变成一个匹配不上的类别。

必需字段（缺了这些行就不能存在）：`source`、`age`、`sex`、`sbp`、`dbp`、`bp_stage`、`bp_context`、
`med_classes`、`contraindications`。注意那两个列表字段虽然必需，但**可以为空** —— 空列表是一个肯定性断言
（「未发现禁忌」），这与 null 含义不同。

### 序列化

`build_profiles.main()` 同时写 Parquet 与 CSV。Parquet 原生保留 list dtype；而 CSV 会把列表压成有损的
Python repr `"['thiazide']"`，因此列表列在写 CSV 前会被 **JSON 编码**，读回时用 `json.loads` 还原。
如果你读 CSV，请记得解析这两列。

---

## 4. 清洗规则（按执行顺序）

`build_profiles.build()` 里的顺序是承重的。其中有两处顺序是**正确性要求**，而非偏好。

### 第 1 步 —— 读取

逐组件调用 `io_xpt.try_read(component)`。`GHB` 是唯一的**可选**组件：缺失时流水线带警告继续跑，
糖尿病退化为仅用自报。其他任何文件缺失都是硬报错 —— 悄悄产出没有血钾的档案，就等于产出没有禁忌判定的档案。

### 第 2 步 —— 把每个组件清洗成每 `SEQN` 一行

每个 `clean_*` 函数返回一个以 `SEQN` 为键、使用**面向引擎的列名**的整洁数据框。源专有名称
（`LBXSCR`、`BPXOSY1`）到此为止，下游永不出现。这正是 MIMIC 流水线可以替换进来的原因：下游代码永不按源分支。

本步施加的规则：

- **哨兵值 → NA。** `_na_sentinels` 把问卷的 `7`（拒答）与 `9`（不知道）映射为 `pd.NA`。
  在任何比较之前先施加于每一个问卷列 —— 因为在未净化的数据上做 `DIQ010 == 1`，会悄悄把「拒答」当成「无糖尿病」。
- **编码 → 含义。** `RIAGENDR` 在清洗时就变成 `"male"`/`"female"`。下游比较的是词而不是数字，
  这样将来某个 cycle 若改了编码，会明确报错而不是悄悄反转。
- **血压汇总。** 取可用的第 1–3 次读数的均值，要求至少 1 组有效；`bp_n_readings` 记录由几次读数得出。
  > 🚨 **文档写的是中位数，代码实现的是均值（HC-23）。** 项目的每一份文档都声称中位数已于 2026-07-18
  > 跨源统一，但 `clean.py` 算的是 `df[sys_cols].mean(axis=1)`。**已交付的 `nhanes_profiles_J.csv`
  > 是一份基于均值的产物**，任何地方引用的分期/标签数字描述的都是均值管线。在 NHANES 里实际差异很小 ——
  > 4,783/4,806 行有全部三次读数 —— 但切换会重新导出基准底料并移动已发布的数字，所以这是一次
  > **基准冻结级决策，而不是清理**。在 HC-23 落地前，请把项目文档里的「中位数」读作*意图*而非已实现。
- **是否丢弃第 1 次读数的开关。** `clean_bp` 里 `discard_first = False`。仍是待决问题。
  示波法第 1 次读数系统性偏高，保留它会抬高 Stage 1/2、进而抬高启动用药标签；丢弃它几乎不损失样本
  （只有 10 行仅有单次读数）。请在基准冻结前定下，并报告两种设定下的敏感性表。
- **跳问门控重建**（`on_bp_meds` 与 `current_smoker`）—— 见 §5.2。

### 第 3 步 —— 合并

把每个清洗后的框按 `SEQN` 左连接到 `DEMO`。以 `DEMO` 为主干，因为它是唯一覆盖全部 9,254 名受访者的文件；
其余组件都是子样本（`BPXO` 7,132、`BIOPRO` 6,401、`BPQ` 6,161……）。**必须是左连接而非内连接** ——
内连接会悄悄施加一个未写进文档的队列过滤，把任何跳过某项化验的人剔除掉，并使队列成为连接顺序的副作用，
而不是一条明确规则。

### 第 4 步 —— 范围门要在派生**之前** ⚠️

`qa.apply_ranges` 把越界值置空并逐条记录违规。

| 列 | 接受范围 | 单位 |
|---|---|---|
| `sbp` | 60–290 | mmHg |
| `dbp` | 30–200 | mmHg |
| `creatinine` | 0.1–20 | mg/dL |
| `potassium` | 1.5–9 | mmol/L |
| `age` | 0–120 | 岁 |
| `bmi` | 10–90 | kg/m² |
| `total_chol` | 50–600 | mg/dL |
| `hdl` | 5–200 | mg/dL |
| `uacr` | 0–30000 | mg/g |

两个性质很关键：

- **拒绝，绝不截断。** 越界值变成 `NA`。把 350 mmHg 截成 290，是在用我们已知损坏的数据制造一个
  看起来合理的测量值，进而产出一个自信的 Stage 2 标签。
- **门在派生之前跑。** 若先派生，一个不合理的肌酐会先产出 eGFR、一个不合理的 SBP 会先产出分期，
  而它们所依据的值下一行就被删掉了 —— 留下一个没有存活输入的派生字段。在当前 cycle-J 运行中违规日志为空，
  但正是这个顺序让「为空」是可验证的，而不是运气好。

### 第 5 步 —— 派生引擎字段

在此处统一计算而非各源自算，从而保证 NHANES/MIMIC/eICU 的 schema 完全一致。

- **`egfr`** —— CKD-EPI 2021 无种族版：
  `142 · min(Scr/κ,1)^α · max(Scr/κ,1)^−1.200 · 0.9938^age ·（女性再乘 1.012）`，
  κ = 0.7 ♀ / 0.9 ♂，α = −0.241 ♀ / −0.302 ♂。
- **`bp_stage`** —— 阈值取自 `vocab.BP_THRESHOLDS`（elevated SBP ≥120；Stage 1 ≥130 或 ≥80；
  Stage 2 ≥140 或 ≥90），或逻辑，最严重的最后施加。比较用**半开区间（`>=`）**而不是 `between()`：
  早先的 `between(130, 139)` 会把 139.5/79 这类非整数均值血压置为 NA，并使档案列与引擎不一致
  （引擎经 `vocab.bp_stage_scalar` 独立分期）。`vocab` 是两者唯一的事实来源。
- **`diabetes`** —— `diabetes_self` **或** `hba1c ≥ 6.5`，按 Kleene 逻辑（§5.3）。
- **`ckd_albuminuria`** —— `egfr < 60` **或** `uacr ≥ 30`，Kleene 或。它是**「或」不是「且」**，
  与 KDIGO 及指南原文措辞一致。这个字段*名字*暗示了合取，应当读作朴素的 `ckd`。
- **`contraindications`** —— 目前只有 `hyperkalemia`（K⁺ ≥5.5）。`angioedema_hx` 在 NHANES 里
  确实无从查证，因此留空而不是猜。`pregnancy` **是**可查的（`RIDEXPRG`），但尚未接入 —— 见 §2.3。
- **`prevent_10yr`** —— 委托给纯函数模块 `prevent`（系数转录自 Khan 2024 表 S12A，并已用论文的
  worked example 验证）。任一输入缺失或年龄超出 30–79 时返回 NaN。

### 第 6 步 —— 队列过滤

`age >= 18` **且** `sbp` 非空。在范围门**之后**施加，这样「唯一那次血压不合理」的受访者会被正确排除，
而不是带着一个垃圾分期留下来。效果：**9,254 名受访者 → 4,806 份档案。**

### 第 7 步 —— Schema 校验

在 build 内部用 `patient_profile.schema.json` 跑 `validate.validate_profiles(df)`。
缺失的列先补为 `pd.NA`、并按 `PROFILE_COLUMNS` 重排，因此无论当次有哪些可选组件在场，导出的列集合都是固定的。

### 第 8 步 —— QA 报告

`qa.write_report` 产出 `data/nhanes/qa/nhanes_qa_J.json`：各源文件行数、越界违规日志、逐列缺失率、
分期分布。**在任何打标运行之前写出** —— 这就是你在信任任何下游数字之前该去查的那个产物。

### 第 9 步 —— 写出

Parquet + 经 JSON 编码的 CSV，写入 `data/nhanes/processed/`。

---

## 5. 缺失数据 —— 本流水线最与众不同的地方

**结论先行：我们不填补临床值。没有均值填充、没有中位数填充、没有 MICE、没有 LOCF、没有 k-NN。**
没测过的血压、肌酐、血钾或胆固醇，会一路以缺失状态进入引擎，引擎随即弃权。

理由是：引擎的输出就是 ground truth。一个填补出来的肌酐会产出一个填补出来的 eGFR，进而产出一个
**自信的** CKD 判定，进而把一个 Stage-1 患者从「生活方式干预」翻转为「开始用药」。我们随后就会拿
一个源自「没人测过的数字」的推荐去给 LLM 打分。填补是估计人群参数的合理工具；但它**不可用于**
构建逐病人的标准答案。

流水线实际做的事分为四条策略。其中只有第 2 条和第 4 条会在原本没有值的地方放上值，而两者都不是
对临床测量值的填补。

### 5.1 策略 1 —— 保留（默认，适用于每一个实测值）

哨兵 `7`/`9` → `pd.NA`。化验/血压空值保持 `NA`。越界 → `NA`。在下游，`NA` 会传播到派生字段，
引擎随即带理由发出 `ABSTAIN` 而不是猜。

已导出队列的当前缺失率（取自 QA 报告）：

| 字段 | 缺失 | 解读 |
|---|---|---|
| `age`、`sex`、`sbp`、`dbp`、`bp_stage` | 0% | 由队列过滤保证 |
| `bmi` | 0.7% | |
| `told_hypertension`、`on_bp_meds` | 0.2% / 0.3% | 之所以这么低，**正是因为**做了跳问门控重建（§5.2） |
| `uacr` | 1.5% | |
| `diabetes` | 3.4% | 低于单看 `DIQ010`，因为 HbA1c 分支救回了一部分 |
| `hba1c` | 3.8% | |
| `total_chol`、`hdl` | 5.2% | |
| `creatinine`、`egfr` | 5.6% | 两者相同，符合预期 —— eGFR 是肌酐的纯函数 |
| `potassium` | 5.6% | |
| `ckd_albuminuria` | 5.5% | 略低于肌酐：UACR 救回了一些没有肌酐的行 |
| **`prevent_10yr`** | **29.2%** | **预期之内且正确** —— 见下 |
| **`clinical_cvd`** | **100%** | **真实缺口** —— `MCQ_J` 未下载（§2.2） |

PREVENT 的 29.2% 缺失并不是数据质量问题。PREVENT 只对 30–79 岁有定义，所以 18–29 岁和 80 岁以上的人
本就无法计算，且任一输入（胆固醇、eGFR、吸烟）缺失都会剔除该行。另一条路 —— 把模型外推到其验证范围之外 ——
等于凭空捏造那个决定 Stage-1 是否起始用药的数字。

### 5.2 策略 2 —— 重建跳问门控的问卷逻辑（是**解码**，不是填补）

这是流水线唯一会填空的地方，而它是正当的，因为**那个空白不是缺失数据 —— 它是一个以「跳问」形式记录下来的回答。**

NHANES 问卷是分支式的。如果你说自己从不吸烟，就根本不会被问「你现在吸烟吗？」。把这个空白当成未知是错的：
受访者**确实**告诉了我们他不吸烟，只不过是通过门控而非通过后续问题。

**`current_smoker`**（`clean_smq`）：

| 条件 | 结果 | 依据 |
|---|---|---|
| `SMQ020 == 2`（一生吸烟未达 100 支） | `False` | 从不吸烟者不会被问 `SMQ040`；他们是真正的非吸烟者，不是未知 |
| `SMQ040 == 3`（完全不吸） | `False` | 既往吸烟者 |
| `SMQ040 ∈ {1, 2}`（每天/有些天） | `True` | 当前吸烟 |
| 其他 | `pd.NA` | 真正的拒答或缺失 |

**`on_bp_meds`**（`clean_bpq`）—— 三级门控 `BPQ020 → BPQ040A → BPQ050A`：

| 条件 | 结果 | 依据 |
|---|---|---|
| `BPQ020 == 2`（从未被告知高血压） | `False` | 不可能在服降压药 |
| `BPQ040A == 2`（被告知过，但从未被建议服药） | `False` | |
| `BPQ050A == 2`（被建议过，但目前未服） | `False` | |
| `BPQ050A == 1` | `True` | 在治 → PREVENT 的在治血压项，且属于「强化」而非「启动」 |
| 其他 | `pd.NA` | 仅限真正落在问答路径内的拒答/不知道 |

`clean_bpq` 里的注释记录了原因：一刀切地保留 NA 会导致对未治疗、未确诊者错误弃权 —— 也就是对人群中的大多数弃权。
重建把 `on_bp_meds` 的缺失率压到 0.25%，且每一个被填上的值**都能从受访者真实给出的回答推导出来**。

### 5.3 策略 3 —— 派生布尔量用 Kleene 三值逻辑

当一个派生 flag 由两条各自可能未知的分支做「或」时，流水线通过 pandas 可空 `boolean` 使用 **Kleene 或**：

```
True  | NA   = True     （一条分支成立即可，另一条改变不了结果）
False | NA   = NA       （未知 —— 绝不可读作 False）
NA    | NA   = NA
```

应用于 `diabetes`（自报 | HbA1c ≥6.5）与 `ckd_albuminuria`（eGFR <60 | UACR ≥30）。

这修正了一个真实缺陷。`ckd_albuminuria` 此前以 `.fillna(False)` 收尾，把「未知」洗成了「已知阴性」，
使引擎对那些肾功能从未被测过的患者走上 Stage-1 的**低危**分支 —— 把治疗不足当成了标准答案。
连同另外两处相关修复（PREVENT 为 NaN 时必须弃权而非读作低危；numpy-bool 加固），这总共改变了
4,806 个标签中的 109 个，全部朝着更高保真度的方向。

一般规则：**`False` 必须意味着「测过且为阴性」，绝不能意味着「没测」。**

### 5.4 策略 4 —— 结构性默认值（缺席本身即是证据的场合）

| 字段 | 默认值 | 依据 |
|---|---|---|
| `med_classes` | `[]` | `RXQ_RX` 是一份完整的处方清单。一名受访者若不在其中，或在其中但没有降压药，那他确实没有降压药类别 —— 在一份完整枚举中的缺席是阴性，不是空缺 |
| `contraindications` | `[]` | 结构相同 —— 但注意，这只在「已实际评估的那些 flag」范围内成立。由于 `pregnancy` 尚未接入，当前的空列表是一种过度断言 |
| `statin_use` | 经 `.fillna(False)` 置 `False` | **这里最弱的一个默认值。** 依据同样是「完整清单」论证，但与 `med_classes` 不同，它是在合并之后以一刀切的 `fillna` 施加的，所以任何因故未出现在 `RXQ_RX` 中的受访者都会变成确定的「未用他汀」。这会使 PREVENT 略微上移（未治疗者风险更高）。为与别处的 Kleene 策略保持一致，值得重新审视 |

---

## 6. 完整处理流水线一览

```
Data/NHANES/*.XPT                    13 个 SAS 传输文件，每 SEQN 一行
   │
   ├─ io_xpt.try_read                一切皆 float64；SEQN → Int64
   │                                 GHB 可选；其余缺失即硬报错
   ├─ clean.clean_*                  → 每组件一个整洁框，以 SEQN 为键
   │                                   • 7/9 → NA
   │                                   • 编码 → 词（性别）
   │                                   • 血压汇总 + bp_n_readings
   │                                   • 跳问门控重建
   ├─ drug_class                     RXQ_RX（长表 19,643 行）⋈ RXQ_DRUG 词典
   │                                   → med_classes：每 SEQN 一个排序列表
   │                                   → statin_use：每 SEQN 一个布尔
   ├─ _merge                         全部按 SEQN 左连接到 DEMO（9,254）
   ├─ qa.apply_ranges       ⚠️ 先跑   越界 → NA + 违规日志
   ├─ derive.*                       egfr、bp_stage、diabetes、ckd_albuminuria、
   │                                 contraindications、prevent_10yr
   ├─ 队列过滤                        age ≥ 18 且 sbp 非空   → 9,254 → 4,806
   ├─ validate.validate_profiles     JSON Schema；非法行写不出去
   ├─ qa.write_report                → data/nhanes/qa/nhanes_qa_J.json
   └─ 写出                            → nhanes_profiles_J.parquet + .csv
                                       （CSV 中列表列经 JSON 编码）
```

在 `htn-concord/` 下用 `python -m pipelines.nhanes.build_profiles` 运行。
用 `NHANES_CYCLE=J|P_pre_pandemic` 切换周期；用 `NHANES_RAW_DIR` 指向原始文件目录。

**当前产出：** 4,806 份 schema 合法的成人档案。分期分布：normal 2,073 / elevated 674 /
Stage 1 975 / Stage 2 1,084，即 Stage 1+2 ≈ 42.8%。*这些数字描述的是均值血压管线（§4 第 2 步）；
若 HC-23 落地，它们会变动。*

---

## 6b. MIMIC-IV —— 用到的表与未用的表

> ⚠️ **构建状态。** 目前只有 `pipelines/mimic/feasibility.py`（HC-13，仅计数）与
> `pipelines/mimic/omr_bp.py`（HC-14，血压解析器）。队列构建器、labevents 加载器、
> ICD 交叉映射、medrecon 连接与档案导出**（尚未构建）**。

### 用到的表

| 表 | 列 | 为什么需要 | 处理方式 |
|---|---|---|---|
| `hosp/omr` | `subject_id`、`chartdate`、`result_name`、`result_value` | **MIMIC 里唯一的门诊血压** —— 唯一能驱动慢性分期的 MIMIC 来源 | `result_value` 是 `"SYS/DIA"` **字符串** → 正则解析；体位取自 `result_name`；`bp_context="office"` |
| `hosp/labevents` | `itemid`、`charttime`、`valuenum`、`valueuom` | 肌酐（`50912`）→ eGFR；钾（`50971`）→ 高钾禁忌 | 2.4 GB —— 加载**前**先按 `itemid` 过滤；用 `valuenum`（`value` 可能是去标识的 `"___"`） |
| `hosp/d_labitems` | `itemid`、`label`、`fluid` | 核对 itemid 与单位 | 仅连接 |
| `hosp/diagnoses_icd` | `icd_code`、`icd_version` | 高血压锚点 + 合并症 flag | ICD-9 与 ICD-10 混用 → 两套都要映射 |
| `hosp/d_icd_diagnoses` | `icd_code`、`long_title` | 可读标签 | 仅连接 |
| `hosp/patients` | `gender`、`anchor_age`、`dod` | 人口学；`dod` 用于 Task D | 89 岁以上顶码为 91 |
| `hosp/admissions` | `admittime`、`dischtime`、`hospital_expire_flag`、`race` | index 就诊选择；院内死亡 | 按病人做日期平移；病人内部顺序有效，绝对日期无意义 |
| `note/discharge` | `note_id`、`hadm_id`、`text` | Task-C 输入 | 去标识 `___` 原样保留；每个 index `hadm_id` 一份；按 `note_id` 去重 |
| `ed/medrecon` | `name`、`etcdescription`、`etccode` | **家庭**用药 —— `on_bp_meds` 唯一不泄漏的来源 | `etcdescription` = 治疗学分类 → 引擎类别；收敛为类别集合 |
| `ed/edstays` | `subject_id`、`hadm_id`、`stay_id` | 急诊↔住院连接主干 | 仅连接 |
| `ed/triage`、`ed/vitalsign` | `sbp`、`dbp`、`chiefcomplaint`、`acuity` | **仅**用于高血压急症 flag | 急性 → `bp_context="admission"` → 引擎对慢性分期弃权 |

### 未使用的表及原因

| 表 | 为什么不用 |
|---|---|
| `hosp/prescriptions` | **住院**医嘱而非家庭用药。用它做 `on_bp_meds` 会泄漏正被评估的那个决策；`medrecon` 取代它 |
| `hosp/pharmacy`、`hosp/emar`、`hosp/emar_detail` | 给药/发药明细 —— 同样是住院数据、同样的泄漏问题 |
| `hosp/poe`、`hosp/poe_detail` | 医嘱录入：流程元数据，不是临床状态 |
| `hosp/procedures_icd`、`hosp/d_icd_procedures`、`hosp/hcpcsevents`、`hosp/d_hcpcs` | 操作/手术不在范围内 —— 这是一个「是否起始用药」的基准 |
| `hosp/microbiologyevents` | 感染数据；与慢性高血压无关 |
| `hosp/drgcodes` | 计费分组，不是临床状态 |
| `hosp/services`、`hosp/transfers`、`hosp/provider` | 行政流转/身份信息 |
| **整个 `icu/` 模块**（`chartevents`、`icustays`、`inputevents`、`outputevents`、`procedureevents`、`datetimeevents`、`ingredientevents`、`d_items`、`caregiver`） | **ICU 血压全部是急性的** → 引擎对慢性分期一律弃权。`chartevents` 是 MIMIC 最大的表，却会贡献**零**个决策标签 |
| `note/radiology`、`note/radiology_detail`、`note/discharge_detail` | 影像叙述不含降压决策内容；`discharge_detail` 是元数据 |
| `ed/diagnosis`、`ed/pyxis` | 急诊就诊编码与发药柜数据；家庭用药已由 `medrecon` 提供 |
| `hosp/omr` 的 `eGFR` 行 | 虽存在但只有约 279 行 —— 改为由肌酐推导 |

### 队列规则（设计不变量）

> **高血压 ICD 编码只用来选取*病人/就诊*（锚点），它绝不生成标签。**
> 慢性分期独立地由该次就诊*之前*的门诊 OMR 推导。

- **锚点码集：** ICD-9 `4010`/`4011`/`4019`（+`402–404`，仅作锚点）、ICD-10 `I10`、`I11–I13`。
  **排除** ICD-9 `405` 与 ICD-10 `I15*`（继发性高血压，出范围）。
- **index 就诊：** 最早一次具备合格既往 OMR 的锚点就诊。
- **PRIMARY 血压规则：** index 之前 365 天内、**≥2 个不同日期**的 OMR 读数，取中位数。
- **化验：** 严格早于 `admittime` 的最近一次值，且落在预注册的回溯窗内。
  「离 index 就诊最近」是双向的，会让住院**期间**抽的化验去设定 `egfr` 与高钾 flag —— index 后泄漏（HC-27）。
- **用药：** 取自 `medrecon` 的入院前家庭用药；**绝不**用出院带药，那就是答案本身。

### 可行性漏斗（HC-13，仅计数）

| 数量 | 步骤 |
|---:|---|
| 364,627 | 全部病人（hosp） |
| 364,627 | 成人 ≥18（MIMIC hosp 本就全是成人） |
| 110,932 | 带高血压锚点诊断 |
| 40,980 | ……且在最早锚点就诊前有任意 OMR 血压 |
| **28,530** | **PRIMARY：** 365 天内 ≥2 个不同日期的 OMR |
| 40,027 | FALLBACK：730 天内 ≥1 次 OMR |
| 138,038 | OMR-only 队列（≥2 个不同日期） |

> ⚠️ **真正可决策的 N 约为 8,921，而不是 28,530**（HC-26）。只有 31.3% 的 PRIMARY index 就诊带有
> 急诊用药重整，而 `medrecon` 是 `on_bp_meds` 唯一不泄漏的来源 —— 那正是区分*启动*与*强化*的变量。

### MIMIC 特有的缺失处理

- **去标识 `___`** —— 绝不跨它插补；用 `valuenum` 而非 `value`。
- **日期平移** —— 按病人平移年份、保留间隔；绝不跨边界插补。
- **`medrecon` 缺失** —— 那 68.7% 没有急诊用药重整的 PRIMARY 就诊必须**弃权**，
  而不是默认「未服药」。默认会系统性地把*强化*病例错标成*启动*。
- **UACR 缺失** —— `itemid 51070` 尚未纳入 itemid 集合；没有它，MIMIC 的 `ckd` 会退化成只剩 eGFR 一条腿而触发不足。
- **肌酐 itemid 覆盖面** —— 除 `50912` 外还需核实 `52546` 与 `52024`。

---

## 6c. 考虑过但被否决的其他处理方式

| 备选做法 | 否决理由 |
|---|---|
| 填补化验值（均值/中位数/MICE/k-NN/LOCF） | 产物是标准答案；填补出来的值会用「没人测过的数字」产出一个**自信的**标签 |
| 把越界值截断 | 制造出看起来合理的测量值；置 `NA` 才诚实 |
| 对未知 flag 用 `fillna(False)` | 把未知洗成已知阴性 —— 正是弃权原则明令禁止的猜测 |
| 各组件做内连接 | 会悄悄施加一个未写进文档的队列过滤，并使队列沦为连接顺序的副作用 |
| 先派生、后做范围门 | 会留下「输入在下一行被删掉」的派生字段 |
| 分期用 `between(130,139)` | 把非整数均值置为 `NA`，并使档案与引擎判断不一致 |
| 含种族项的 eGFR 方程 | 出于原则排除；CKD-EPI 2021 是无种族版 |
| Pooled Cohort Equations | 终点不同（ASCVD 对比总 CVD）—— 7.5% 的切点只对总 CVD 有效 |
| 把 PREVENT 外推到 30–79 岁之外 | 会捏造那个决定 Stage-1 是否起始用药的数字 |
| 用 ICD 编码生成高血压标签 | ICD 只选*就诊*；否则基准会退化成一次编码查表测试 |
| 用 `prescriptions` 作家庭用药 | 住院医嘱会泄漏正被评估的决策 |
| 用出院带药作 `on_bp_meds` | 那**就是**答案 —— 最严重的泄漏 |
| 建完整 eICU pipeline | 约 20 万行，且每一行在头条决策上都只能弃权 |
| 双向的「最近一次化验」 | 会向 `egfr` 与高钾 flag 造成 index 后泄漏（HC-27） |
| 对逐行标签使用调查权重 | 一位患者该接受什么治疗，不取决于他代表多少人 |
| 把 NHANES J 与 `P_` 合进同一个数据框 | 权重列不同；会产出静默失效的加权估计 |

---

## 7. 适用于所有数据源的全局约定

这些对 MIMIC-IV 与 eICU 同样成立，也正是它们让同一个引擎能读三个源。

1. **唯一规范 schema。** 每个源都产出 `patient_profile.schema.json`。源专有列在清洗边界终结；
   下游代码永不按源分支。
2. **缺失 ≠ 零。** 保留 `NA`；把每一个拒答/不知道/未知哨兵映射为 `NA`；引擎弃权而不是猜。
3. **单位必须显式。** 断言预期单位（血压 mmHg、肌酐 mg/dL、K⁺ mmol/L、UACR mg/g），不符即报错。
   单位漂移是 MIMIC 与 eICU 最主要的静默错误来源；NHANES 相对安全，因为 `LBXSKSI` 本身就是 SI。
4. **范围门只拒绝、不截断** —— 且必须在派生之前跑。
5. **每条血压都带 context flag。** `chronic`（NHANES 体检、MIMIC `omr`）对比 `admission`
   （急诊/ICU/分诊）。慢性分期只用慢性血压。
6. **绝不跨去标识伪影做插补。** MIMIC 的 `___` 与日期平移；用 `valuenum` 而非 `value`。
   年龄顶码按源显式处理：NHANES 80、MIMIC 91、eICU 90。
7. **可复现。** 确定性流水线、锁定版本、输入校验和、每次运行一份 QA 报告。绝不手工改数据文件。
8. **防泄漏纪律。** 清洗后的结构化行**就是隐藏标签**。LLM 只看到渲染出的病例或原始病历。
   标签列必须与任何送给模型的文本物理隔离。
9. **PHI/授权。** MIMIC 与 eICU 需授权 —— 只能留在本地，绝不把原始记录发给外部服务。
   NHANES 公开可再分发，这也是它成为主底料的原因之一。

---

## 8. 本流水线的已知缺口（引用任何数字之前请先读）

| # | 缺口 | 影响 | 方向 |
|---|---|---|---|
| 1 | `MCQ_J` 未下载 → `clinical_cvd` 100% 为 null | 一个 Stage-1 高危触发因子从不触发 | **治疗不足**（不安全） |
| 2 | `RIDEXPRG` 未接到 `pregnancy` flag | 孕期受访者带空禁忌列表；引擎可能把「启动 ACEI/ARB」当作标准答案输出 | **不安全推荐** |
| 3 | HC-23：文档写中位数，代码算均值 | 已交付底料与所有引用的分期数字都是均值口径 | 基准冻结级决策 |
| 4 | 是否丢弃第 1 次读数仍未决（`discard_first=False`） | 第 1 次读数偏高 → 抬高 Stage 1/2 → 抬高启动用药标签 | **过度治疗** |
| 5 | `statin_use` 一刀切 `fillna(False)` | 与别处的 Kleene 策略不一致 | PREVENT 轻微上移 |

缺口 1 与 2 涉及安全，应在基准冻结前关闭。缺口 3 与 4 都会移动已发布的数字，应当一次性决策并执行，
并在同一轮里把所有下游数字重新引用一遍。

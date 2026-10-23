# 方向 ② 新颖性检索（2026-09-23）

**问题：** 「让 LLM 从真实病历中算 PREVENT 风险，把错误拆成抽取、计算、缺失处理三类；并在数据缺失时，检验它能否判断结论已经确定」还有没有空位？

**做法：** 17 轮网络检索，其中 6 篇核对到摘要或正文。另外查了本地 MIMIC 档案里 PREVENT 输入变量的完整度（§4）。

---

## 1. 结论

**「抽取与计算分开看，错误主要出在计算」这个结论在心血管领域已经被占了，而且是两次。**

- **EHJ-DH 2026 SCORE2 vignette 研究**（ztag073）：11 个模型、30 个葡萄牙语和英语 vignette。风险因素抽取的 F1 为 0.97–0.99；模型自己算出的风险分类 κw 最高 0.69；用模型抽出的变量**事后按确定性公式重算**，κw 升到 0.85–0.90。原文结论就是「计算执行是主要失败环节」。
- **EHJ-DH 2026 心血管风险管线**（ztag124，HTN-Concord 文献地图里已有）：分成三段的管线 α 为 0.78，单独用 LLM 只有 0.32。

所以「LLM 会抽不会算，交给代码算就好」**不能再当发现写**。

**仍然空着的，是下面三件事的组合：**

1. **真实病历 + 结构化表格当抽取真值，并且上规模。** SCORE2 那篇自陈局限是「模拟 vignette、只有 30 例、没有真实 EHR」。CHA₂DS₂-VASc 的 RAG 研究（Yale，1,000 份病历）用的是两名医生人工标注的 200 份。**没有检索到以 MIMIC labevents / OMR 为抽取真值、在出院小结上算连续风险方程的工作。**
2. **连续方程上的可判定性。** ClinDet-Bench 是这个思路唯一的前作，但它用的是 16 个**计点式**评分（CHADS2、HAS-BLED 等）、94 个合成病例，由医生编写。**连续方程（PREVENT）+ 对缺失变量做区间运算 + 真实数据里自然出现的缺失**，这个组合没有检索到。
3. **PREVENT 本身**。检索到的 LLM 风险计算研究测的都是旧量表：PCE（ChatGPT-3.5，2023）、Framingham、SCORE2、EuroSCORE II、CHA₂DS₂-VASc。**没有一篇测 PREVENT。** PREVENT 在 2023 年底发表，比很多模型的训练数据都新，天然可以用来讨论训练数据污染。不过这一点单独撑不起论文。

**判断：** ② 的空位比 ① 窄，但**真值最硬**：抽取对错、计算对错、能否判定都是机器可算的，完全不需要医生。「计算是瓶颈」这个前提已被别人证明，这反而可以当作已知条件，把重心放到 2 和 3 上。

---

## 2. 已被占的：直接竞争者

| 工作 | 做了什么 | 数据 | 与我们的差别 | 核验 |
|---|---|---|---|---|
| **LLMs approach clinician performance in ESC CV risk stratification** EHJ-DH 2026;7(5):ztag073（PMC13215473） | 11 个 LLM 抽取 SCORE2 输入 → 计算 → 分类；事后用确定性公式重算；与 8 名医生对照 | **30 个模拟 vignette**，葡英双语；三名心内科医生定参考标准 | **最强竞争者，已经占了「抽取 vs 计算」这个结论。**我们的增量：真实病历、结构化表格作真值、规模大两个数量级、连续方程上的可判定性 | 正文 |
| **LLM pipeline exceeding physician-documented CV risk scores** EHJ-DH 2026;7(7):ztag124 | 知识注入 → LLM 抽取 → 确定性计算；α 0.78 对单独 LLM 的 0.32 | 真实临床文本；CHA₂DS₂-VASc、HAS-BLED、EuroSCORE II | 真值由专家裁定；都是计点式或离散量表；没有可判定性 | 摘要（文献地图已收录） |
| **ClinDet-Bench** arXiv 2602.22771 | 信息不完整时，分可判定 / 不可判定两类；模型「既过早下结论又过度弃权」 | **94 个合成病例，16 个计点式评分**，由一名医生编写；8 个模型 | 可判定性的**唯一前作**。我们的增量：连续方程、区间运算、真实缺失 | 正文 |
| **Clinical Risk Computation by LLMs Using Validated Risk Scores** J Med Syst 2025（PMID 41023468） | 3 个 LLM 算 5 个量表；**都在 Framingham 上失败** | 未核实 | 说明「连续方程难算」已有人观察到 | 检索 |
| **LLM chatbots cannot reliably calculate clinical risk scores** MDPI 2026 | EuroSCORE II：直接算和给出公式两个条件；MAE 3.3–6.4%，一致率最高约 51% | 未核实 | 同上，单一量表 | 检索 |
| **ChatGPT-3.5 for PCE ASCVD risk** medRxiv 2023 | 重复查询差异大，经常跨阈值重新分类 | 合成输入 | 早期工作；PCE 是 PREVENT 的前身 | 检索 |
| **LLM agents can use tools for clinical calculations** npj DM 2025;8:163 | 48 个计算任务；RAG / 代码解释器 / OpenMedCalc 三种工具；任务专用工具让错误减少 5.5–13 倍 | 合成题 | 「给工具就好」已被证明，不能当贡献 | 检索（Nature 重定向，未读正文） |
| **MedCalc-Bench**（NeurIPS 2024）、**From Scores to Steps**（EMNLP 2025）、**MedCalc-Pro**（arXiv 2607.02879） | 计算器基准；分步评分；多计算器 / 嵌套计算 agent | 病例报告摘录（PubMed） | 通用计算器；病例文本来自文献，不是 EHR；真值由医生写的解释给出 | 检索 / 地图 |
| **RAG extracting CHA₂DS₂-VASc factors** medRxiv 2024（Yale） | Llama3.1 + RAG 从真实病历抽风险因素 | 1,000 份病历，**医生人工标注 200 份** | 真实病历有了，但真值要人工标注，只到抽取、没做计算 | 检索 |
| **Measuring sensitivity of LLM structured extraction** arXiv 2606.05970 | 在 MIMIC-IV 出院小结上一次只变一个选择（提示 / 模型 / schema），**不用人工真值** | MIMIC-IV | 同样在 MIMIC 上做不依赖人工的评估，但它测的是一致性，**不以结构化表为真值** | 摘要 |

---

## 3. 仍空的，以及每一项有多站得住

| 空位 | 站得住的程度 | 理由 |
|---|---|---|
| **A. 连续风险方程的区间可判定性**（对缺失变量取合理范围 → 风险区间 → 是否跨过阈值 τ） | **强** | ClinDet-Bench 只做了计点式评分、合成病例、医生编写。连续方程 + 区间运算在检索中没有出现。这也是纯计算机科学的问题：区间传播、单调性、何时可以安全弃权。 |
| **B. 结构化表格当抽取真值，在真实出院小结上上规模** | **中强** | 没有找到以 labevents / OMR 为真值的 LLM 风险计算工作。**风险：**出院小结里写的数值和表格里的数值可能本来就不一致（时间点不同、同一项测了多次），「真值」本身需要定义规则。这是数据工程问题，不需要临床判断，但必须事先写清楚。 |
| **C. PREVENT** | **弱到中** | 属于领域空白，可以借机谈训练数据污染。单独不够。 |
| **D. 错误归因在真实数据上的分布** | **中** | SCORE2 那篇已证明「计算是瓶颈」，但它是 vignette。**真实病历里抽取错误可能重新变成主要错误**，比如单位、时间点、否定句。如果结果真是这样，就能和 SCORE2 那篇形成对照。 |

**不能主张的：** 「首次分离抽取与计算」「首次证明 LLM 算不好风险分数」「首次证明工具 / 代码能修复」「首次研究弃权 / 可判定性」。

---

## 4. MIMIC 可行性（本地数据核查）

数据：`htn-concord-main/htn-concord/data/mimic/processed/mimic_profiles_primary_prior_plus_index.csv`

| | 数量 |
|---|---|
| 档案总数 | 8,919 |
| 年龄 30–79（PREVENT 的适用范围） | 6,689 |
| 其中能完整算出 PREVENT | **2,376（35.5%）** |
| 算不出的：缺总胆固醇 / 缺 HDL / 糖尿病状态未知 / 缺 eGFR | 74.1% / 75.5% / 70.2% / 2.3% |
| 能算出的人群中 PREVENT ≥ 7.5% | 79% |

**怎么读：**

- 约 4,300 人**自然缺少**一到三个 PREVENT 输入。对 HTN-Concord 来说这是缺陷；对方向 ② 来说这正是**可判定性实验的现成样本**：缺了 HDL，风险区间是否仍然整体落在 7.5% 以上？
- 可算人群中 79% 超过 7.5%，说明住院人群风险普遍偏高，很多缺失病例可能「缺了也能判定」。这会影响可判定 / 不可判定两类的比例，要事先估计。
- 糖尿病「未知」比例高，需要先确认是管线只记录阳性，还是确实没有记录。这是数据问题，不是临床问题。

---

## 5. 建议的收窄方式

1. **主张：**「在真实 EHR 上，以结构化表格为抽取真值、以区间运算为可判定性真值，评估 LLM 的 PREVENT 风险计算与弃权」。「抽取与计算分离」作为已知条件，引用 SCORE2 和 EHJ-DH 两篇。
2. **四个条件：** 直接算 / 给出公式 / 给工具（代码执行）/ 只让 LLM 抽取、由我们来算。第四个条件就是 SCORE2 那篇的「事后重算」，把它作为基线。
3. **可判定性真值：** 每个缺失变量取人群合理范围，如 NHANES 的 1–99 分位；算出 PREVENT 区间，看是否整体在 τ 的同一侧。τ 在 5–20% 之间扫描，不需要论证哪个阈值在临床上正确。**注意 §5（方向 ①）已查明 PREVENT 在 SBP < 110 时不单调，区间要用数值优化求，不能只取端点。**
4. **最小先导：** 200 份出院小结，分可算 / 缺一项 / 缺两项三层；一个前沿模型加一个开源模型；看抽取与表格的一致率，以及可判定性判断的两类错误率。

---

## 6. 核验标注

- **正文：** ESC SCORE2 研究（PMC13215473）、ClinDet-Bench（arXiv HTML）
- **摘要：** 2606.05970、2605.05715（方向 ③ 用）、EHJ-DH ztag124（文献地图）
- **只到检索摘要：** J Med Syst 2025 风险计算、MDPI EuroSCORE II、ChatGPT PCE 2023、npj DM 工具 2025、MedCalc-Pro、Yale CHA₂DS₂-VASc RAG、Regression vs Medical LLMs for CVD（medRxiv 2026.03）

**盲区：** 没有查 EHJ-DH 两篇的被引列表；没有查中文数据库。**最该补查：** SCORE2 那篇（ztag073）的被引列表，看有没有人已经把它搬到真实 EHR 上。

---

## 来源

- [LLMs approach clinician performance in ESC CV risk stratification (EHJ-DH 2026, PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC13215473/)
- [LLM pipeline exceeding physician-documented CV risk scores (EHJ-DH 2026)](https://academic.oup.com/ehjdh/article/7/7/ztag124/8746371)
- [ClinDet-Bench (arXiv 2602.22771)](https://arxiv.org/abs/2602.22771)
- [Clinical Risk Computation by LLMs Using Validated Risk Scores (J Med Syst)](https://link.springer.com/article/10.1007/s10916-025-02261-5)
- [LLM Chatbots Cannot Reliably Calculate Clinical Risk Scores (MDPI)](https://www.mdpi.com/1664-204X/29/3/31)
- [ChatGPT-3.5 for PCE ASCVD risk (medRxiv 2023)](https://www.medrxiv.org/content/10.1101/2023.08.11.23293957.full.pdf)
- [LLM agents can use tools to perform clinical calculations (npj DM 2025)](https://www.nature.com/articles/s41746-025-01475-8)
- [MedCalc-Bench (arXiv 2406.12036)](https://arxiv.org/pdf/2406.12036)
- [From Scores to Steps (arXiv 2509.16584)](https://arxiv.org/html/2509.16584)
- [MedCalc-Pro (arXiv 2607.02879)](https://arxiv.org/abs/2607.02879)
- [RAG for CHA₂DS₂-VASc factors (medRxiv 2024)](https://www.medrxiv.org/content/10.1101/2024.09.19.24313992v1)
- [Sensitivity of LLM structured extraction in discharge summaries (arXiv 2606.05970)](https://arxiv.org/abs/2606.05970)
- [When Confidence Fails (arXiv 2608.09080)](https://arxiv.org/abs/2608.09080)
- [Regression vs. Medical LLMs for CVD (medRxiv 2026)](https://www.medrxiv.org/content/10.64898/2026.03.11.26347789v1.full.pdf)

# 方向 ① 新颖性检索（2026-09-23）

**问题：** 「在心血管场景下，用信息不变的改写来检验 LLM 治疗决策的一致性」还有没有空位？

**做法：** 24 轮网络检索，12 篇核对到摘要或正文，其余只到检索摘要这一级（见 §6 核验标注）。另外用 HTN-Concord 已有的先导调用数据算了一次翻转率（§4），并对 PREVENT 方程做了一次单调性数值检查（§5）。

---

## 1. 结论

**宽泛的说法已经被占了。**「LLM 的临床决策对不改变意思的输入变化很敏感」至少有 8 篇工作做过，时间集中在 2025–2026 年。这一点不能再当贡献写。

**窄的组合仍然空着。** 没有检索到任何一篇同时满足下面四条：

1. **等价由构造保证**：变体由确定性渲染器从同一份结构化档案生成，信息不变由测试强制。现有工作都是先用 LLM 改写，再事后用 NLI、LLM 评委或医生抽查来验证等价。
2. **任务是治疗决策**，不是诊断或选择题；
3. **心血管 / 高血压领域**。检索到的心血管 LLM 研究只测了重复调用的一致性和提示策略，没有测信息不变改写；
4. **方向性关系取自已发表方程**（PREVENT），而不是由医生预先规定该往哪个方向变。

**但先导数据给出了一个必须正视的风险信号（§4）：** 在已有的 120 次调用里，前沿模型跨呈现档的**决策**翻转率是 2/120，和它自身的重复噪声 1/60 一样。如果主要实验对象是前沿模型，并且只用呈现层面的改写，最可能得到的结果是「没有效应」。

---

## 2. 已被占的：直接竞争者

| 工作 | 做了什么 | 等价怎么保证 | 任务 / 领域 | 与我们的差别 | 核验 |
|---|---|---|---|---|---|
| **Same Patient, Different Words, Different Diagnosis?** arXiv 2605.30646（2026-05） | 16 个开源模型在不改意思的改写下的稳定性；提出 MVS、ΔC、WCI 三个指标 | **NLI 过滤 → LLM 评委 → 医生审核** | **诊断**；DiagnosisQA、MedQA | 最直接的竞争者。等价靠事后验证，任务是诊断选择题，不涉及心血管 | 摘要 |
| **MedPerturb** arXiv 2506.17163（2025-06） | 800 个情境，扰动性别、文风、格式（多轮对话、摘要），并与人类标注对照 | 格式变体**由 LLM 生成**；摘要未说明如何验证信息不变 | **治疗规划**（MANAGE / VISIT / RESOURCE），多科 | 任务与我们最接近，但等价没有保证，也没有领域真值 | 摘要 |
| **The Medium is the Message** FAccT 2025（Gourabathina…Ghassemi） | 非临床信息（不确定语气、夸张语气、性别）改变治疗建议 | LLM 改写 | 治疗建议，病人留言 | 同上；偏公平性视角 | 检索（ACM 页 403） |
| **Baseline-aware counterfactual audits** BioNLP 2026 | 人口学扰动的效应要和改写噪声基线对比；Jaccard 噪声底 0.46–0.71 | 改写作为对照扰动 | EHR 分诊 / 预测 | **方法必须借用**：没有噪声基线的翻转率无法解读 | 摘要 |
| **Metamorphic Testing for Clinical ML Models** arXiv 2607.22984（2026-07） | 基于 MIMIC-III/IV 为 3 个 ICU 任务设计 12 条蜕变关系；5 条先导关系的违反率在 27–87% 之间 | 蜕变关系以指南为依据 | **经典 ML，不是 LLM**；结构化数据 | 「蜕变测试 + 临床」这个提法已被用过。我们的增量在于测的是 LLM、输入是文本、蜕变关系取自方程 | 摘要 |
| **Counterfactual Evaluation / CSS** arXiv 2605.30590（2026-05） | 224 个肿瘤病例 × 5 类**应当改变**的干预，给「是否往预设正确方向更新」打分 | 正确方向预先注册，并经三名医学人员验证 | 肿瘤 MTB | 只做**方向性**关系，**没有做不变性**；方向由人预先规定 | 摘要 |
| **ClinicNumRobBench** arXiv 2604.11133 / Findings ACL 2026 | 用 MIMIC-IV 生命体征的 3 种语义等价表示测数值推理；换成病历文风后性能下降 | 模板化表示 | 数值检索 / 比较 / 聚合，**不是决策** | 「等价表示 + MIMIC」已有人做，但停在数值问答层面 | 摘要 |
| **Robustness is important**（PNAS Nexus 2026） | 变量名、变量顺序、小数位、NL→JSON 这些与任务无关的变化，使预测变化 0.45–17.34% | 构造保证 | **合成**表格回归 / 分类，非临床 | 构造保证等价这个思路已有，但不在临床领域 | 正文（PMC） |
| LLM Sensitivity Evaluation Framework, COLING 2025（2504.13475） | 区分「应敏感」与「不应敏感」两类扰动 | — | 诊断 | 早期同类工作 | 摘要 |
| Artificial Intolerance, arXiv 2605.17228 | 一句污名化语言就能改变决策，且有剂量–反应关系 | LLM / 人工插入 | 治疗（疼痛、影像） | 属于「无关信息」类扰动 | 检索 |
| BiasMedQA（npj DM 2024；medRxiv 2025） | 7 种认知偏差，含近因、框架效应 | 人工改写 USMLE 题 | 选择题 | 顺序效应已有人研究 | 检索 |
| 跨语言一致性：XLingEval（WWW 2024）、arXiv 2609.07687（2026-09） | 同一医学问题换语言后答案不一致，中文差距最大之一 | 翻译 | 健康问答 | 跨语言不变性已有人做，但限于问答，而且等价要依赖翻译质量 | 检索 |

**心血管领域的情况：** 房颤抗凝（Sci Rep 2025、PubMed 41704798）和 PCI 决策（Front CV Med 2026）只测了重复调用一致性和提示策略。高血压方面，AHA 2026 那篇和 npj 提示工程那篇都已在 HTN-Concord 文献地图里。**没有检索到任何心血管 LLM 研究做信息不变改写。**

**综述佐证：** J Med Syst 2026 的范围综述（PMC13161009）纳入 33 篇医学 LLM 鲁棒性研究：73% 是「混合医学」领域；只有 12% 做情境变化测试；只有 33% 的测试贴近真实临床场景。综述没有提到任何形式的等价验证方法。专科化、贴近临床这两项被列为明确的缺口。

---

## 3. 仍空的，以及每一项有多站得住

| 空位 | 站得住的程度 | 理由 |
|---|---|---|
| **A. 构造保证等价的改写族**（确定性渲染器 + 测试强制） | **强** | 2605.30646 用 NLI、LLM 评委、医生三层做事后验证，本身就说明他们没法事前保证等价。PNAS Nexus 那篇做到了构造保证，但不在临床领域。空缺 02 的判断经这次检索仍然成立。 |
| **B. 心血管 / 高血压治疗决策** | **中** | 属于领域空白，这种新颖性审稿人一般会打折扣。单独撑不起一篇论文，要和 A 绑在一起。 |
| **C. 方程派生的方向性关系**（PREVENT） | **中强** | CSS 的正确方向由人预先规定；2607.22984 的蜕变关系以指南为依据，而且测的是经典 ML。**以已发表方程为规格、不需要医生就能定方向的 LLM 蜕变测试没有检索到。**但见 §5：方程本身不是处处单调的。 |
| **D. 人群代表性样本**（NHANES 4,806 份，带权重） | **中** | 竞争者用的都是 vignette 或考试题库。能报「按美国成人人群加权的翻转率」是独有的，但属于增量。 |
| **E. 不变性 + 方向性放在同一框架、共用噪声基线** | **中** | 两者各自都有人做过；放在同一套病例上、用同一个噪声底，还没见到。 |

**不能主张的：** 「首次发现 LLM 对改写敏感」「首次把蜕变测试用于临床」「首次研究顺序效应或跨语言一致性」。

---

## 4. 先导数据的风险信号（用现有数据算出，未发起新调用）

数据来源：`htn-concord-pilot-gate/htn-concord/data/pilot/pilot_calls.jsonl`（HC-101，前沿模型 `gpt-6-astra`，20 名病人 × 3 个呈现档 × 2 次重复，共 120 次调用）。三个呈现档在构造上信息不变，所以它们本身就是一组现成的不变性变体。

| 比较对象 | 重复噪声（同档不同次） | 跨档（同次不同档） |
|---|---|---|
| `decision` | 1/60（1.7%） | **2/120（1.7%）** |
| `decision` + `drug_classes` | 5/60（8.3%） | **14/120（11.7%）** |

**怎么读：**

- **决策层面，前沿模型对呈现改写基本不变**：跨档翻转率等于噪声。这与 HC-101 的结论一致，即提取 F1 在三档之间完全相同。
- **药物类别层面，跨档翻转略高于噪声**（11.7% 对 8.3%），但 n=20，不能据此下任何结论。
- HC-80 先导里，开源模型的提取 F1 从 0.923 降到 0.888，说明**较弱的模型不是不变的**。
- **含义：** 如果方向 ① 只拿前沿模型测呈现层面的改写，大概率得到零结果。要么把重点放在开源 / 小模型，以及模型规模与不变性的关系上；要么换用更强的改写族，见 §7。

---

## 5. PREVENT 方程不是处处单调的（数值检查结果）

`pipelines/common/prevent.py` 按原文对 SBP 做了分段：`(min(SBP,110)−110)/20` 与 `(max(SBP,110)−130)/20`。**低于 110 那一段的系数为负**（女性 −0.239，男性 −0.435）。

数值检查设置：年龄 30–79（步长 7）× 性别 × 是否服降压药 × 是否糖尿病，SBP 从 90 到 200（步长 2），共 3,520 个相邻步。

- **640 步风险下降，且全部出现在 SBP ≤ 110。**
- 110 以上，在这个网格内风险单调上升。

**含义：** 「SBP 升高 → 风险不降」这条蜕变关系**只在 SBP ≥ 110 时成立**。蜕变关系必须从方程**算出来**，不能凭常识假设。这正好是方向 C 相对 CSS 的方法学优势：规格是方程，不是人的直觉。还要注意，这里说的是 PREVENT 方程的形状，**不涉及对临床因果的任何判断**。

---

## 6. 核验标注

- **正文：** PNAS Nexus 2026（PMC13253566）、J Med Syst 2026 综述（PMC13161009）
- **摘要：** 2605.30646、2506.17163、2607.22984、2605.30590、BioNLP 2026.14、2604.11133、2504.13475、2606.00031、2605.17436、2404.03664
- **只到检索摘要这一级（引用前必须读原文）：** FAccT 2025 Medium is the Message、2605.17228、BiasMedQA、MamaBench 2607.14385、MedEqualQA 2510.12818、MedFuzz 2406.06573、ICD 编码蜕变测试（ScienceDirect 2025）、XLingEval、2609.07687、房颤 / PCI 研究、JGIM 2025 推荐差异

**这次检索的盲区：** 没有查 Google Scholar 或 Semantic Scholar 的引用链；没有查中文数据库（CNKI）；2026-09 之后的预印本可能还没被收录。**最该做的补查**是 2605.30646 和 2506.17163 的被引列表，看有没有人已经在做「构造保证等价」。

---

## 7. 如果走这个方向，建议的收窄方式

1. **主张收窄为：**「以确定性渲染保证信息等价、以已发表风险方程为规格的 LLM 心血管治疗决策蜕变测试」。宽泛的「LLM 对改写敏感」只放在 related work。
2. **噪声基线是必做项**（借 BioNLP 2026）：每条蜕变关系都报「翻转率减去同条件重复噪声」。
3. **改写族要比 HC-101 更强**，而且每一族都能构造保证等价：
   - 表示形式：结构化 JSON、表格、叙述三者互换
   - 单位：mmHg/kPa、mg/dL/mmol/L，换算由代码完成
   - 语言：中英两套**确定性模板**，而不是翻译，这样跨语言等价也由构造保证
   - 无关信息：加入 PREVENT 不使用的变量，如姓名、职业、种族（PREVENT 已去掉种族）
   - 事实顺序
4. **方向性关系只取方程能直接给出的**：SBP ≥ 110 时的单调性、eGFR、糖尿病、吸烟，每一条都先像 §5 那样做数值检查；另外可以加上跨过 7.5% 阈值的边界病例。
5. **模型谱系要宽**：开源 4B–70B 加前沿模型。把「不变性随规模怎么变」作为一个研究问题，这样前沿模型的零结果也有信息量。
6. **一周内能完成的零成本下一步：** 用现成的 renderer 和 runner，拿 20 名病人 × 2–3 族新改写 × 一个开源小模型跑一轮先导，只看翻转率是否明显高于噪声。高于噪声就值得继续做；不高于就及时止损，转向方向 ②。

---

## 来源

- [Same Patient, Different Words, Different Diagnosis? (arXiv 2605.30646)](https://arxiv.org/abs/2605.30646)
- [MedPerturb (arXiv 2506.17163)](https://arxiv.org/abs/2506.17163)
- [The Medium is the Message (FAccT 2025)](https://dl.acm.org/doi/10.1145/3715275.3732121)
- [Baseline-Aware Counterfactual Audits for Clinical NLP (BioNLP 2026)](https://aclanthology.org/2026.bionlp-1.14/)
- [Metamorphic Testing for Clinical ML Models (arXiv 2607.22984)](https://arxiv.org/abs/2607.22984)
- [Counterfactual Evaluation Reveals Hidden Capability Profiles (arXiv 2605.30590)](https://arxiv.org/abs/2605.30590)
- [ClinicNumRobBench (arXiv 2604.11133)](https://arxiv.org/abs/2604.11133)
- [Robustness is important: Limitations of LLMs for predictions on tabular data (PNAS Nexus 2026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC13253566/)
- [LLM Sensitivity Evaluation Framework for Clinical Diagnosis (COLING 2025)](https://arxiv.org/abs/2504.13475)
- [Artificial Intolerance (arXiv 2605.17228)](https://arxiv.org/abs/2605.17228)
- [Medical Context Distorts Decisions in Clinical VLMs (arXiv 2605.17436)](https://arxiv.org/abs/2605.17436)
- [Clinical Plausibility in LLM Robustness Testing: Scoping Review (J Med Syst 2026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC13161009/)
- [LLMs for Cardiovascular Risk Prediction from Structured Clinical Data (arXiv 2606.00031)](https://arxiv.org/abs/2606.00031)
- [Cognitive bias in clinical LLMs / BiasMedQA (npj DM)](https://www.nature.com/articles/s41746-024-01283-6)
- [MamaBench (arXiv 2607.14385)](https://arxiv.org/abs/2607.14385)
- [MedEqualQA (arXiv 2510.12818)](https://arxiv.org/abs/2510.12818)
- [MedFuzz (arXiv 2406.06573)](https://arxiv.org/abs/2406.06573)
- [Metamorphic Testing of LLM-based ICD Coding (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S235264832500025X)
- [Perspectives on Cross-Lingual Consistency in LLMs for Medical Questions (arXiv 2609.07687)](https://arxiv.org/html/2609.07687)
- [AF management prompting & languages (Sci Rep 2025)](https://www.nature.com/articles/s41598-025-04309-5)
- [9 LLMs in NVAF anticoagulation (PubMed 41704798)](https://pubmed.ncbi.nlm.nih.gov/41704798/)
- [Variation in LLM Recommendations in Inpatient Scenarios (JGIM 2025)](https://link.springer.com/article/10.1007/s11606-025-09888-7)
- [LLMs in the Heart of Differential Testing: Medical Rule Engine (arXiv 2404.03664)](https://arxiv.org/abs/2404.03664)

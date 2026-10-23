# 方向 ③ 新颖性检索（2026-09-23）

**问题：** 「在开源 LLM 的隐藏状态里，能不能读出 SBP、eGFR、PREVENT 风险这些心血管中间量；如果内部算对了，是在哪一步丢掉的」还有没有空位？

**做法：** 7 轮网络检索，其中 6 篇核对到摘要或正文。

---

## 1. 结论

**「模型内部知道，但说不出来」这个现象已经被反复证明，在医学领域也有。** 能不能用这个方法，不是问题；关键在于**用它解释什么**。

**仍然空着的：** 检索到的医学探针工作，探测的都是**离散标签**：答案对错、证据等级、ICD 类别、药物不良反应。**没有一篇探测连续临床中间量**（生命体征、化验值、方程风险值），也**没有一篇研究多步计算在模型内部的哪一层断掉**。心血管领域完全是空白。一篇 JMIR AI 2026 的综述直接写明：医学 SAE 研究几乎没有实证工作，专科方面（包括心血管）一篇都没有。

**判断：** ③ 的新颖空间最大，但风险也最大：
- 需要 GPU 和可解释性方面的工程能力；
- 在医学领域，这类论文的审稿人最少；
- 结果可能是「能读出来，但解释不了为什么」。2605.05715 就遇到了这种情况：信号可以线性解码，但沿这个方向做干预修正不了任何错误。

最合适的定位是**给 ① 或 ② 补一层机制解释**，不宜单独作为博士主线。

---

## 2. 已被占的：方法前作

| 工作 | 做了什么 | 与我们的差别 | 核验 |
|---|---|---|---|
| **Internal Representation, Not Clinical Knowledge** arXiv 2605.29889（文献地图已收录） | 用 Gemma 3 4B/12B 和 Qwen3-8B 做分诊；医学特征在叙述部分激活，**到选择题决策 token 处全部失活**；用 SAE 和 logit 归因 | 最近的医学机制研究，但任务是分诊（离散），变量是输出格式；没有连续量 | 摘要 |
| **LLMs Know More About Numbers than They Can Say** arXiv 2602.07812 | 隐藏状态能读出数字的对数量级（相对误差约 2.3%），数对大小比较 >90%；**让模型直接说出来只有 50–70%** | 「数值能读出来但说不出来」已有人证明，但**非医学、只涉及单个数字，不涉及计算** | 摘要 |
| **Probing for Arithmetic Errors** arXiv 2507.12379 | 从隐藏状态同时解码模型答案和正确答案；判断对错准确率 >90%；可推广到 GSM8K | 「探测多步计算中的错误」有前作，但是纯数学，不是临床方程 | 摘要 |
| **Strength of clinical evidence is recoverable from representations** arXiv 2606.29034 | 22 个开源模型（0.6–70B），45,134 条论断；线性探针 AUROC 中位数 71.8，**模型自己报出的等级接近随机** | 医学领域「内部知道、说不出来」的最新证据；但信号**主要来自词汇特征，跨主题不迁移** | 摘要 |
| **Decodable but Not Corrected** arXiv 2605.05715 | Qwen2.5-7B 的医学 QA 失败模式可线性解码（平衡准确率 71.6%），但 29 种干预配置**全部无效** | **重要的负面结果**：能读出来不等于能修好。我们的研究问题要定成「在哪里断掉」，不要定成「能否修复」 | 摘要 |
| **PING**（medRxiv 2025.09.17） | 在冻结模型上训练探针，MedMCQA 上校准误差降低多达 96%；安全微调后拒答的模型仍能恢复 87% 性能 | 医学探针工具包（`pingkit`），可以直接拿来用 | 检索（medRxiv 403） |
| **Primary ICD Category Prediction using LLM-based Probing** arXiv 2606.28798 | 多层隐藏状态 + 线性探针做 ICD 类别预测，结构化与非结构化输入 | 探测的是诊断类别，不是连续量 | 检索 |
| **Linear Probe Robustness in Medical QA** arXiv 2609.01361 | 探针在语体、专科、语料变化下的稳健性 | 方法学注意事项，可以借用 | 检索 |
| **SAE in medicine**（JMIR AI 2026，PMC13215048） | **综述**；明确写出几乎没有医学 SAE 实证，心血管等专科零篇；训练一个 SAE 约 1,000–4,000 美元 | 可以直接引用来说明空白 | 正文 |

---

## 3. 仍空的

| 空位 | 站得住的程度 | 理由 |
|---|---|---|
| **A. 连续临床中间量的线性可读性**（SBP、eGFR、PREVENT 风险） | **强** | 医学探针工作全部探测离散标签；数值探针工作全部不在医学领域。 |
| **B. 多步方程计算的逐层定位**（输入变量 → 分段项 → 线性预测值 → 风险 → 阈值决策，每一步在哪一层可读、在哪一层丢失） | **强** | PREVENT 是一条完全透明的计算链，每个中间量都可以用方程算出来当探针标签。检索中没有在任何临床方程上做过这件事。 |
| **C. 与行为错误对齐**：内部读得出正确风险、嘴上却答错的病例占多少 | **中** | ODBB（文献地图）观察到 3–9% 的题在推理里说对了、最终答案却没给出；2606.29034 在证据等级上观察到类似现象。放到连续风险上还没人做。 |
| **D. 干预修复** | **弱，不建议作为主张** | 2605.05715 已给出强负面结果。 |

---

## 4. 如果走这个方向

- **模型：** Qwen3-8B、Gemma 3 12B、Llama 3.x 8B（显存 24–48 GB 就够）。不必训练 SAE，**线性探针加激活修补**就能回答 A–C，也绕开了训练 SAE 的成本。
- **输入：** 直接用方向 ① 的确定性渲染器生成的 NHANES vignette，标签由 `prevent.py` 算出。**这样 ③ 就是 ① 的机制层**，两篇论文共用同一套数据。
- **最小先导：** 1,000 个 vignette 输入 Qwen3-8B，逐层提取最后一个 token 和数值 token 位置的隐藏状态，用岭回归读出 SBP 和 PREVENT 的 logit。只看一件事：风险值在哪一层能被读出、R² 有多高。一张 GPU 大约一天可以完成。
- **控制实验必须做：** 对打乱标签、随机初始化的模型各跑一次基线。2606.29034 的教训是信号可能只是词汇特征，比如 SBP 可以直接从 vignette 里那串数字的 token 读出来。所以 SBP 这类输入量可读并不说明问题，**真正有信息量的是只存在于计算之后的量（风险值）是否可读**。

---

## 5. 核验标注

- **正文：** PMC13215048（SAE 综述）
- **摘要：** 2605.05715、2602.07812、2507.12379、2606.29034、2605.29889（地图）
- **只到检索摘要：** PING（medRxiv 403）、2606.28798、2609.01361、Hidden Error Awareness 2605.09502、Causal Tongue-Tie 2605.25891

**盲区：** 可解释性论文大多发在 ICLR、NeurIPS、ICML 和 workshop 上，arXiv 之外的收录不全；没有查 OpenReview。**最该补查：** 「numerical probing」和「arithmetic circuits」近一年的 OpenReview 投稿，看有没有人在任何领域做过「方程中间量逐层定位」。如果非医学领域已经有人做过，B 的新颖性就只剩「首次用于临床方程」。

---

## 来源

- [Internal Representation, Not Clinical Knowledge (arXiv 2605.29889)](https://arxiv.org/abs/2605.29889)
- [LLMs Know More About Numbers than They Can Say (arXiv 2602.07812)](https://arxiv.org/abs/2602.07812)
- [Probing for Arithmetic Errors in Language Models (arXiv 2507.12379)](https://arxiv.org/abs/2507.12379)
- [Strength of clinical evidence is recoverable from representations (arXiv 2606.29034)](https://arxiv.org/abs/2606.29034)
- [Decodable but Not Corrected (arXiv 2605.05715)](https://arxiv.org/abs/2605.05715)
- [PING: Probing Hidden States for Calibrated Predictions (medRxiv)](https://www.medrxiv.org/content/10.1101/2025.09.17.25336018v3)
- [Primary ICD Category Prediction using LLM-based Probing (arXiv 2606.28798)](https://arxiv.org/html/2606.28798v1)
- [Linear Probe Robustness in Medical QA (arXiv 2609.01361)](https://arxiv.org/abs/2609.01361)
- [Application of SAEs to Medical LLMs (JMIR AI 2026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC13215048/)
- [Hidden Error Awareness in CoT (arXiv 2605.09502)](https://arxiv.org/pdf/2605.09502)
- [Causal Tongue-Tie (arXiv 2605.25891)](https://arxiv.org/pdf/2605.25891)

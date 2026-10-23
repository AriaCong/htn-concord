# 成本估算：OpenAI API 与 Colab（2026-09-23）

**价格来源：** OpenAI 官方定价页（2026-09 读取）；Colab 定价取自第三方整理，官方未公开各 GPU 的每小时计算单元消耗，下文按区间估算。
**所有数字都是数量级估计，**先导实验后需要按实际 token 数重算。

## 1. 单价

### OpenAI（每 100 万 token，美元）

| 模型 | 标准：输入 / 输出 | Batch（五折）：输入 / 输出 | 用途 |
|---|---|---|---|
| gpt-6-luna | 0.10 / 0.50 | 0.05 / 0.25 | 便宜的大规模主力 |
| gpt-5.4-mini | 0.75 / 4.50 | ≈0.375 / 2.25 | 较早一代的对照 |
| gpt-6-sol | 2.00 / 10.00 | 1.00 / 5.00 | 中档主力 |
| gpt-6-astra | 10.00 / 50.00 | 5.00 / 25.00 | 旗舰，只跑子集 |

- 重复输入（系统提示、指南片段）可以按缓存价计费，约为输入价的 10%。
- **推理模型的「思考」token 一般按输出计费**（本文按此假设估算，以官方文档为准）。
- 实验不要求实时返回，**一律用 Batch API**。

### Colab

| 方案 | 价格 | 计算单元 |
|---|---|---|
| Pro | $9.99 / 月 | 100 |
| Pro+ | $49.99 / 月 | 500 |
| 按量购买 | $9.99 / 100 单元 | — |

| GPU | 计算单元 / 小时（不同来源） | 约合美元 / 小时 |
|---|---|---|
| T4（15 GB） | 1.2–2.0 | $0.12–0.20 |
| L4（22.5 GB） | ≈1.7–5 | $0.17–0.50 |
| A100 40 GB | 5.4–15 | $0.54–1.50 |
| A100 80 GB | ≈7.5 | ≈$0.75 |

下文**一律按 A100 每小时 15 单元（$1.50）这个上限估算**，偏保守。

## 2. 用量假设

**每次调用：**
- 输入约 1,500 token：题面加输出格式约 800；RAG 或贴原文的条件会更长，这里取平均；
- 输出约 300 token（JSON 加简短理由）；
- 推理模式再加约 2,000 个「思考」token。

**各研究的调用次数：**
- **A：** 1,000 例 × 6 个条件 × 3 次重复 = **每个模型 18,000 次**；
- **B：** 1,500 例 × 5 个条件 × 5 次重复（算一致性要多采样）= **每个模型 37,500 次**；
- **C：** API 只用来跑对照基线，约 5,000 次。

## 3. API 费用（Batch 价）

| 研究 | 模型 | 非推理 | 推理模式 |
|---|---|---|---|
| A | luna | ≈ $3 | ≈ $12 |
| A | sol | ≈ $54 | ≈ $230 |
| A | astra（**子集**：300 例 × 主要条件 × k = 1，约为全量的 1/10） | ≈ $30 | ≈ $120 |
| B | luna | ≈ $6 | ≈ $24 |
| B | sol | ≈ $110 | ≈ $490 |
| B | astra（子集） | ≈ $55 | ≈ $240 |
| C | 基线评测 | ≈ $20 | ≈ $80 |
| 先导实验与返工 | 全部 | ≈ $50 | ≈ $150 |

**合计：**
- 以非推理为主：**约 $300**
- 推理 / 非推理各半：**约 $900**
- 全部跑推理、多轮返工：**约 $2,000**

**建议预算：$1,000，其中 20% 作为缓冲。** 最大的开销是「sol 加推理模式」，如果预算紧，可以只在子集上跑推理模式。

## 4. Colab 费用（按 A100 每小时 $1.50 的上限估算）

| 任务 | A100 小时 | 计算单元 | 美元 |
|---|---|---|---|
| A：Qwen3 0.6B–14B 推理（vLLM），非推理加 thinking 模式 | 30–40 | 450–600 | $45–60 |
| A：LoRA 知识更新（4B / 8B，约 2,000 条样本，多次试跑） | 5–10 | 75–150 | $8–15 |
| A / B：探针（抽取隐藏状态 + 训练线性探针） | 5–10 | 75–150 | $8–15 |
| B：Qwen 推理（NHANES 部分） | 30–50 | 450–750 | $45–75 |
| C：GRPO 先导（1.5B，300 步） | 3–6 | 45–90 | $5–9 |
| C：正式训练（2 个规模 × 3–4 种配置 × 2 个种子，约 12–16 次） | 150–300 | 2,250–4,500 | $225–450 |
| 调试与中断重跑（×1.5） | — | — | 另加 50% |

**合计：约 $500–1,000，分摊在大约 11 个月里。**

**建议的订阅方式：**
- A、B 阶段订 **Pro**（$9.99 / 月），不够时按量补买；
- C 的训练月份订 **Pro+**（$49.99 / 月），并补买计算单元。

## 5. 总计（约 11 个月）

> 2026-09-23 修订：A、B 的 Qwen 推理、探针和 LoRA 改在本机（M4 Max，36 GB）上跑，Colab 基本只用于 C 的 GRPO 训练，所以 Colab 一行下调。

| 项目 | 低 | 中 | 高 |
|---|---|---|---|
| OpenAI API | $300 | $900 | $2,000 |
| Colab | $250 | $450 | $700 |
| **合计** | **≈ $550** | **≈ $1,350** | **≈ $2,700** |

## 6. 需要注意

1. **Colab 不保证分到 A100。** 即使是 Pro+ 也可能只拿到 T4，而 T4 跑不了 GRPO。C 的训练阶段如果频繁拿不到 A100，可以考虑按小时租云 GPU（常见 A100 报价约 $1–2 / 小时，需要另查）。
2. **会话会中断，训练必须能从检查点续跑。**
3. **MIMIC 不上 API，也不上 Colab。** 2026-09-23 查过 PhysioNet 指引：它强烈建议使用本地模型，MIMIC 相关推理放在本机（M4 Max，36 GB）。C 的训练数据来自 NHANES，可以在 Colab 上训练。
4. 本文用的价格是 2026-09 读取的，gpt-5.6-sol 的促销价只维持到 2026-11-21。


## 7. 省钱版（2026-09-23 新增，推荐采用）

**Claude Pro 订阅不能抵扣 API 费用。** Pro 覆盖的是 claude.ai 和 Claude Code，API 要在 Console 另外按 token 付费。能真正省钱的是下面三件事。

### 7.1 申请研究额度（效果最大）

| 项目 | 额度 | 审核节奏 | 申请入口 |
|---|---|---|---|
| Anthropic AI for Science | 最多 $20,000 API 额度，有效期 6 个月 | 每月第一个周一审核 | [申请表（Google Form）](https://docs.google.com/forms/d/e/1FAIpQLSfwDGfVg2lHJ0cc0oF_ilEnjvr_r4_paYi7VLlr5cLNXASdvA/viewform?usp=header) · [说明页](https://support.claude.com/en/articles/11199177-anthropic-s-ai-for-science-program) |
| OpenAI Researcher Access Program | 最多 $1,000，有效期 12 个月，不能续期 | 每季度审一次（3 / 6 / 9 / 12 月），批准后约 4 周到账 | [申请入口（SurveyMonkey Apply）](https://openai.smapply.org/prog/openai_researcher_access_program/) · [FAQ](https://help.openai.com/en/articles/10139500-researcher-access-program-faq) |
| 学校 GPU 集群 | 通常免费 | — | 问导师或学校 IT |

- Anthropic 的说明页仍写着偏重生命科学；据报道，2026-08-27 起已扩展到其他学科。本项目属于医学，申请时强调「心血管临床决策的可靠性」。
- OpenAI 优先资助 7 个方向，本项目可以对应其中的 **Robustness**（稳健性）、**Interpretability**（可解释性）、**Societal impact**（社会影响）。
- 拿到 Anthropic 额度后，可以把 Claude 作为第三个模型家族加进实验，结论就不只适用于一家厂商。

### 7.2 改实验设计（省 60–80% 的 API 费用）

| 做法 | 节省 |
|---|---|
| 温度固定，每个病例只跑 1 次；只在 10% 的子集上重复 3 次，用来估计噪声 | A 约省 60% |
| B 的多次采样（每题 5 次）只在 300 例子集上做 | B 约省 70% |
| 推理模式只在子集上开 | 去掉最大的开销 |
| 先导实验后做功效分析，确定需要多少病例 | 可能再省 30–50% |
| 提示缓存：固定的说明和指南原文放在开头 | 这部分输入降到原价的 10% |
| 只输出 JSON，理由写短，并限制最大输出长度 | 输出约减半 |
| 全部走 Batch / Flex（半价）；每次调用都缓存，不重复跑；正式跑之前先用 20 例试一遍 | 半价，外加不返工 |

### 7.3 算力

- M4 Max：所有推理、探针、LoRA（零成本）。
- Kaggle 每周约 30 小时免费 GPU（T4 / P100）：小规模 SFT 和调试。
- C 的 GRPO：先用 1.5B 模型、少跑几个种子，Colab 按量付费，不按月订阅。

### 7.4 三种情形下的预算

| | 原估计（中） | 省钱版（没拿到额度） | 拿到研究额度后 |
|---|---|---|---|
| API | $900 | 约 $100–250 | 约 $0 |
| Colab / GPU | $450 | 约 $100–200 | 如果学校有集群，约 $0 |
| **合计** | **约 $1,350** | **约 $200–450** | **约 $0–100** |

省钱版的数字是按 7.2 和 7.3 的做法折算的粗估，要等先导实验跑出实际 token 用量后再核对。

**执行顺序：**
1. 现在申请 Anthropic 额度（每月审）和 OpenAI 额度（下一轮 12 月）。
2. 问导师学校有没有 GPU 集群。
3. 先导实验只用本机和 gpt-6-luna。

**来源：**
- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)
- [Colab pricing summary (aicoolies, 2026-09)](https://aicoolies.com/pricing/google-colab)
- [Colab GPUs features & pricing (McCormick)](http://mccormickml.com/2024/04/23/colab-gpus-features-and-pricing/)
- [Colab alternatives (Thunder Compute, 2026-09)](https://www.thundercompute.com/blog/colab-alternatives-for-cheap-deep-learning-in-2025)
- [Claude subscription vs API billing](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console)
- [Kaggle Efficient GPU Usage](https://www.kaggle.com/docs/efficient-gpu-usage)

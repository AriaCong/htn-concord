# cv-llm-invariance

候选方向 ①：**心血管场景下，LLM 治疗决策在信息不变改写下的一致性**（metamorphic / invariance testing）。

这个方向是从 HTN-Concord 分出来的。起因是 HTN-Concord 的真值是临床判断，要靠医生裁定（HC-49）才能验证；本方向的真值是「同一信息 → 同一输出」这类不需要医生的关系。

**状态：** 探索期，尚未决定是否转向。与 `htn-concord-main/` 平行，不改动其中任何文件。

## 目录

| 文件 | 内容 |
|---|---|
| `docs/novelty_search_2026-09-23.md` | 新颖性检索：什么已被占、什么仍空、先导数据给出的风险信号 |

## 复用自 HTN-Concord 的资产（只读引用，不复制）

- `htn-concord/renderer/` — 确定性渲染器 + 信息不变性测试
- `htn-concord/runner/` — 唯一调用 LLM 的阶段
- `htn-concord/pipelines/common/prevent.py` — PREVENT 方程（已对原文算例验证）
- NHANES 2017–2018 档案 4,806 份；MIMIC 管线

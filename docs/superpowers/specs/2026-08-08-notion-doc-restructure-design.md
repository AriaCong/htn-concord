# Design spec — HTN-Concord documentation restructure (Notion + `docs/`)

**Date:** 2026-08-08
**Status:** approved design, not yet implemented
**Scope:** the two Notion trees under *PhD Source Note*, and the bilingual `docs/*.md` pairs in the repo.

---

## 1. Problem

The documentation has three legs — the English Notion tree, the Chinese Notion tree, and `docs/*.md` — and all three have drifted. The drift is not incidental; it is the direct cause of every finding in the 2026-07-18 audits, and it keeps recurring because of two structural faults.

**Fault 1 — figures are restated instead of referenced.** `4,806`, `42.8%`, `40.7%`, `8,921`, `28,530`, `144 abstain` each appear in three to five places across the hubs, the audit log, and the walkthrough pages. Each copy is an independent opportunity to drift, and several already have:

- `pipelines/nhanes/clean.py` computes BP with `mean`, while the data dictionary, the Master Plan, the MIMIC cohort algorithm and both Notion trees all state `median` was adopted on 2026-07-18. No code implements that decision (HC-23 / GAI-62). Every published NHANES figure therefore describes a pipeline that the documentation does not describe.
- The PREVENT high-risk share was published as `38.4%` (denominator 3,606 age-eligible) when the correct value is `40.7%` (denominator 3,404 actually scored). The wrong denominator silently treated 202 unscorable patients as low-risk — the exact error `prevent.py` warns against in a comment.
- `eICU note.csv` is recorded as **321 MB** in the EN "Corrected figures" list and **306 MB** in the EN reconciliation section and CN §七. The same page contradicts itself.
- Test counts 9 / 23 / 28 / 37 / 46 / 83 / 84 / 113 / 123 have all circulated as current. A rule already exists ("run `pytest -q`, never quote") but it is unenforced and applies only to test counts.

**Fault 2 — pages carry more than one job, so the same content is duplicated across trees.** The 2026-07-18 audit log and cross-source reconciliation appear in full in *both* hub pages, in *both* languages — four copies of one log, roughly 40% of each hub's length. The EN hub is simultaneously a thesis statement, a data dictionary, a metrics specification, a build-status report and an audit journal.

**Consequent asymmetry.** Because the trees were explicitly allowed to diverge, they now hold different content, not different phrasings of the same content:

| Only in CN | Only in EN |
|---|---|
| architecture diagram + component-contract table (§六) | data sources with exact tables/variables |
| technical framework / stack (§八) | NHANES and MIMIC cohort definitions |
| validation plan (§十一) | the five open decisions |
| PhD-suitability assessment (§十三) | pilot status and kill criteria |

There is also an unresolved self-contradiction inside the CN hub: §八 cites `HC-4b` as a real ticket for the CI badge, while the same page's reconciliation section lists `HC-4b` among the 幽灵编号 (phantom IDs). EN has this right.

**Literature is split three ways** with no Chinese coverage: the EN *📚 Reference Papers* page (8-paper synthesis plus a 2026-08 delta), the CN *文献定位与方向决策* snapshot (dated 2026-07-23, predates the sweep), and `docs/reference/Literature_Landscape_2026-08.md`. The Notion delta section is titled "the 13-paper delta" but the sweep holds 27 entries and the section's own table names only 24. Its open action #6 already says "merge this into the synthesis so there is one authoritative list, not two."

## 2. Goals

1. Eliminate duplicated content across the two trees and within each hub.
2. Bring the EN and CN trees to strict structural parity.
3. Separate the material into single-purpose sections that can be cited in an audit, lifted into a manuscript, or handed to a supervisor without further editing.
4. Make figure drift and parity drift **mechanically detectable** rather than dependent on manual sweeps.

## 3. Non-goals

- Re-running any pipeline or changing any pipeline code. HC-23's re-emission is a separate, ticketed benchmark-freeze action; this work records its status, it does not perform it.
- Resolving any open clinical or scientific decision. Open decisions are migrated into a register with their status intact, not settled.
- Changing the Linear board or the Notion Progress Tracker database.

## 4. Decisions taken

| # | Decision | Chosen |
|---|---|---|
| D1 | Alignment model | **Strict parity, EN canonical.** Every section exists in both trees with the same numbering. EN is source of truth; CN is a faithful full translation. |
| D2 | Decomposition | **Split by document role into separate pages**, each with a fixed section contract. |
| D3 | Fate of superseded pages | **Merge and delete**, gated behind a committed git snapshot and user review. |
| D4 | `docs/*.md` in scope | **Yes** — Notion and `docs/` receive the same structure. |
| D5 | Page count | **Eight per language** (hub + 7), amending D2's original six, to give literature/positioning a home and a Chinese counterpart. |
| D6 | Plain-language register | Preserved as `▶ In plain terms / 通俗解释` callouts inside pages 01 and 04, rather than as separate primer pages. |

D5 and D6 were raised as amendments during design and approved.

## 5. Target structure

```
PhD Source Note
├─ 🇬🇧 HTN-Concord — Master Plan (English)      [hub: page + URL retained, stripped to nav]
│   ├─ 01. Scientific Spec
│   ├─ 02. Data & Cohorts
│   ├─ 03. Tasks & Evaluation
│   ├─ 04. Architecture & Build
│   ├─ 05. Canonical Figures Register
│   ├─ 06. Audit & Decision Log
│   └─ 07. Literature & Positioning
├─ 🇨🇳 HTN-Concord — 项目全景（中文）           [hub: page + URL retained, stripped to nav]
│   └─ 01–07 identical structure, 一一对应
├─ 📋 Ticket & Progress Log                     [live, untouched]
├─ 🗄 HTN-Concord — Progress Tracker (database)  [live, untouched]
└─ My Learning Notes                            [untouched]
```

### 5.1 Hub contract

Hubs hold **only**: the one-sentence thesis, the failure-mechanism claim, RQ1–RQ3, ranked contributions and explicit cuts, the parity banner, and navigation to 01–07.

Hubs must **not** contain: any figure, any audit history, any dated correction, any build status.

### 5.2 Page contracts

| Page | Contains | Sourced from |
|---|---|---|
| **01 Scientific Spec** | claim and RQs expanded; scope in/out including the HC-28 caveat that exclusions are declared but not enforced at runtime; the why-hypertension methodological argument; the 2025 AHA/ACC encoded-logic table; comparator policy (ESC 2024 / ESH 2023 / WHO HEARTS / China 2024 encoded as separate modules, disagreement reported not merged); post-sweep novelty framing; risks including the HC-49 clinician-adjudication reframe | EN hub; CN §一/三/五 |
| **02 Data & Cohorts** | four substrates with roles and exact tables/variables; cross-source cleaning principles (missing ≠ 0, explicit units, range gates, per-reading BP context flag, de-identification artifacts); derived-variable list; NHANES cohort definition; MIMIC leakage-safe chronic-HTN cohort algorithm (anchor code sets, earliest-index rule, OMR ≥2 distinct dates within 365 d pre-index, `medrecon`-only current meds, three subcohorts); eICU abstention-probe scope | EN hub; EN *data* + walkthrough; CN §七 |
| **03 Tasks & Evaluation** | Tasks A–D with input/label/scoring; the Task-B example vignette, leakage rules and hard distractors; the nine metrics; enumerated failure modes tagged extraction/reasoning/citation; difficulty-level and subgroup reporting; kill criteria; the HC-64 archival-vs-sampling reproducibility distinction; TRIPOD-LLM mapping and ablation matrix | EN hub; EN *Experiment Design*; CN §四/十/十一 |
| **04 Architecture & Build** | pipeline diagram; component-contract table; engineering invariants; language/stack; engine implementation (`engine/types.py`, `rules/aha_acc_2025/`, `vocab.py`, PREVENT transcription); build status under the `(NOT BUILT)` convention and a "verified against commit `<sha>` on `<date>`" line | CN §六/八 (promoted to EN); EN *Architecture & Build Plan (v1)* |
| **05 Canonical Figures Register** | every number in the project, once. See §6. | all pages |
| **06 Audit & Decision Log** | append-only correction history, open-decision register, superseded-text archive. See §7. | EN hub audit sections; CN 审计记录 + 跨源对齐记录 |
| **07 Literature & Positioning** | one merged reference list with read-status; what survives as unoccupied; the frank PhD-suitability/viability assessment | EN *Reference Papers*; CN *文献定位与方向决策*; `docs/reference/Literature_Landscape_2026-08.md`; CN §十三 |

### 5.3 Pages absorbed and then deleted

**EN:** *HTN-Concord — Architecture & Build Plan (v1)*, *data*, *analysis*, *Data Selection, Types & Processing — NHANES + MIMIC (walkthrough)*, *Experiment Design — ablation matrix, RQs, TRIPOD-LLM mapping*.

**CN:** *HTN-Concord 引擎规则 HC-32 / HC-33*, *HTN-Concord 完整系统 —— LLM 那一半 & 全项目蓝图*, *数据选取、类型与处理全流程（NHANES + MIMIC）*, *实验设计 —— 消融矩阵、研究问题、TRIPOD-LLM 映射*, *文献定位与方向决策（2026-07-23 检索快照）*.

The EN *📚 Reference Papers* page is **retained and becomes page 07 EN** rather than being deleted, preserving its URL.

## 6. Canonical Figures Register

### 6.1 Schema

One row per number. Columns:

| Column | Meaning |
|---|---|
| `ID` | stable token, e.g. `FIG-NHANES-N` |
| `Figure` | what it measures |
| `Value` | the number |
| `Definition / denominator` | the exact denominator or definition |
| `Source artifact` | path to the artifact the value was read from |
| `Producing code` | path to the code that produced it |
| `Commit` | SHA at which the value was verified |
| `Verified` | date |
| `Status` | `verified` · `pending-reemission` · `unverified` · `superseded` |
| `Supersedes` | the previous incorrect value, retained visibly |

### 6.2 Citation convention

Prose may state a number **only** when immediately followed by its register ID:

> The cleaned substrate holds 4,806 adult profiles [FIG-NHANES-N].

A bare number in prose is a defect. This keeps prose readable while making every figure greppable.

Two figure classes are **banned outright** and get no register row:
- **Test counts.** CI badge only.
- **Reference/paper counts in headings.** The "13-paper delta" heading is the cautionary case.

### 6.3 Seed rows and known conflicts

The register is built by reading values off artifacts and code, **not** off the existing documents. Conflicts already on record and how each is recorded:

| Conflict | Recorded as |
|---|---|
| BP summarized by `mean` in code vs `median` in all docs (HC-23) | all downstream NHANES figures `pending-reemission`, with a note that they describe the mean pipeline |
| `eICU note.csv` 321 MB vs 306 MB | `unverified` pending a `stat` of the file on disk during implementation |
| MIMIC 28,530 vs ~8,921 vs 138,038 | three separate rows with explicit denominators; ~8,921 flagged as the only decision-capable cohort |
| PREVENT ≥7.5% = 40.7% of 3,404 scored | `Supersedes: 38.4% (wrong denominator, 3,606 age-eligible)` |
| BP Stage 1+2 = 42.8% | definition states *unweighted sample description, not population prevalence* |
| NHANES pooled-span gain 1.7× (9,254 → ~15,560) | `Supersedes: "roughly double"` |
| Post-fix label distribution over 4,806 profiles (lifestyle_only 2,545 · intensify 857 · initiate 751 · at_goal_continue 509 · abstain 144) | one row per label, all `pending-reemission` under HC-23 |

## 7. Audit & Decision Log

Append-only, newest entry first. Three subsections:

1. **Corrections (closed)** — schema: `Date · Finding · Why it matters · Ticket · Resolution`. Seeded with the 2026-07-18 three-reviewer audit and the cross-source reconciliation, **deduplicated to a single copy**.
2. **Open decisions register** — schema: `Finding · Options · Owner · Ticket · Blocking what`. Seeded with the five open decisions from the EN hub (NHANES span, MIMIC index-encounter rule, discard-reading-#1, one-vs-two papers, HC-23 re-emission) and the open audit findings HC-24, HC-25, HC-26, HC-27, HC-28, HC-49.
3. **Superseded text** — verbatim prior wording, retained so an older quotation remains traceable.

The `HC-4b` self-contradiction in CN §八 is resolved during migration in favour of the EN treatment: `HC-4a`, `HC-4b` and `HC-8b` are phantom IDs; the CI workflow and badge are both part of HC-4.

## 8. Literature & Positioning

The 8-paper synthesis (compiled 2026-07-24) and the 2026-08-05 sweep merge into **one** ranked list — satisfying the existing open action #6.

A `Read status` column is added with values `full text` · `abstract only` · `title/search only`. This is a citation-safety control: of the sweep entries, only the four executable-guideline papers had abstracts fetched; the remainder were captured from search results and titles and must not be cited until read.

No count appears in any heading.

The page also carries the frank PhD-suitability and viability assessment promoted from CN §十三, and the "what survives as genuinely unoccupied" positioning statement.

## 9. Parity contract

Each page carries a header block stating: which language is canonical, the paired page in the other tree, and the date parity was last verified.

Parity means: the same numbered sections in the same order, the same section titles in translation, and the same set of `[FIG-*]` IDs cited. It does not require sentence-level literal translation; it requires that no fact, figure, ticket ID, decision or correction exists in one tree and not the other.

## 10. CI enforcement

Notion cannot be tested; `docs/` can, and `docs/` is the canonical versioned leg. Two new tests:

**`tests/test_figures_register.py`**
- Parses the register table from `docs/HTN-Concord_05_Figures_Register.md`.
- Walks every `docs/*.md`, extracts every `[FIG-*]` citation and the numeric literal immediately preceding it.
- Fails if a cited ID is absent from the register, or if the adjacent literal does not match the register's current value.
- Fails if the register contains an ID that no document cites (dead row).

**`tests/test_bilingual_parity.py`**
- Asserts every `docs/HTN-Concord_NN_*.md` has a `_zh` counterpart.
- Asserts both files carry the same ordered list of numbered section headings.
- Asserts both files cite the same set of `[FIG-*]` IDs.

These convert parity and figure integrity from manual discipline into build failures.

## 11. Local `docs/` mapping

Eight pages × two languages = sixteen files, numbered to match the Notion tree:

```
HTN-Concord_00_Hub.md                          HTN-Concord_00_Hub_zh.md
HTN-Concord_01_Scientific_Spec.md              HTN-Concord_01_Scientific_Spec_zh.md
HTN-Concord_02_Data_and_Cohorts.md             HTN-Concord_02_Data_and_Cohorts_zh.md
HTN-Concord_03_Tasks_and_Evaluation.md         HTN-Concord_03_Tasks_and_Evaluation_zh.md
HTN-Concord_04_Architecture_and_Build.md       HTN-Concord_04_Architecture_and_Build_zh.md
HTN-Concord_05_Figures_Register.md             HTN-Concord_05_Figures_Register_zh.md
HTN-Concord_06_Audit_and_Decision_Log.md       HTN-Concord_06_Audit_and_Decision_Log_zh.md
HTN-Concord_07_Literature_and_Positioning.md   HTN-Concord_07_Literature_and_Positioning_zh.md
```

**Replaced and deleted:** `HTN-Concord_Master_Plan.md`, `HTN-Concord_DataProcessing_Walkthrough.md`, `HTN-Concord_Experiment_Design.md` and their `_zh` pairs; `docs/reference/Literature_Landscape_2026-08.md` (folds into 07).

**Retained, out of scope:** `HTN-Concord_Backlog.md` / `_zh` — Linear is the primary tracker and this mirrors it.

**Retained as a deep reference, pointed at from page 02:** `HTN-Concord_DataDictionary_and_CleaningStrategy.md` / `_zh`. Note this pair is itself asymmetric — 325 EN lines against 217 CN — and closing that gap is part of this work even though the file keeps its name.

## 12. Migration plan

Steps 1–7 are additive and reversible. Step 8 is the only destructive action.

1. **Snapshot** all thirteen current Notion pages verbatim into `docs/archive/2026-08-08-pre-restructure/` and **commit**. No deletion occurs before this lands.
2. **Build the Figures Register first**, reading values from artifacts and code rather than from documents. Verify or mark every figure currently in prose. Resolve the `eICU note.csv` size by inspecting the file.
3. Write EN pages 00–07 into `docs/`, citing register IDs.
4. Add `test_figures_register.py` and `test_bilingual_parity.py`; make the suite pass.
5. Write CN pages 00–07 to strict parity.
6. Publish all sixteen documents to Notion; strip both hubs to navigation.
7. **User reviews the new tree.**
8. Delete the ten superseded Notion pages.

## 13. Dependencies and sequencing

- `docs/reference/Literature_Landscape_2026-08.md` — required for page 07 — currently exists **only** on the unmerged branch `ariacongdev/mimic-eicu-data-pipeline-design`. Either that branch merges first, or the file is cherry-picked onto the restructure branch before step 3.
- The Notion MCP connector rejects writes containing shell-command strings (Cloudflare WAF). Page 04 describes the stack, and §10's CI tests are referenced by filename; wording must avoid literal command strings, or those passages must be published as inline code that does not read as a shell invocation.
- Both Notion trees must be updated together with the Linear board and Notion Progress Tracker whenever ticket state changes; this work does not alter ticket state.

## 14. Risks

| Risk | Mitigation |
|---|---|
| Deleting Notion pages destroys the state older supervisor emails cite | Step 1 commits a verbatim snapshot to git before any deletion; deletion is gated behind user review at step 7 |
| Content silently lost while merging thirteen pages into sixteen files | The snapshot enables a diff; acceptance requires every section of every deleted page to map to a destination |
| The CN plain-language teaching register is lost | D6 — carried forward as marked callouts in pages 01 and 04 |
| Register values are copied from prose rather than verified, reproducing the original fault | Step 2 mandates reading from artifacts and code; unverifiable values are marked `unverified`, never guessed |

## 15. Acceptance criteria

1. Both Notion trees present hub + 01–07 with identical structure and one-to-one section correspondence.
2. No figure appears in prose without a `[FIG-*]` citation; every cited ID resolves to a register row; and no instance of a banned figure class (test counts, counts in headings) appears anywhere.
3. The 2026-07-18 audit log exists in exactly one place per language.
4. The literature list is single and merged, carries a read-status column, and no heading states a count.
5. `test_figures_register.py` and `test_bilingual_parity.py` pass.
6. Every section of every deleted page maps to a destination in the new structure, demonstrable against the committed snapshot.
7. The `HC-4b` contradiction is resolved and no phantom ticket ID is cited as real.

<!-- CI badge: replace OWNER/REPO once a GitHub remote exists (see "CI" below). -->
[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)

# HTN-Concord

A clinician-free, reproducible framework that turns the 2025 AHA/ACC hypertension guideline into a
**Deterministic Guideline Engine** producing citation-linked ground-truth labels — then uses those labels to
locate *where and why* LLMs violate the guideline when reasoning over realistic clinical input.

The claim is not "GraphRAG improves accuracy." It is a **failure mechanism**: hypertension management is
multi-constraint satisfaction over `BP stage × comorbidity × contraindication × current meds`, realistic
clinical language degrades an LLM's ability to extract those constraints, and the resulting failures are
localizable to **extraction**, **reasoning**, or **unsupported citation**.

## Documentation

Docs are maintained as **English/Chinese pairs — edit both together.** On conflict, English wins.

| Document | English | 中文 |
|---|---|---|
| Master execution plan | [`docs/HTN-Concord_Master_Plan.md`](docs/HTN-Concord_Master_Plan.md) | [`..._zh.md`](docs/HTN-Concord_Master_Plan_zh.md) |
| Epics & tickets | [`docs/HTN-Concord_Backlog.md`](docs/HTN-Concord_Backlog.md) | [`..._zh.md`](docs/HTN-Concord_Backlog_zh.md) |
| Data dictionary & cleaning | [`docs/HTN-Concord_DataDictionary_and_CleaningStrategy.md`](docs/HTN-Concord_DataDictionary_and_CleaningStrategy.md) | [`..._zh.md`](docs/HTN-Concord_DataDictionary_and_CleaningStrategy_zh.md) |

Live ticket tracking is in Linear (GAI board, authoritative) mirrored to a Notion database. The backlog
markdown is a snapshot, not a source of truth.

## Quickstart

```bash
cd htn-concord
python -m venv .venv && source .venv/bin/activate    # Python 3.12
pip install -r requirements.txt
pytest -q
```

Commands run from `htn-concord/` — tests import `engine.*`, `pipelines.*` and `vocab` as top-level
modules, which only resolve from there.

## Layout

```
vocab.py      shared controlled vocabulary: med classes, comorbidity and
              contraindication flags, HTN ICD anchor sets, BP thresholds
schemas/      patient_profile.schema.json   (llm_output.schema.json NOT BUILT)
engine/       types, citations, evaluate + rules/aha_acc_2025/
              {staging, initiation_intensification}   (2 rules built)
pipelines/    nhanes/  cohort builder, derive, PREVENT, QA  — BUILT
              mimic/   config, feasibility, omr_bp          — partial
tests/        one module per rule

renderer/     NOT BUILT      runner/  NOT BUILT      evaluator/  NOT BUILT
```

Present tense describes verified-existing code only; anything planned is tagged `NOT BUILT`. This
convention exists because a doc that described an *intended* repo in the present tense produced a phantom
"1 worked rule + 9 tests" claim that cost a full spec cycle to disprove.

## Data

**No data is committed, and none should be.** `Data/` holds ~60 GB of credentialed PhysioNet sources
(MIMIC-IV, MIMIC-IV-ED, MIMIC-IV-Note, eICU-CRD) whose licences forbid redistribution, plus NHANES, which is
public but produces patient-level derived rows. Obtain them yourself:

- **NHANES 2017–2018 (cycle J)** — public: <https://wwwn.cdc.gov/nchs/nhanes/>
- **MIMIC-IV / -ED / -Note, eICU-CRD** — credentialed: <https://physionet.org/> (training + DUA required)

The Khan 2024 PREVENT paper and supplements are likewise not committed (copyright). The coefficients
transcribed from Supplemental Table S12A stay verifiable without them: the transcription is unit-tested
against the paper's published worked example (women 14.684%, men 16.317%).

## CI

`.github/workflows/ci.yml` runs the suite on every push and pull request against pinned Python 3.12.

> **Not yet active.** This repository has no GitHub remote, so the workflow has never executed and the badge
> above points at a placeholder. To activate: create the remote, `git push -u origin main`, then replace
> `OWNER/REPO` in the badge URL. Every step was dry-run locally and verified to pass, and the collection gate
> was verified to fail on a deliberately broken import — but *verified locally* is not *verified in CI*.

Two guards exist because "tests pass" was previously unverifiable:

1. **Collection integrity.** A test importing a not-yet-written module aborts collection, so the rest of the
   suite never runs. Measured: with one broken import, **zero** of 123 collectible tests execute. `pytest`
   does exit non-zero, but as "Interrupted", which reads like infrastructure noise — the explicit gate names
   it instead. **Never add `--continue-on-collection-errors`**; it downgrades a structural break to an
   ordinary failure.
2. **Silent test-count collapse.** The failure no exit code catches: a module-level `try/except ImportError`
   or a stray `importorskip` makes tests vanish rather than fail, and the suite goes green with fewer tests.
   The collected count is published to the run summary so a drop is visible between runs.

**Never quote a test count in prose.** Nine different counts (9 / 23 / 28 / 37 / 46 / 83 / 84 / 113 / 123)
have circulated through these documents, every one stale within days — including, at one point, the sentence
warning about stale counts. Run `pytest -q`; let the badge answer the question.

<!-- Repo is private: this badge renders for authenticated collaborators only.
     Anonymous viewers see nothing until the repo goes public at HC-90. -->
[![CI](https://github.com/AriaCong/htn-concord/actions/workflows/ci.yml/badge.svg)](https://github.com/AriaCong/htn-concord/actions/workflows/ci.yml)

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

> 🚨 **Open blocker for HC-90 (making this repo public) — ticket HC-56.**
> `tests/test_mimic_omr_bp.py` contains a fixture row that is a **verbatim record from the credentialed
> MIMIC-IV `omr` table**: `10000032,2180-04-27,1,Blood Pressure,110/65`, confirmed present in `omr.csv.gz`
> (that subject has 41 real rows). The neighbouring `10000099` rows are synthetic.
> This is contained while the repo is private, but PhysioNet's DUA forbids redistributing MIMIC data, so it
> **must be resolved before the repo goes public.** Either confirm the row comes from the ODbL-licensed
> MIMIC-IV *demo* subset — which is redistributable, and `10000032` is plausibly a demo patient — and record
> that determination here, or replace the fixture with synthetic values. Do not make the repo public on the
> assumption that a single row is de minimis.

## CI

`.github/workflows/ci.yml` runs the suite on every push and pull request against pinned Python 3.12.

**Active and green.** First run: [`29642244912`](https://github.com/AriaCong/htn-concord/actions/runs/29642244912)
— all 8 steps succeeded, 123 collected / 123 passed on Python 3.12.13, pytest 9.0.2, matching local exactly.

> **Repository visibility: private.** The badge therefore renders only for authenticated collaborators;
> anonymous viewers see nothing until the repo is made public at HC-90. See "Data" below for why private is
> the correct default here, and `docs/` for the open-sourcing plan.

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

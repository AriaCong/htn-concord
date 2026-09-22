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
schemas/      patient_profile.schema.json, llm_output.schema.json      (both built)
engine/       types, citations, evaluate + rules/aha_acc_2025/
              {staging, initiation_intensification}                    (2 rules built;
              drug-class / comorbidity / contraindication / abstention /
              citation-linker / trace-emitter rules NOT BUILT — HC-34..39)
pipelines/    nhanes/  cohort builder, derive, PREVENT, QA             — BUILT
              mimic/   config, feasibility, omr_bp                     — partial
leakage.py    forbidden-token scanner shared by renderer + Task-B gate — BUILT (HC-46)
renderer/     phrasing, render — 3-level facts-only vignettes          — BUILT (HC-50)
tasks/        profiles, splits, spotcheck, task_b — Task-B builder + leakage audit — BUILT (HC-53)
runner/       providers, run_case — JSON-mode runner + transcript replay — BUILT (HC-60;
              AnthropicProvider authored but not yet run against the live API)
evaluator/    metrics, score — all 9 plan metrics + aggregation         — BUILT (HC-70)
tests/        one module per rule
```

Present tense describes verified-existing code only; anything planned is tagged `NOT BUILT`. This
convention exists because a doc that described an *intended* repo in the present tense produced a phantom
"1 worked rule + 9 tests" claim that cost a full spec cycle to disprove. *(Synced 2026-07-23 against
Linear + the working tree: renderer / tasks / runner / evaluator and `llm_output.schema.json` are now
built — the earlier `NOT BUILT` block had itself gone stale, the very failure this convention guards.)*

## Data

**No data is committed, and none should be.** `Data/` holds ~60 GB of credentialed PhysioNet sources
(MIMIC-IV, MIMIC-IV-ED, MIMIC-IV-Note, eICU-CRD) whose licences forbid redistribution, plus NHANES, which is
public but produces patient-level derived rows. Obtain them yourself:

- **NHANES 2017–2018 (cycle J)** — public: <https://wwwn.cdc.gov/nchs/nhanes/>
- **MIMIC-IV / -ED / -Note, eICU-CRD** — credentialed: <https://physionet.org/> (training + DUA required)

The Khan 2024 PREVENT paper and supplements are likewise not committed (copyright). The coefficients
transcribed from Supplemental Table S12A stay verifiable without them: the transcription is unit-tested
against the paper's published worked example (women 14.684%, men 16.317%).

> ✅ **HC-56 resolved 2026-09-20 — no credentialed data remains in any committed file.**
> `tests/test_mimic_omr_bp.py` previously carried **three** verbatim rows from the credentialed
> MIMIC-IV `omr` table (the ticket named only one), and this README quoted one of them in full.
> **Determination: they were not license-cleared.** The ODbL *demo* subset was not confirmed as their
> source, and PhysioNet's DUA forbids redistributing MIMIC-IV data, so they were replaced rather than
> justified — the conservative reading, since a wrong call here is a licence breach and the cost of
> replacing a fixture is nil.
>
> The fixture is now wholly synthetic. Fixture `subject_id`s live in the `9xxxxxxx` range, which is
> provably disjoint from the real MIMIC-IV range `10000032`–`19999987` (verified against
> `hosp/patients.csv.gz`), so no fixture line can be a verbatim record. A regression test,
> `test_fixture_contains_no_credentialed_subject_id`, pins that invariant so the problem cannot
> return silently. Adopt the same `9xxxxxxx` convention for every new MIMIC fixture.

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

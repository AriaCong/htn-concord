"""HC-80 pilot: run C1 at all three levels on two models, k times each.

The pilot exists to answer one question — **does this corpus tell two models
apart?** — and to make "no" cheap to discover. Its numbers are *not results*:
they inform a go/no-go and nothing else, and they are provisional until HC-57
closes.

**Scope, resolved 2026-09-20.** The backlog said 20 cases × 3 difficulties × 2
models; Experiment Design §11 said moderate level only. §11 was internally
inconsistent — it stated the kill criterion as "all difficulties near ceiling",
which one difficulty cannot evaluate. Resolved in favour of all three levels;
see `docs/HTN-Concord_Pilot_Kill_Criteria.md` §7.

**Append-only and resumable.** 600 calls cost real money, and a crash at call 450
must not mean paying for the first 450 again. Every call appends one record; a
re-run skips the keys already present.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from evaluator import score as scoring
from runner import (
    MalformedOutputError,
    RefusalError,
    TruncatedOutputError,
    run_case,
)
from runner.providers import Provider
from tasks.task_b import INPUTS_FILE, LABELS_FILE

LEVELS: tuple[str, ...] = ("simple", "moderate", "hard")


@dataclass(frozen=True)
class PilotSpec:
    """Everything that defines the pilot's shape. Recorded beside its results."""
    models: tuple[str, ...]
    n_patients: int = 20
    levels: tuple[str, ...] = LEVELS
    replicates: int = 5              # design §4.4, D2 — raise if pilot SD is large
    split: str = "test"
    seed: int = 80                   # HC-80
    condition: str = "C1"

    @property
    def n_calls(self) -> int:
        return (self.n_patients * len(self.levels) * len(self.models)
                * self.replicates)


DEFAULT_SPEC = PilotSpec(models=())


@dataclass(frozen=True)
class CallRecord:
    """One model call's outcome. `key` is what makes a re-run idempotent."""
    case_id: str
    patient_id: str
    level: str
    model: str
    replicate: int
    outcome: str                     # ok | refusal | truncated | malformed
    output: Mapping[str, Any] | None = None
    transcript: Mapping[str, Any] | None = None
    detail: str | None = None

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.case_id, self.model, self.replicate)

    def to_json(self) -> str:
        return json.dumps({
            "case_id": self.case_id, "patient_id": self.patient_id,
            "level": self.level, "model": self.model, "replicate": self.replicate,
            "outcome": self.outcome, "output": self.output,
            "transcript": self.transcript, "detail": self.detail,
        }, ensure_ascii=False)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def select_patients(corpus_dir: str | Path, spec: PilotSpec) -> list[str]:
    """Deterministically pick the pilot's patients from one split.

    Stratified by engine decision, for the same reason the spot-check is: the
    test split is 51.5% `lifestyle_only`, so a uniform draw of 20 would be mostly
    one class and the pilot would learn nothing about abstention or the rarer
    decisions. Round-robin across decisions keeps the sample balanced when
    `n_patients` does not divide evenly.
    """
    labels = _read_jsonl(Path(corpus_dir) / LABELS_FILE)
    by_decision: dict[str, set[str]] = {}
    for row in labels:
        if row["split"] != spec.split or not row["case_id"].endswith("-simple"):
            continue
        by_decision.setdefault(row["decision"], set()).add(str(row["patient_id"]))

    rng = random.Random(spec.seed)
    pools = {d: rng.sample(sorted(p), len(p)) for d, p in sorted(by_decision.items())}
    picked: list[str] = []
    while len(picked) < spec.n_patients and any(pools.values()):
        for decision in sorted(pools):
            if len(picked) >= spec.n_patients:
                break
            if pools[decision]:
                picked.append(pools[decision].pop())
    return sorted(picked)


def iter_planned_calls(corpus_dir: str | Path, spec: PilotSpec) -> Iterator[dict[str, Any]]:
    """Every call the pilot intends to make, in a stable order."""
    patients = select_patients(corpus_dir, spec)
    inputs = {r["case_id"]: r for r in _read_jsonl(Path(corpus_dir) / INPUTS_FILE)}
    for patient in patients:
        for level in spec.levels:
            case_id = f"taskb-{patient}-{level}"
            record = inputs.get(case_id)
            if record is None:
                continue
            for model in spec.models:
                for replicate in range(1, spec.replicates + 1):
                    yield {"case_id": case_id, "patient_id": patient,
                           "level": level, "model": model,
                           "replicate": replicate, "vignette": record["vignette"]}


def load_records(out_path: str | Path) -> list[CallRecord]:
    path = Path(out_path)
    if not path.exists():
        return []
    return [CallRecord(**{k: v for k, v in row.items()})
            for row in _read_jsonl(path)]


def run_pilot(corpus_dir: str | Path, spec: PilotSpec, out_path: str | Path,
              provider_for: Callable[[str], Provider], *,
              profiles: Mapping[str, Mapping[str, Any]] | None = None,
              on_call: Callable[[CallRecord, int, int], None] | None = None,
              on_error: Callable[[Mapping[str, Any], Exception], None] | None = None,
              max_attempts: int = 3,
              api_retries: int = 3,
              sleep: Callable[[float], None] = time.sleep) -> list[CallRecord]:
    """Run (or resume) the pilot, appending one JSON line per call.

    The hidden profile is passed to `run_case` only to be hashed into the
    transcript for linkage. It is never serialized into a request — that is the
    runner's half of the anti-leakage discipline, and `ScriptedProvider` records
    every request so a test can assert it.

    **Transport failures are not model behaviour.** A 429 or a 5xx mid-run used
    to propagate and end a multi-hour run. It is now retried with backoff, and if
    it still fails **no record is written**: the resume check skips keys already
    present, so recording an outage would bake a permanent hole into the
    denominator instead of letting the next resume fill it. Only outcomes the
    model is responsible for — refusal, truncation, malformed output — are
    recorded and counted.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r.key for r in load_records(out)}
    records: list[CallRecord] = []
    planned = list(iter_planned_calls(corpus_dir, spec))

    with out.open("a", encoding="utf-8") as handle:
        for index, call in enumerate(planned, 1):
            key = (call["case_id"], call["model"], call["replicate"])
            if key in done:
                continue
            profile = (profiles or {}).get(call["patient_id"])
            record: CallRecord | None = None
            for api_attempt in range(1, api_retries + 1):
                try:
                    result = run_case(
                        model=call["model"],
                        prompt_input=call["vignette"],
                        profile=profile,
                        provider=provider_for(call["model"]),
                        case_id=call["case_id"],
                        task="B",
                        max_attempts=max_attempts,
                    )
                    record = CallRecord(
                        case_id=call["case_id"], patient_id=call["patient_id"],
                        level=call["level"], model=call["model"],
                        replicate=call["replicate"], outcome="ok",
                        output=result.output, transcript=result.transcript,
                    )
                except RefusalError as exc:
                    record = _failure(call, "refusal",
                                      f"{exc} category={exc.category!r}")
                except TruncatedOutputError as exc:
                    record = _failure(call, "truncated", str(exc))
                except MalformedOutputError as exc:
                    record = _failure(call, "malformed", str(exc))
                except Exception as exc:          # transport, not the model
                    if api_attempt >= api_retries:
                        if on_error is not None:
                            on_error(call, exc)
                        break
                    sleep(min(60.0, 5.0 * 2 ** (api_attempt - 1)))
                    continue
                break

            if record is None:
                continue        # nothing written, so a resume retries this call

            handle.write(record.to_json() + "\n")
            handle.flush()          # a crash must not lose calls already paid for
            records.append(record)
            if on_call is not None:
                on_call(record, index, len(planned))
    return records


def _failure(call: Mapping[str, Any], outcome: str, detail: str) -> CallRecord:
    return CallRecord(
        case_id=call["case_id"], patient_id=call["patient_id"],
        level=call["level"], model=call["model"], replicate=call["replicate"],
        outcome=outcome, detail=detail,
    )


def summarize(records: Sequence[CallRecord], corpus_dir: str | Path,
              profiles: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score the pilot and produce the per-model, per-level report.

    Three things this deliberately does not do:

    * it does not drop failed calls silently — `harness` reports refusal,
      truncation and malformed rates over the *attempted* denominator, because a
      model that refuses 30% of cases and answers the rest perfectly is not a
      90%-concordant model;
    * it does not average the two abstention directions together;
    * it does not strip `majority_class_baseline` from beside the concordance
      figures. `evaluator.aggregate` emits it and it travels with every number.
    """
    labels = {r["case_id"]: r for r in _read_jsonl(Path(corpus_dir) / LABELS_FILE)}

    scored: dict[tuple[str, str], list[scoring.CaseScore]] = {}
    per_case: dict[tuple[str, str, str], list[bool]] = {}
    harness: dict[str, dict[str, int]] = {}

    for record in records:
        counts = harness.setdefault(record.model, {
            "attempted": 0, "ok": 0, "refusal": 0, "truncated": 0, "malformed": 0})
        counts["attempted"] += 1
        counts[record.outcome] += 1
        if record.outcome != "ok" or record.output is None:
            continue
        case_score = scoring.score_case(
            record.output, labels[record.case_id],
            profiles.get(record.patient_id, {}),
            case_id=record.case_id, level=record.level)
        scored.setdefault((record.model, record.level), []).append(case_score)
        per_case.setdefault((record.model, record.level, record.case_id), []).append(
            case_score.decision_concordance)

    by_model_level = {
        f"{model}|{level}": scoring.aggregate(group)
        for (model, level), group in sorted(scored.items())
    }
    by_model = {
        model: scoring.aggregate([s for (m, _), g in scored.items() if m == model
                                  for s in g])
        for model in sorted({m for m, _ in scored})
    }

    for model, counts in harness.items():
        attempted = counts["attempted"] or 1
        counts["malformed_output_rate"] = counts["malformed"] / attempted
        counts["refusal_rate"] = counts["refusal"] / attempted
        counts["truncation_rate"] = counts["truncated"] / attempted

    return {
        "by_model": by_model,
        "by_model_level": by_model_level,
        "harness": harness,
        "replicate_sd": _replicate_sd(per_case),
        "n_records": len(records),
    }


def _replicate_sd(per_case: Mapping[tuple[str, str, str], Sequence[bool]]
                  ) -> dict[str, Any]:
    """Across-replicate SD of case-level concordance (design §4.4, decision D2).

    Run-to-run variance is a quantity this project reports rather than hides:
    sampling parameters are not pinnable on current frontier models (HC-64), so
    this is the measurement that stands in for the determinism we cannot have.
    """
    from statistics import median, stdev

    per_model: dict[str, list[float]] = {}
    for (model, _level, _case), values in per_case.items():
        if len(values) < 2:
            continue
        per_model.setdefault(model, []).append(stdev(float(v) for v in values))
    return {
        model: {"median_sd": median(sds), "max_sd": max(sds), "n_cases": len(sds)}
        for model, sds in sorted(per_model.items())
    }

"""HC-53 — Task B builder: rendered vignette in, hidden engine label out.

Task B is the headline task. One structured PatientProfile produces three cases
(simple / moderate / hard); the model sees only the vignette, and the label is the
engine's decision on the *hidden* row.

**Physical separation (Master Plan principle 4).** Inputs and labels are written to
two separate files joined only by `case_id`. Nothing that reaches a model lives in
the same file as an answer, so a wrong path in a later script produces a missing
key rather than a silently leaked label. `task_b_inputs.jsonl` is the only file the
runner is ever given.

**The audit gate.** Build refuses to emit a corpus whose inputs carry a
label-bearing token. It is a gate, not a report: a corpus that fails is not
written, because a leaked benchmark that exists on disk will eventually get used.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import leakage
from engine.evaluate import evaluate
from engine.types import EngineDecision
from renderer import LEVELS, render
from tasks.splits import DEFAULT_SALT, assert_disjoint, assign_split, split_counts

BUILD_VERSION = "1.0"

INPUTS_FILE = "task_b_inputs.jsonl"
LABELS_FILE = "task_b_labels.jsonl"
MANIFEST_FILE = "task_b_manifest.json"

# Profile keys that must never appear in a model-facing record. Distinct from the
# token scanner: that catches leaked *prose*, this catches a leaked *column*.
_LABEL_KEYS: frozenset[str] = frozenset({
    "bp_stage", "prevent_10yr", "ckd_albuminuria", "contraindications",
    "decision", "triggers", "abstain_reason", "citations", "trace",
})


class LeakageAuditFailed(RuntimeError):
    """The built corpus did not pass the leakage gate; nothing was written."""


@dataclass
class AuditReport:
    """Result of auditing a built corpus. `ok` gates the write."""
    n_cases: int = 0
    n_token_hits: int = 0
    n_label_key_hits: int = 0
    findings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.ok,
            "n_cases_audited": self.n_cases,
            "n_token_hits": self.n_token_hits,
            "n_label_key_hits": self.n_label_key_hits,
            "findings": self.findings[:20],
        }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patient_id(profile: Mapping[str, Any]) -> str:
    for key in ("SEQN", "subject_id", "case_id", "patient_id"):
        if profile.get(key) not in (None, ""):
            return str(profile[key])
    raise KeyError("profile carries no usable patient identifier "
                   "(expected one of SEQN / subject_id / case_id / patient_id)")


def _label_payload(decision: EngineDecision) -> dict[str, Any]:
    """The hidden label, flattened to JSON. Mirrors EngineDecision exactly."""
    return {
        "decision": decision.decision.value,
        "bp_stage": decision.bp_stage,
        "triggers": list(decision.triggers),
        "abstain_reason": decision.abstain_reason,
        "citations": [c.anchor for c in decision.citations],
        "trace": [{"rule": s.rule, "detail": s.detail, "citation": s.citation}
                  for s in decision.trace],
    }


def build_cases(profiles: Iterable[Mapping[str, Any]], *,
                levels: Sequence[str] = LEVELS,
                seed: int = 0,
                salt: str = DEFAULT_SALT) -> tuple[list[dict], list[dict]]:
    """Render + label every (profile x level). Returns (inputs, labels).

    The two lists are parallel by `case_id` and share no other field. The engine
    runs on the structured profile and never sees the vignette, which is the
    labelling half of the leakage discipline.
    """
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []

    for profile in profiles:
        patient_id = _patient_id(profile)
        split = assign_split(patient_id, salt)
        decision = evaluate(profile)  # label from the hidden row, once per patient
        label_payload = _label_payload(decision)

        for level in levels:
            case_id = f"taskb-{patient_id}-{level}"
            vignette = render(profile, level, seed=seed)  # self-checks for leakage

            inputs.append({
                "case_id": case_id,
                "task": "B",
                "level": level,
                "split": split,
                "patient_id": patient_id,
                "source": profile.get("source"),
                "vignette": vignette,
                "vignette_sha256": _sha256_text(vignette),
            })
            labels.append({
                "case_id": case_id,
                "patient_id": patient_id,
                "split": split,
                "level": level,
                **label_payload,
            })

    return inputs, labels


def audit(inputs: Sequence[Mapping[str, Any]],
          labels: Sequence[Mapping[str, Any]] | None = None) -> AuditReport:
    """Leakage audit over model-facing records. Empty findings == pass.

    Three independent checks, because they fail in different ways:
      1. no forbidden token in any vignette (leaked prose);
      2. no label column present on an input record (leaked schema);
      3. inputs and labels align 1:1 on case_id (a silent join error would pair a
         vignette with the wrong answer and read as model failure).
    """
    report = AuditReport(n_cases=len(inputs))

    for record in inputs:
        case_id = record.get("case_id", "<unknown>")

        hits = leakage.scan(str(record.get("vignette", "")))
        if hits:
            report.n_token_hits += len(hits)
            report.findings.append(f"{case_id}: {len(hits)} forbidden token(s): {hits[0]}")

        present = _LABEL_KEYS.intersection(record)
        if present:
            report.n_label_key_hits += len(present)
            report.findings.append(f"{case_id}: label column(s) on a model-facing record: "
                                   f"{sorted(present)}")

    if labels is not None:
        in_ids = [r["case_id"] for r in inputs]
        lab_ids = [r["case_id"] for r in labels]
        if len(set(in_ids)) != len(in_ids):
            report.findings.append("duplicate case_id among inputs")
        if set(in_ids) != set(lab_ids):
            missing = set(in_ids) ^ set(lab_ids)
            report.findings.append(f"inputs/labels do not align on case_id: "
                                   f"{len(missing)} unmatched, e.g. {sorted(missing)[:3]}")
    return report


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build(profiles: Iterable[Mapping[str, Any]], out_dir: str | Path, *,
          levels: Sequence[str] = LEVELS,
          seed: int = 0,
          salt: str = DEFAULT_SALT) -> dict[str, Any]:
    """Build, audit, and freeze the Task-B corpus. Returns the manifest.

    Raises LeakageAuditFailed *before writing anything* if the audit does not pass.
    """
    profiles = list(profiles)
    inputs, labels = build_cases(profiles, levels=levels, seed=seed, salt=salt)

    report = audit(inputs, labels)
    if not report.ok:
        raise LeakageAuditFailed(
            f"leakage audit failed with {len(report.findings)} finding(s); corpus not written. "
            + "; ".join(report.findings[:5]))
    assert_disjoint(inputs)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    inputs_path, labels_path = out / INPUTS_FILE, out / LABELS_FILE
    _write_jsonl(inputs_path, inputs)
    _write_jsonl(labels_path, labels)

    decision_counts: dict[str, int] = {}
    for record in labels:
        decision_counts[record["decision"]] = decision_counts.get(record["decision"], 0) + 1

    manifest = {
        "build_version": BUILD_VERSION,
        "task": "B",
        "n_patients": len(profiles),
        "n_cases": len(inputs),
        "levels": list(levels),
        "render_seed": seed,
        "split_salt": salt,
        "patients_per_split": split_counts([_patient_id(p) for p in profiles], salt),
        "cases_per_split": {s: sum(1 for r in inputs if r["split"] == s)
                            for s in sorted({r["split"] for r in inputs})},
        "decision_distribution": dict(sorted(decision_counts.items())),
        "leakage_audit": report.summary(),
        "files": {
            INPUTS_FILE: {"sha256": _sha256_file(inputs_path),
                          "n_records": len(inputs),
                          "model_facing": True},
            LABELS_FILE: {"sha256": _sha256_file(labels_path),
                          "n_records": len(labels),
                          "model_facing": False},
        },
    }
    (out / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(out_dir: str | Path) -> dict[str, Any]:
    """Re-check a frozen corpus on disk: checksums still match, audit still passes.

    This is what makes the split *frozen* rather than merely *recorded* -- it turns
    "the benchmark has not changed" into an assertion anyone can run, including a
    reviewer working from the released artifact.
    """
    out = Path(out_dir)
    manifest = json.loads((out / MANIFEST_FILE).read_text())

    mismatches = []
    for name, meta in manifest["files"].items():
        actual = _sha256_file(out / name)
        if actual != meta["sha256"]:
            mismatches.append(f"{name}: manifest {meta['sha256'][:12]} != actual {actual[:12]}")
    if mismatches:
        raise LeakageAuditFailed("frozen corpus checksum mismatch: " + "; ".join(mismatches))

    inputs = [json.loads(line) for line in (out / INPUTS_FILE).read_text().splitlines() if line]
    labels = [json.loads(line) for line in (out / LABELS_FILE).read_text().splitlines() if line]
    report = audit(inputs, labels)
    if not report.ok:
        raise LeakageAuditFailed("frozen corpus fails the leakage audit: "
                                 + "; ".join(report.findings[:5]))
    assert_disjoint(inputs)
    return manifest

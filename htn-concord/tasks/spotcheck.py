"""Generate the human facts-only spot-check sample (HC-53 acceptance gate).

The Phase-4 gate has two halves: the mechanical leakage audit (`tasks.task_b.audit`,
which runs on every case) and *a human confirming that 20 rendered vignettes state
only facts*. A scanner catches the forbidden tokens it was told about; only a reader
catches a vignette that gives the answer away in wording nobody thought to ban. This
module produces the sample for that read.

Sampling is stratified by engine decision and shows all three levels of each patient,
so the reviewer sees the cases most likely to leak (abstentions, contraindication
positives) rather than a uniform draw dominated by `lifestyle_only`.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from tasks.task_b import INPUTS_FILE, LABELS_FILE

DEFAULT_PER_DECISION = 4


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build_spotcheck(corpus_dir: str | Path, out_path: str | Path | None = None, *,
                    per_decision: int = DEFAULT_PER_DECISION,
                    seed: int = 20) -> str:
    """Render a stratified spot-check sheet as Markdown. Returns the text."""
    corpus = Path(corpus_dir)
    inputs = _read_jsonl(corpus / INPUTS_FILE)
    labels = {r["case_id"]: r for r in _read_jsonl(corpus / LABELS_FILE)}

    by_case = {r["case_id"]: r for r in inputs}
    patients_by_decision: dict[str, set[str]] = {}
    for record in inputs:
        decision = labels[record["case_id"]]["decision"]
        patients_by_decision.setdefault(decision, set()).add(record["patient_id"])

    rng = random.Random(seed)
    picked: list[tuple[str, str]] = []
    for decision in sorted(patients_by_decision):
        pool = sorted(patients_by_decision[decision])
        for patient in rng.sample(pool, min(per_decision, len(pool))):
            picked.append((decision, patient))

    lines = [
        "# Task B — facts-only spot-check (HC-53 acceptance gate)",
        "",
        f"{len(picked)} patients, stratified by engine decision ({per_decision} per decision), "
        "all three difficulty levels each.",
        "",
        "**What to check, per vignette:** every statement is a raw observation; nothing "
        "names a BP stage, states or implies a treatment decision, or names a drug *class*; "
        "and the three levels describe the same patient with the same facts.",
        "",
        "The hidden label is shown here for the reviewer only. It is not in "
        f"`{INPUTS_FILE}`, which is the only file a model is ever given.",
    ]

    for i, (decision, patient) in enumerate(picked, 1):
        label = labels[f"taskb-{patient}-simple"]
        extras = []
        if label["triggers"]:
            extras.append("triggers: " + ", ".join(label["triggers"]))
        if label["abstain_reason"]:
            extras.append("abstain: " + label["abstain_reason"])
        suffix = f" ({'; '.join(extras)})" if extras else ""

        lines += ["", "---", "",
                  f"## {i}. patient {patient} — hidden label: **{decision}**{suffix}",
                  "",
                  f"*split: {label['split']} · hidden bp_stage: {label['bp_stage']}*"]
        for level in ("simple", "moderate", "hard"):
            record = by_case.get(f"taskb-{patient}-{level}")
            if record:
                lines += ["", f"### {level}", "", record["vignette"]]

    text = "\n".join(lines) + "\n"
    if out_path is not None:
        Path(out_path).write_text(text, encoding="utf-8")
    return text

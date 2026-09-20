"""Generate the human facts-only spot-check sample (HC-53 acceptance gate, HC-57).

The Phase-4 gate has two halves: the mechanical leakage audit (`tasks.task_b.audit`,
which runs on every case) and *a human confirming that rendered vignettes state only
facts*. A scanner catches the forbidden tokens it was told about; only a reader
catches a vignette that gives the answer away in wording nobody thought to ban. This
module produces the sample for that read.

**Three strata, because one was not enough.** Sampling by engine decision alone
leaves two blind spots, both found by auditing the real corpus on 2026-09-20:

1. `abstain` is a single decision word covering three different rule paths. The
   corpus carries `stage1_risk_indeterminate` (131 patients),
   `pregnancy_management_out_of_scope` (45) and `med_status_unknown` (12); a draw of
   four abstentions returned four of the first kind, so the prose the other two
   paths produce went unread by the only gate that can catch it.
2. Contraindication flags are **not in the labels file** at all -- by design, they
   are part of the hidden row -- so nothing here could sample for them. Hyperkalemia
   does not change the engine's decision, so its nine carriers in 4,806 patients are
   invisible to decision stratification and a 20-patient draw will never show one.

So the sheet is built from a decision stratum, an abstain-mechanism stratum, and
(when the profiles are supplied) a contraindication stratum. Every patient is shown
at all three difficulty levels, and each entry records why it was selected.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tasks.task_b import INPUTS_FILE, LABELS_FILE

DEFAULT_PER_DECISION = 4
DEFAULT_PER_MECHANISM = 1
DEFAULT_PER_CONTRAINDICATION = 2


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _pick(rng: random.Random, pool: Iterable[str], taken: set[str], n: int) -> list[str]:
    """Deterministically draw up to `n` patients not already on the sheet."""
    candidates = sorted(set(pool) - taken)
    chosen = rng.sample(candidates, min(n, len(candidates)))
    taken.update(chosen)
    return chosen


def build_spotcheck(corpus_dir: str | Path, out_path: str | Path | None = None, *,
                    per_decision: int = DEFAULT_PER_DECISION,
                    per_mechanism: int = DEFAULT_PER_MECHANISM,
                    per_contraindication: int = DEFAULT_PER_CONTRAINDICATION,
                    profiles: Sequence[Mapping[str, Any]] | None = None,
                    seed: int = 20) -> str:
    """Render a stratified spot-check sheet as Markdown. Returns the text.

    `profiles` is the hidden structured rows the corpus was built from. It is
    optional only so the sheet can still be generated without them; when it is
    omitted the sheet says in its own header that contraindication coverage was not
    included, rather than letting a reader assume it was.
    """
    corpus = Path(corpus_dir)
    inputs = _read_jsonl(corpus / INPUTS_FILE)
    labels = {r["case_id"]: r for r in _read_jsonl(corpus / LABELS_FILE)}

    by_case = {r["case_id"]: r for r in inputs}
    patients_by_decision: dict[str, set[str]] = {}
    patients_by_mechanism: dict[str, set[str]] = {}
    for record in inputs:
        label = labels[record["case_id"]]
        patient = str(record["patient_id"])
        patients_by_decision.setdefault(label["decision"], set()).add(patient)
        if label["abstain_reason"]:
            patients_by_mechanism.setdefault(label["abstain_reason"], set()).add(patient)

    patients_by_flag: dict[str, set[str]] = {}
    for row in profiles or ():
        for flag in row.get("contraindications") or ():
            patients_by_flag.setdefault(flag, set()).add(str(row["SEQN"]))

    rng = random.Random(seed)
    taken: set[str] = set()
    picked: list[tuple[str, str]] = []          # (why, patient)

    for decision in sorted(patients_by_decision):
        for patient in _pick(rng, patients_by_decision[decision], taken, per_decision):
            picked.append((f"decision stratum — {decision}", patient))

    supplementary: list[tuple[str, str]] = []
    for mechanism in sorted(patients_by_mechanism):
        already = len(patients_by_mechanism[mechanism] & taken)
        wanted = max(0, per_mechanism - already)
        for patient in _pick(rng, patients_by_mechanism[mechanism], taken, wanted):
            supplementary.append((f"abstain mechanism — {mechanism}", patient))

    for flag in sorted(patients_by_flag):
        already = len(patients_by_flag[flag] & taken)
        wanted = max(0, per_contraindication - already)
        for patient in _pick(rng, patients_by_flag[flag], taken, wanted):
            supplementary.append((f"contraindication — {flag}", patient))

    lines = [
        "# Task B — facts-only spot-check (HC-53 acceptance gate / HC-57 sign-off)",
        "",
        f"**{len(picked)} patients** in the main sample, stratified by engine decision "
        f"({per_decision} per decision), plus **{len(supplementary)}** added to cover "
        "rule paths and hidden-row flags that decision stratification cannot reach. "
        "Every patient is shown at all three difficulty levels.",
        "",
        "**What to check, per vignette:** every statement is a raw observation; nothing "
        "names a BP stage, states or implies a treatment decision, or names a drug *class*; "
        "and the three levels describe the same patient with the same facts.",
        "",
        "The hidden label is shown here for the reviewer only. It is not in "
        f"`{INPUTS_FILE}`, which is the only file a model is ever given.",
    ]
    if profiles is None:
        lines += [
            "",
            "> ⚠️ **Contraindication coverage not included.** This sheet was generated "
            "without the structured profiles, and contraindication flags live on the "
            "hidden row rather than in the labels file. Patients carrying a "
            "contraindication are therefore present only by chance. Re-generate with "
            "`profiles=` to cover them.",
        ]

    def emit(index: int, why: str, patient: str) -> None:
        label = labels[f"taskb-{patient}-simple"]
        extras = []
        if label["triggers"]:
            extras.append("triggers: " + ", ".join(label["triggers"]))
        if label["abstain_reason"]:
            extras.append("abstain: " + label["abstain_reason"])
        suffix = f" ({'; '.join(extras)})" if extras else ""

        lines.extend(["", "---", "",
                      f"## {index}. patient {patient} — hidden label: "
                      f"**{label['decision']}**{suffix}",
                      "",
                      f"*split: {label['split']} · hidden bp_stage: {label['bp_stage']} "
                      f"· sampled as: {why}*"])
        for level in ("simple", "moderate", "hard"):
            record = by_case.get(f"taskb-{patient}-{level}")
            if record:
                lines.extend(["", f"### {level}", "", record["vignette"]])

    index = 0
    for why, patient in picked:
        index += 1
        emit(index, why, patient)

    if supplementary:
        lines.extend(["", "---", "",
                      "# Supplementary coverage",
                      "",
                      "Patients a decision-stratified draw cannot be relied on to "
                      "surface: the rare abstain mechanisms, and the contraindication "
                      "flags that live on the hidden row and do not change the "
                      "decision. Read these with the same question."])
        for why, patient in supplementary:
            index += 1
            emit(index, why, patient)

    text = "\n".join(lines) + "\n"
    if out_path is not None:
        Path(out_path).write_text(text, encoding="utf-8")
    return text

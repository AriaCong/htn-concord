"""HC-50 — deterministic, facts-only vignette renderer (3 difficulty levels).

    render(profile, level, seed) -> str

**Design invariant: difficulty changes presentation, never information.** All three
levels render the same fact set. `simple` states each fact as a labelled line in
canonical order; `moderate` folds them into clinical prose; `hard` scatters them
through a longer narrative in a seeded order with inert filler. A model that
extracts perfectly gets the same evidence at every level, so a level-over-level
accuracy drop localizes to *extraction*, not to a question the vignette never
answered. Levels that dropped facts would confound difficulty with answerability
and quietly invalidate the per-level breakdown the pilot (HC-80) turns on.

Facts-only means raw observations, never derived labels. Rendered: BP values,
creatinine, eGFR, potassium, UACR, HbA1c, lipids, named drugs, history.
Never rendered: `bp_stage`, `prevent_10yr`, `ckd_albuminuria`, or any
`contraindications` flag *as a flag*. Those are engine determinants -- the model
has to re-derive them from the raw values, which is the task. Their raw inputs
are all present, so nothing is unanswerable: PREVENT's inputs (age, sex, BP,
lipids, eGFR, diabetes, smoking, statin, BP-med status) are rendered
individually, and hyperkalemia is rendered as a potassium number.

Determinism: seeded off a SHA-256 of (case identity, level, seed) rather than
`hash()`, whose string salt varies per interpreter process -- `hash()` would make
the corpus irreproducible across runs while looking fine inside one.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Literal, Mapping

import leakage
from renderer import phrasing
from renderer.phrasing import dec, num, person_noun, pronouns

Level = Literal["simple", "moderate", "hard"]
LEVELS: tuple[Level, ...] = ("simple", "moderate", "hard")

# Inert narrative filler for the `hard` level: visit logistics only. Deliberately
# carries NO clinical facts -- adding decision-relevant traps is HC-51's
# hand-authored, clinician-validated distractor library, not something to
# improvise here. `hard` is currently "harder to extract from", and becomes
# "harder to reason about" once HC-51 lands and plugs in via `distractors=`.
_FILLER: tuple[str, ...] = (
    "The visit was a routine follow-up scheduled several months earlier.",
    "Records from an outside clinic were requested but had not arrived at the time of the visit.",
    "The patient arrived on time and was seen after a short wait.",
    "Vital signs were repeated by a second staff member before the encounter ended.",
    "A follow-up appointment was arranged before discharge from clinic.",
    "The patient reported no difficulty attending appointments.",
)


def _identity(profile: Mapping[str, Any]) -> str:
    """Stable identity for a profile: SEQN/case_id when present, else the whole row."""
    return str(profile.get("SEQN") or profile.get("case_id") or json.dumps(
        {k: v for k, v in sorted(profile.items())}, sort_keys=True, default=str
    ))


def _rng(profile: Mapping[str, Any], level: str, seed: int) -> random.Random:
    """Stable RNG: same (profile identity, level, seed) -> same stream, any process."""
    digest = hashlib.sha256(f"{_identity(profile)}|{level}|{seed}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _case_rng(profile: Mapping[str, Any], seed: int) -> random.Random:
    """Level-independent RNG for facts that belong to the *patient*, not the telling.

    Drug choice uses this. Seeding it off the level too would give one patient
    ramipril in the simple vignette and lisinopril in the hard one -- harmless to
    the label (both classify to `acei`) but incoherent to any human reading two
    levels of the same case side by side, which is exactly what the 20-vignette
    facts-only spot-check does.
    """
    digest = hashlib.sha256(f"{_identity(profile)}|case|{seed}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _get(profile: Mapping[str, Any], key: str) -> Any:
    """Read a profile field, normalizing '' and NaN to None."""
    v = profile.get(key)
    if v is None or v == "":
        return None
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def _listy(value: Any) -> list[str]:
    """med_classes / contraindications arrive as a list or a JSON string (CSV round-trip)."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return [str(v) for v in value]


def _bool(value: Any) -> bool | None:
    """Three-valued read, matching the engine's `_tri`: unknown stays unknown."""
    if isinstance(value, bool):
        return value
    if value in ("True", "true"):
        return True
    if value in ("False", "false"):
        return False
    return None


def _join(items: list[str]) -> str:
    """Grammatical list join: 'a', 'a and b', 'a, b, and c'."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


# --------------------------------------------------------------------------
# Fact sections. Each takes (profile, rng, case_rng) and returns
# (label, simple_line, prose_sentences).
# --------------------------------------------------------------------------
def display_bp(value: float | None) -> int | None:
    """Floor a BP to a whole mmHg for display, which is provably stage-preserving.

    NHANES BP is a mean of up to 3 readings, so profiles carry values like
    131.667 -- a number no clinician ever charts, and a tell that the text is
    generated. It has to be shown as an integer.

    Rounding would be a correctness bug, not a cosmetic choice: 129.6 rounds to
    130 and crosses the Stage-1 threshold, so the vignette would show a BP one
    stage above the hidden label computed from 129.6, and a model reading the
    vignette correctly would be scored wrong. Flooring cannot do this. Every
    staging threshold in `vocab.BP_THRESHOLDS` is an integer, and no integer lies
    in the half-open interval (floor(v), v] -- any such integer would have to be
    strictly between floor(v) and floor(v)+1. So floor(v) and v always fall on
    the same side of every threshold. Pinned by
    `test_rendered_bp_stages_identically_to_profile_bp`.

    Handoff to HC-70: extraction scoring must compare a model's extracted SBP to
    this displayed value, not to the raw profile float, or every case with a
    fractional mean counts as an extraction miss.
    """
    if value is None:
        return None
    try:
        return int(float(value) // 1)  # float() so a CSV-string BP works too
    except (TypeError, ValueError):
        return None


def _bp_facts(profile, rng, case_rng) -> tuple[str, str, list[str]]:
    sbp, dbp = display_bp(_get(profile, "sbp")), display_bp(_get(profile, "dbp"))
    n = _get(profile, "bp_n_readings")
    context = _get(profile, "bp_context") or "chronic"

    where = {
        "chronic": "averaged across outpatient clinic visits over the past year",
        "office": "recorded at today's clinic visit",
        # Acute context is rendered honestly: the engine abstains on it, and the
        # model must have the same chance to notice. Softening it would make an
        # appropriate abstention look like a model failure.
        "admission": "recorded on arrival to the emergency department during an acute illness",
    }[context]

    reading = f"{num(sbp)}/{num(dbp)} mmHg" if sbp is not None else "not recorded"
    count = f" from {num(n)} readings" if n is not None else ""

    simple = f"Blood pressure: {reading}{count}, {where}."
    prose = [f"Blood pressure was {reading}{count}, {where}."]
    return "blood pressure", simple, prose


def _med_facts(profile, rng, case_rng) -> tuple[str, str, list[str]]:
    on_meds = _bool(_get(profile, "on_bp_meds"))
    classes = _listy(_get(profile, "med_classes"))
    subj, _obj, poss = pronouns(_get(profile, "sex"))

    if classes:
        # case_rng, not rng: the prescription is a property of the patient and must
        # be identical across all three levels of the same case.
        drugs = [phrasing.exemplar_for(c, case_rng) for c in sorted(classes)]
        named = _join([f"{d} {dose} daily" for d, dose in drugs])
        simple = f"Current medications: {named}."
        prose = [f"{subj.capitalize()} takes {named}."]
    elif on_meds is True:
        # Known treated but no class recorded: say exactly that, invent nothing.
        simple = "Current medications: taking prescribed blood pressure medication; agents not recorded."
        prose = [f"{subj.capitalize()} takes prescription medication for blood pressure, "
                 "though the specific agents are not documented."]
    elif on_meds is False:
        simple = "Current medications: none for blood pressure."
        prose = [f"{subj.capitalize()} takes no medication for blood pressure."]
    else:
        # Unknown med status drives the engine to ABSTAIN. Render the gap as a
        # gap so an abstaining model is scored as correct, not as evasive.
        simple = "Current medications: not documented."
        prose = ["Whether the patient takes any medication for blood pressure is not documented "
                 "in the available record."]
    return "medications", simple, prose


def _history_facts(profile, rng, case_rng) -> tuple[str, str, list[str]]:
    """History section.

    Two buckets, because they are not grammatically interchangeable: `conditions`
    are noun phrases that read correctly after "history includes ...", while
    `statements` are full sentences (smoking status, pregnancy, the angioedema
    event). Folding the second kind into the first produced "her history includes
    ... does not smoke".
    """
    subj, _obj, poss = pronouns(_get(profile, "sex"))
    conditions: list[str] = []
    statements: list[str] = []

    if _bool(_get(profile, "diabetes")) is True:
        conditions.append("type 2 diabetes")
    if _bool(_get(profile, "clinical_cvd")) is True:
        conditions.append("a previous myocardial infarction")
    bmi = _get(profile, "bmi")
    if bmi is not None:
        conditions.append(f"a body mass index of {dec(bmi)} kg/m²")

    if _bool(_get(profile, "told_hypertension")) is True:
        statements.append(f"{subj.capitalize()} recalls being told at a previous visit that "
                          f"{poss} blood pressure was high.")

    for flag in _listy(_get(profile, "contraindications")):
        if flag == "pregnancy":
            statements.append(f"{subj.capitalize()} is currently pregnant, in the second trimester.")
        elif flag == "angioedema_hx":
            # The event, not its interpretation. "Lip and tongue swelling after
            # starting a drug" is a fact; "contraindication to ACEI" is the answer.
            statements.append(
                f"Two years ago {subj} developed lip and tongue swelling requiring emergency "
                f"care a few days after starting a new prescription, and that drug was stopped.")
        # 'hyperkalemia' is deliberately not rendered here: it reaches the model as
        # the raw potassium value in the lab section, which is the fact to read.

    smoker = _bool(_get(profile, "current_smoker"))
    if smoker is True:
        statements.append(f"{subj.capitalize()} currently smokes.")
    elif smoker is False:
        statements.append(f"{subj.capitalize()} does not smoke.")

    if _bool(_get(profile, "statin_use")) is True:
        statements.append(f"{subj.capitalize()} also takes a statin for cholesterol.")

    if conditions:
        lead = f"{poss.capitalize()} history includes {_join(conditions)}."
        simple_hx = f"Past medical history: {_join(conditions)}."
    elif statements:
        lead, simple_hx = "", "Past medical history:"
    else:
        return "history", "Past medical history: nothing documented.", [
            "No past medical history is documented."]

    prose = ([lead] if lead else []) + statements
    simple = " ".join([simple_hx] + statements) if statements else simple_hx
    return "history", simple, prose


def _lab_facts(profile, rng, case_rng) -> tuple[str, str, list[str]]:
    rows: list[str] = []
    for key, label, places, unit in (
        ("creatinine", "creatinine", 2, " mg/dL"),
        ("egfr", "estimated GFR", 0, " mL/min/1.73m²"),
        ("potassium", "potassium", 1, " mmol/L"),
        ("uacr", "urine albumin-to-creatinine ratio", 1, " mg/g"),
        ("hba1c", "HbA1c", 1, "%"),          # no space: "6.2%", not "6.2 %"
        ("total_chol", "total cholesterol", 0, " mg/dL"),
        ("hdl", "HDL cholesterol", 0, " mg/dL"),
    ):
        value = _get(profile, key)
        if value is not None:
            shown = num(value) if places == 0 else dec(value, places)
            rows.append(f"{label} {shown}{unit}")

    if not rows:
        return "laboratory results", "Laboratory results: none available.", [
            "No laboratory results are available."]

    simple = "Laboratory results: " + "; ".join(rows) + "."
    prose = [f"Laboratory testing showed {_join(rows)}."]
    return "laboratory results", simple, prose


_SECTIONS = (_bp_facts, _med_facts, _history_facts, _lab_facts)


def render(profile: Mapping[str, Any], level: Level = "moderate", seed: int = 0) -> str:
    """Render one PatientProfile as a facts-only clinical vignette.

    Deterministic: identical (profile, level, seed) always yields identical text.
    Self-checks against `leakage.scan` before returning, so a template edit that
    introduces a label-bearing token fails at render time rather than silently
    poisoning a benchmark split.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")

    rng = _rng(profile, level, seed)
    case_rng = _case_rng(profile, seed)
    opening = f"The patient is {person_noun(_get(profile, 'age'), _get(profile, 'sex'))}."
    sections = [fn(profile, rng, case_rng) for fn in _SECTIONS]

    if level == "simple":
        body = [opening] + [simple for _label, simple, _prose in sections]
        text = "\n".join(body)

    elif level == "moderate":
        parts = [opening]
        for _label, _simple, prose in sections:
            parts.extend(prose)
        text = " ".join(parts)

    else:  # hard
        # Seeded section order + inert filler: the same facts, harder to locate.
        blocks = [prose for _label, _simple, prose in sections]
        order = list(range(len(blocks)))
        rng.shuffle(order)
        filler = list(_FILLER)
        rng.shuffle(filler)

        paragraphs = [
            f"{opening} {filler[0]}",
            " ".join(blocks[order[0]] + blocks[order[1]] + [filler[1]]),
            " ".join([filler[2]] + blocks[order[2]] + blocks[order[3]]),
        ]
        text = "\n\n".join(paragraphs)

    leakage.assert_clean(text, where=f"rendered vignette (level={level})")
    return text

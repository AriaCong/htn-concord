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
import vocab
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


def _int_or_none(value: Any) -> int | None:
    """Read a count that may arrive as an int, a float, or a CSV string."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


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


# --------------------------------------------------------------------------
# HC-101 -- the `hard` extraction burden (kill criterion K2)
#
# The HC-80 pilot found the ladder inert: extraction F1 was 0.918 at every
# level, to three decimals, with identical per-field counts. Shuffling
# paragraphs and interleaving visit logistics costs a reader nothing while
# every fact stays in the same sentence with the same label and units.
#
# Both mechanisms below target fields the evaluator actually scores, and
# neither removes information -- they change what it costs to recover it,
# which is the line the module docstring draws.
# --------------------------------------------------------------------------

#: How far individual readings sit from their mean, in mmHg. Wide enough that
#: taking any single reading is a wrong answer, narrow enough to stay clinical.
_SBP_SPREAD = (2, 9)
_DBP_SPREAD = (2, 6)

#: How long ago the earlier potassium was drawn. Seeded, never "recently" --
#: the decoy has to be unmistakably older than the current value, or it stops
#: being a careless-reader trap and becomes a genuine ambiguity.
_DECOY_WHEN = ("at a check three months ago", "when last checked in the spring",
               "on a panel drawn six months ago", "at a review last autumn")


def _zero_sum_offsets(n: int, rng: random.Random, lo: int, hi: int) -> list[int]:
    """`n` non-zero integer offsets summing to zero, each `lo <= |o| <= hi`.

    Summing to zero is what makes the readings average *exactly* to the value
    the evaluator compares against. None may be zero: an offset of zero would
    put the mean itself on the page as one of the readings, handing back the
    number the mechanism exists to withhold.
    """
    if n <= 1:
        return [0]
    if n == 2:
        step = rng.randint(lo, hi)
        return [step, -step] if rng.random() < 0.5 else [-step, step]
    if n == 3:
        pool = [(a, b, -(a + b))
                for a in range(-hi, hi + 1) if lo <= abs(a) <= hi
                for b in range(-hi, hi + 1) if lo <= abs(b) <= hi
                and lo <= abs(a + b) <= hi]
        return list(rng.choice(pool))
    # n > 3 does not occur in the NHANES corpus (max 3); handled rather than
    # assumed away, by pairing offsets and dropping any leftover to a pair.
    offsets: list[int] = []
    while len(offsets) + 2 <= n:
        step = rng.randint(lo, hi)
        offsets += [step, -step]
    if len(offsets) < n:
        step = rng.randint(lo, hi)
        offsets += [step, step, -2 * step][:n - len(offsets)]
    return offsets


def bp_readings(sbp: int, dbp: int, n: int,
                rng: random.Random) -> list[tuple[int, int]]:
    """`n` integer (systolic, diastolic) readings whose means are exactly `sbp`/`dbp`.

    Exactness is a correctness requirement, not a nicety. `evaluator.metrics`
    scores extraction against `display_bp(profile.sbp)` -- the floored value the
    vignette showed. Readings that averaged to anything else would score a model
    that read and averaged perfectly as an extraction miss, and the
    level-over-level drop would measure our arithmetic rather than its reading.
    Integer readings summing to `n * displayed` make the mean exact under any
    rounding convention the model might apply. Pinned by
    `test_hard_readings_average_exactly_to_the_displayed_value`.

    Spreads are narrowed, never the sum, so the offsets still cancel: clamping
    an individual reading would shift the mean off the label.
    """
    pulse = sbp - dbp
    s_hi = max(_SBP_SPREAD[0], min(_SBP_SPREAD[1], sbp - vocab.SBP_MIN,
                                   vocab.SBP_MAX - sbp, (pulse - 1) // 2))
    d_hi = max(_DBP_SPREAD[0], min(_DBP_SPREAD[1], dbp - vocab.DBP_MIN,
                                   vocab.DBP_MAX - dbp, (pulse - 1) // 2))
    s_off = _zero_sum_offsets(n, rng, min(_SBP_SPREAD[0], s_hi), s_hi)
    d_off = _zero_sum_offsets(n, rng, min(_DBP_SPREAD[0], d_hi), d_hi)
    return [(sbp + s, dbp + d) for s, d in zip(s_off, d_off)]


def potassium_decoy(value: float | None, rng: random.Random) -> float | None:
    """An earlier potassium, on the same side of the one threshold it drives.

    Potassium reaches a label by exactly one route --
    `k >= vocab.K_HYPERKALEMIA -> "hyperkalemia"` in `pipelines/common/derive.py`
    -- so a decoy that stays on the current value's side of that single
    threshold is *provably* decision-inert: no reading of it changes the flag,
    and the engine never sees the vignette at all.

    eGFR was considered for the same treatment and rejected. It enters PREVENT
    as two continuous spline terms (`egfr_lt60`, `egfr_ge60`), so *any*
    alternative value moves `prevent_10yr` and can cross PREVENT_STAGE1_TREAT.
    "Stays in the same CKD band" would not have been enough, and proving
    inertness per case would mean importing the engine into the renderer, which
    the facts/labels separation forbids. Conservative call; flagged for HC-49.

    The excursion is bounded to 1.2 mmol/L so the earlier value reads as the
    same patient's chemistry rather than a different illness.
    """
    if value is None:
        return None
    current = float(value)
    if current >= vocab.K_HYPERKALEMIA:
        lo, hi = vocab.K_HYPERKALEMIA, 6.8
    else:
        lo, hi = 2.8, vocab.K_HYPERKALEMIA - 0.1
    pool = [round(x * 0.1, 1) for x in range(round(lo * 10), round(hi * 10) + 1)]
    pool = [k for k in pool if 0.3 <= abs(k - current) <= 1.2]
    return rng.choice(pool) if pool else None


def _bp_facts(profile, rng, case_rng, level) -> tuple[str, str, list[str]]:
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
    where_each = {
        "chronic": "at outpatient clinic visits over the past year",
        "office": "at today's clinic visit",
        "admission": "on arrival to the emergency department during an acute illness",
    }[context]

    reading = f"{num(sbp)}/{num(dbp)} mmHg" if sbp is not None else "not recorded"
    count = f" from {num(n)} readings" if n is not None else ""

    # `hard` hands over the readings and makes the reader do the averaging.
    # HC-23 settled that the *mean* is the correct summary, and `display_bp`
    # floors it; the readings are built to average to exactly that floored
    # value, so a model that averages correctly matches what the evaluator
    # compares against. Falls back to the averaged form whenever there is
    # nothing to average (one reading, or a count the profile never recorded).
    n_readings = _int_or_none(n)   # CSV round-trip delivers this as "3.0"
    if level == "hard" and sbp is not None and dbp is not None \
            and n_readings is not None and n_readings >= 2:
        readings = bp_readings(sbp, dbp, n_readings, rng)
        shown = _join([f"{s}/{d}" for s, d in readings])
        listed = (f"Blood pressure was measured {num(n)} times {where_each}: "
                  f"{shown} mmHg.")
        return "blood pressure", listed, [listed]

    simple = f"Blood pressure: {reading}{count}, {where}."
    prose = [f"Blood pressure was {reading}{count}, {where}."]
    return "blood pressure", simple, prose


def _med_facts(profile, rng, case_rng, level) -> tuple[str, str, list[str]]:
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


def _history_facts(profile, rng, case_rng, level) -> tuple[str, str, list[str]]:
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


def _lab_facts(profile, rng, case_rng, level) -> tuple[str, str, list[str]]:
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
        if value is None:
            continue
        shown = num(value) if places == 0 else dec(value, places)
        # `hard` sets an older potassium beside the current one. The current
        # value is always the one labelled "today", so a careful reader is
        # never misled and the value stays recoverable; a careless one takes
        # the wrong number. Provably decision-inert -- see `potassium_decoy`.
        if key == "potassium" and level == "hard":
            decoy = potassium_decoy(value, rng)
            if decoy is not None:
                direction = "down from" if decoy > float(value) else "up from"
                rows.append(f"{label} {shown}{unit} today, {direction} "
                            f"{dec(decoy, 1)}{unit} {rng.choice(_DECOY_WHEN)}")
                continue
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
    sections = [fn(profile, rng, case_rng, level) for fn in _SECTIONS]

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

"""Surface forms for the vignette renderer — drug names, pronouns, value formatting.

Kept separate from `render.py` so the *what facts* logic and the *how it reads*
vocabulary can be reviewed independently.

The class->drug exemplar table is the one place this module invents detail the
structured profile does not carry: a PatientProfile records `med_classes`
(["acei"]), never the actual prescription. Naming a drug is forced by the
leakage rule -- a vignette may not say "an ACE inhibitor" (that is the
recommendation vocabulary), so it has to say "lisinopril". Every exemplar is
chosen so `vocab.classify_drug(exemplar) == [that class]` exactly, which makes
the substitution lossless and is pinned by a round-trip test.
"""
from __future__ import annotations

import vocab

# Exemplars per engine class. Each must classify back to exactly its own class --
# no combination pills here, or the round-trip becomes many-to-one.
CLASS_EXEMPLARS: dict[str, tuple[tuple[str, str], ...]] = {
    # class: ((drug, typical daily dose), ...)
    "thiazide":      (("hydrochlorothiazide", "25 mg"), ("chlorthalidone", "12.5 mg"),
                      ("indapamide", "1.25 mg")),
    "acei":          (("lisinopril", "10 mg"), ("enalapril", "10 mg"),
                      ("ramipril", "5 mg")),
    "arb":           (("losartan", "50 mg"), ("valsartan", "80 mg"),
                      ("olmesartan", "20 mg")),
    "dhp_ccb":       (("amlodipine", "5 mg"), ("felodipine", "5 mg"),
                      ("nifedipine", "30 mg")),
    "nondhp_ccb":    (("diltiazem", "180 mg"), ("verapamil", "120 mg")),
    "beta_blocker":  (("metoprolol", "50 mg"), ("atenolol", "50 mg"),
                      ("carvedilol", "12.5 mg")),
    "loop_diuretic": (("furosemide", "20 mg"), ("torsemide", "10 mg")),
    "mra":           (("spironolactone", "25 mg"), ("eplerenone", "25 mg")),
    "alpha_blocker": (("doxazosin", "2 mg"), ("terazosin", "2 mg")),
}


def exemplar_for(med_class: str, rng) -> tuple[str, str]:
    """Pick a (drug, dose) for a class. Deterministic given the caller's rng."""
    options = CLASS_EXEMPLARS.get(med_class)
    if not options:
        # An unmapped class must not silently vanish from the vignette -- that
        # would drop a fact the label depends on. Surface it loudly instead.
        raise KeyError(f"no drug exemplar for med class {med_class!r}; add one to CLASS_EXEMPLARS")
    return options[rng.randrange(len(options))]


def assert_exemplars_round_trip() -> None:
    """Every exemplar classifies back to exactly its own class (import-time contract)."""
    for cls, options in CLASS_EXEMPLARS.items():
        for drug, _dose in options:
            got = vocab.classify_drug(drug)
            if got != [cls]:
                raise AssertionError(f"{drug!r} classifies to {got}, expected [{cls!r}]")


def pronouns(sex: str | None) -> tuple[str, str, str]:
    """(subject, object, possessive). Unknown sex renders as singular they."""
    if sex == "female":
        return "she", "her", "her"
    if sex == "male":
        return "he", "him", "his"
    return "they", "them", "their"


def article_for_age(age_text: str) -> str:
    """'a' vs 'an' for a spoken age: an 8-, an 11-, an 18-, an 80-something."""
    return "an" if age_text.startswith(("8", "11", "18")) else "a"


def person_noun(age: float | None, sex: str | None) -> str:
    """'a 66-year-old woman' / 'an 18-year-old man' / 'an adult of unrecorded age'."""
    noun = {"female": "woman", "male": "man"}.get(sex or "", "adult")
    if age is None:
        return f"an adult {noun}" if noun != "adult" else "an adult of unrecorded age"
    age_text = num(age)
    return f"{article_for_age(age_text)} {age_text}-year-old {noun}"


def num(value: float | None) -> str:
    """Render a number without a trailing '.0' (ages, BP) but keep real decimals."""
    if value is None:
        return "unrecorded"
    f = float(value)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else f"{f:g}"


def dec(value: float | None, places: int = 1) -> str:
    """Fixed-decimal lab value (creatinine 0.92, potassium 4.0)."""
    return "unrecorded" if value is None else f"{float(value):.{places}f}"


# Enforced on import: a bad exemplar is a silent leakage/fidelity bug otherwise.
assert_exemplars_round_trip()

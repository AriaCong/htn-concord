"""ICD-9/10 code-set predicates for MIMIC comorbidity/contraindication counting.

Synthetic codes only -- no credentialed MIMIC rows (HC-56).
"""
import pytest

from pipelines.mimic import icd_sets


@pytest.mark.parametrize("code,version,flag", [
    ("E119",   10, "diabetes"),        # T2DM without complications
    ("E1065",  10, "diabetes"),        # T1DM with hyperglycemia
    ("25000",   9, "diabetes"),
    ("I2510",  10, "clinical_cvd"),    # atherosclerotic heart disease
    ("I509",   10, "clinical_cvd"),    # heart failure
    ("I639",   10, "clinical_cvd"),    # cerebral infarction
    ("41401",   9, "clinical_cvd"),
    ("4280",    9, "clinical_cvd"),
    ("F1721",  10, "current_smoker"),  # nicotine dependence, cigarettes
    ("Z87891", 10, "current_smoker"),  # personal history of nicotine dependence
    ("3051",    9, "current_smoker"),
    ("T783XXA", 10, "angioedema_hx"),  # angioneurotic edema
    ("9951",    9, "angioedema_hx"),
    ("O139",   10, "pregnancy"),       # gestational hypertension
    ("Z3400",  10, "pregnancy"),       # supervision of normal pregnancy
])
def test_positive_classifications(code, version, flag):
    assert flag in icd_sets.classify(code, version)


@pytest.mark.parametrize("code,version", [
    ("I10",   10),   # essential HTN
    ("I110",  10),   # hypertensive heart disease
    ("4019",   9),
    ("4011",   9),
    ("40201",  9),
])
def test_hypertension_anchor_is_never_a_comorbidity_flag(code, version):
    """The anchor selects the encounter; it must never generate a label.

    If an anchor code could set a flag, the benchmark would partly be a
    coding-lookup test rather than a staging-and-decision test.
    """
    assert icd_sets.classify(code, version) == frozenset()


@pytest.mark.parametrize("code,version", [
    ("I15",   10),   # secondary HTN -- out of scope entirely
    ("I150",  10),
    ("405",    9),
    ("40501",  9),
])
def test_secondary_hypertension_is_never_a_flag_either(code, version):
    """Secondary HTN is excluded from the cohort (HC-18); it must not sneak in
    through a comorbidity flag on a patient selected some other way."""
    assert icd_sets.classify(code, version) == frozenset()


def test_unknown_code_returns_empty_set():
    assert icd_sets.classify("ZZZZZ", 10) == frozenset()
    assert icd_sets.classify(None, 10) == frozenset()
    assert icd_sets.classify("", 10) == frozenset()


def test_unknown_icd_version_returns_empty_rather_than_guessing():
    """A version we cannot read is missing data, not ICD-10 by default."""
    assert icd_sets.classify("E119", 11) == frozenset()
    assert icd_sets.classify("E119", None) == frozenset()


def test_dots_and_case_are_normalised():
    assert "diabetes" in icd_sets.classify("e11.9", 10)
    assert "clinical_cvd" in icd_sets.classify("I25.10", 10)
    assert "diabetes" in icd_sets.classify(" 250.00 ", 9)


def test_a_code_can_carry_more_than_one_flag():
    """O10.x is hypertension complicating pregnancy: pregnancy, and nothing
    hypertensive, because the anchor never generates a label."""
    assert icd_sets.classify("O10011", 10) == frozenset({"pregnancy"})


@pytest.mark.parametrize("code", ["63000", "64200", "65000", "66900", "67900"])
def test_icd9_pregnancy_covers_the_whole_obstetric_chapter(code):
    """630-679 all flag. Pregnancy is a scope gate that makes the engine abstain,
    so over-flagging costs a benchmark item while under-flagging ships an unsafe
    INITIATE label -- the HC-24 defect. Deliberately broad; flagged for HC-49."""
    assert "pregnancy" in icd_sets.classify(code, 9)


@pytest.mark.parametrize("code", ["62000", "68000", "70000"])
def test_icd9_pregnancy_stops_at_the_chapter_boundary(code):
    """Broad is not unbounded: codes outside 630-679 must not flag."""
    assert "pregnancy" not in icd_sets.classify(code, 9)


def test_flags_tuple_is_the_full_vocabulary():
    assert set(icd_sets.FLAGS) == {
        "diabetes", "clinical_cvd", "current_smoker",
        "angioedema_hx", "pregnancy",
    }


def test_contraindication_flags_are_a_subset_of_the_engine_vocabulary():
    """angioedema_hx and pregnancy feed contraindications, which the schema and
    the engine share through vocab. A name drift here would silently drop a
    safety flag at profile-build time."""
    import vocab
    assert {"angioedema_hx", "pregnancy"} <= set(vocab.CONTRAINDICATION_FLAGS)

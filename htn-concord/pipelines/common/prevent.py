"""AHA PREVENT — 10-year total-CVD risk (base model). IMPLEMENTED & VALIDATED.

Reference: Khan SS et al., "Development and Validation of the American Heart
Association's PREVENT Equations," Circulation 2024;149:430-449. Coefficients and the
feature transformations are transcribed verbatim from Supplemental Table S12A
("Table S12A Base 10yr"). Validated: reproduces that table's worked example
(Age 50, TC 200, HDL 45, SBP 160, DM, antiHTN, eGFR 90) -> Women 14.684%,
Men 16.317% (see tests/test_prevent.py::test_published_example_table_s12a).

Returns ``None`` (-> NaN in the profile) when inputs are incomplete or age is
outside 30-79 (the validated range). Callers MUST treat None as "abstain / no
PREVENT trigger", never as low risk.

Base model predictors (NOT the enhanced model — UACR/HbA1c/social-deprivation are
excluded by design; BMI is used only in the Heart Failure model, not total CVD):
age, non-HDL cholesterol, HDL cholesterol, systolic BP (treated/untreated splines),
diabetes, current smoking, eGFR (splines), antihypertensive use, statin use, and
age interaction terms.
"""
from __future__ import annotations

from dataclasses import dataclass

# mg/dL -> mmol/L for cholesterol. The paper (Table S12A) uses exactly 0.02586.
_CHOL_MGDL_TO_MMOL = 0.02586

AGE_MIN, AGE_MAX = 30, 79  # PREVENT is validated only for ages 30-79.


@dataclass(frozen=True)
class PreventInputs:
    age: float
    sex: str                 # "male" | "female"
    total_chol_mgdl: float
    hdl_mgdl: float
    sbp: float               # mmHg
    on_bp_meds: bool
    diabetes: bool
    current_smoker: bool
    egfr: float              # mL/min/1.73m^2
    statin: bool

    def complete(self) -> bool:
        vals = [self.age, self.total_chol_mgdl, self.hdl_mgdl, self.sbp, self.egfr]
        return (
            self.sex in ("male", "female")
            and all(v is not None for v in vals)
            and not any(_is_nan(v) for v in vals)
            and self.on_bp_meds is not None
            and self.diabetes is not None
            and self.current_smoker is not None
            and self.statin is not None
        )


def _is_nan(v) -> bool:
    try:
        return v != v  # noqa: PLR0124 - NaN check without importing math for scalars
    except Exception:
        return False


# Order of transformed features. COEFFICIENTS (per sex) must supply one value for
# each of these keys plus "intercept".
FEATURE_ORDER = (
    "cage",                 # (age - 55) / 10
    "non_hdl",              # non-HDL chol (mmol/L) - 3.5
    "hdl",                  # (HDL (mmol/L) - 1.3) / 0.3
    "sbp_lt110",            # (min(SBP,110) - 110) / 20
    "sbp_ge110",            # (max(SBP,110) - 130) / 20
    "diabetes",             # 0/1
    "smoker",               # 0/1
    "egfr_lt60",            # (min(eGFR,60) - 60) / -15
    "egfr_ge60",            # (max(eGFR,60) - 90) / -15
    "on_bp_meds",           # 0/1
    "statin",               # 0/1
    "sbp_ge110_x_bpmed",    # treated-BP interaction
    "non_hdl_x_statin",     # statin interaction
    # age interactions
    "cage_x_non_hdl", "cage_x_hdl", "cage_x_sbp_ge110",
    "cage_x_diabetes", "cage_x_smoker", "cage_x_egfr_lt60",
)


def _features(inp: PreventInputs) -> dict[str, float]:
    cage = (inp.age - 55.0) / 10.0
    non_hdl = (inp.total_chol_mgdl - inp.hdl_mgdl) * _CHOL_MGDL_TO_MMOL - 3.5
    hdl = (inp.hdl_mgdl * _CHOL_MGDL_TO_MMOL - 1.3) / 0.3
    sbp_lt110 = (min(inp.sbp, 110.0) - 110.0) / 20.0
    sbp_ge110 = (max(inp.sbp, 110.0) - 130.0) / 20.0
    egfr_lt60 = (min(inp.egfr, 60.0) - 60.0) / -15.0
    egfr_ge60 = (max(inp.egfr, 60.0) - 90.0) / -15.0
    dia = 1.0 if inp.diabetes else 0.0
    smk = 1.0 if inp.current_smoker else 0.0
    bpmed = 1.0 if inp.on_bp_meds else 0.0
    statin = 1.0 if inp.statin else 0.0
    return {
        "cage": cage, "non_hdl": non_hdl, "hdl": hdl,
        "sbp_lt110": sbp_lt110, "sbp_ge110": sbp_ge110,
        "diabetes": dia, "smoker": smk,
        "egfr_lt60": egfr_lt60, "egfr_ge60": egfr_ge60,
        "on_bp_meds": bpmed, "statin": statin,
        "sbp_ge110_x_bpmed": sbp_ge110 * bpmed,
        "non_hdl_x_statin": non_hdl * statin,
        "cage_x_non_hdl": cage * non_hdl, "cage_x_hdl": cage * hdl,
        "cage_x_sbp_ge110": cage * sbp_ge110, "cage_x_diabetes": cage * dia,
        "cage_x_smoker": cage * smk, "cage_x_egfr_lt60": cage * egfr_lt60,
    }


# ---------------------------------------------------------------------------
# COEFFICIENTS — base 10-year TOTAL CVD model, transcribed verbatim from Khan 2024
# Supplemental Table S12A ("Table S12A Base 10yr", Women/Men columns). Verified: these
# reproduce the table's worked example (Age 50, TC 200, HDL 45, SBP 160, DM=1,
# smoker=0, eGFR 90, antiHTN=1, statin=0) -> Women 14.684%, Men 16.317%.
# ---------------------------------------------------------------------------
COEFFICIENTS_FILLED = True
COEFFICIENTS: dict[str, dict[str, float]] = {
    "female": {
        "cage": 0.7939329, "non_hdl": 0.0305239, "hdl": -0.1606857,
        "sbp_lt110": -0.2394003, "sbp_ge110": 0.3600781,
        "diabetes": 0.8667604, "smoker": 0.5360739,
        "egfr_lt60": 0.6045917, "egfr_ge60": 0.0433769,
        "on_bp_meds": 0.3151672, "statin": -0.1477655,
        "sbp_ge110_x_bpmed": -0.0663612, "non_hdl_x_statin": 0.1197879,
        "cage_x_non_hdl": -0.0819715, "cage_x_hdl": 0.0306769,
        "cage_x_sbp_ge110": -0.0946348, "cage_x_diabetes": -0.27057,
        "cage_x_smoker": -0.078715, "cage_x_egfr_lt60": -0.1637806,
        "intercept": -3.307728,
    },
    "male": {
        "cage": 0.7688528, "non_hdl": 0.0736174, "hdl": -0.0954431,
        "sbp_lt110": -0.4347345, "sbp_ge110": 0.3362658,
        "diabetes": 0.7692857, "smoker": 0.4386871,
        "egfr_lt60": 0.5378979, "egfr_ge60": 0.0164827,
        "on_bp_meds": 0.288879, "statin": -0.1337349,
        "sbp_ge110_x_bpmed": -0.0475924, "non_hdl_x_statin": 0.150273,
        "cage_x_non_hdl": -0.0517874, "cage_x_hdl": 0.0191169,
        "cage_x_sbp_ge110": -0.1049477, "cage_x_diabetes": -0.2251948,
        "cage_x_smoker": -0.0895067, "cage_x_egfr_lt60": -0.1543702,
        "intercept": -3.031168,
    },
}


def _risk_from_linear_predictor(lp: float) -> float:
    """PREVENT logistic link: risk = 100 / (1 + e^-lp).

    Verified against the Khan 2024 Table S12A worked example -- see
    tests/test_prevent.py::test_published_example_table_s12a (W 14.684%, M 16.317%).
    """
    import math
    return 100.0 / (1.0 + math.exp(-lp))


def prevent_10yr_cvd_risk(inp: PreventInputs) -> float | None:
    """10-year total-CVD risk in percent, or None when not computable.

    None is returned when: sex/inputs missing, age outside 30-79, or coefficients
    are not yet filled. Callers MUST treat None as "abstain / no PREVENT trigger",
    never as low risk.
    """
    if not inp.complete():
        return None
    if not (AGE_MIN <= inp.age <= AGE_MAX):
        return None
    if not COEFFICIENTS_FILLED:
        return None
    coef = COEFFICIENTS[inp.sex]
    feats = _features(inp)
    lp = coef["intercept"] + sum(coef[k] * feats[k] for k in FEATURE_ORDER)
    return _risk_from_linear_predictor(lp)

"""The HC-80 kill criteria, as code.

`docs/HTN-Concord_Pilot_Kill_Criteria.md` is the signed document; this module is
the same six criteria written so they evaluate themselves. That is deliberate.
A gate whose thresholds live only in prose gets reinterpreted once the numbers
are on the screen — "near ceiling" becomes whatever we saw. Here the thresholds
are constants fixed before the first call, and the verdict is a pure function of
the summary.

Signed by Aria on 2026-09-20, before any pilot call was made, including the
framing that this pilot is a **smoke test for gross failure**: at 20 patients the
95% CI half-width is roughly ±18 pp, so "no kill" means "no gross failure
detected", never "the benchmark discriminates". The gate is asymmetric on
purpose — a kill verdict is strong evidence, a pass is weak evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Thresholds. Fixed 2026-09-20 before any result was seen. Changing one after a
# pilot call has been made is a protocol deviation and goes in the document's
# change log with its reason, not into this file silently.
CEILING = 0.90                  # K1
LADDER_MIN_SPREAD = 0.05        # K2
MODEL_MIN_SEPARATION = 0.05     # K3
FLOOR_MARGIN = 0.05             # K4
MAX_MALFORMED_RATE = 0.05       # K5
MAX_REFUSAL_RATE = 0.02         # K5
MAX_TRUNCATION_RATE = 0.01      # K5
MAX_MEDIAN_REPLICATE_SD = 0.05  # K6


@dataclass(frozen=True)
class Criterion:
    name: str
    fired: bool
    statement: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KillVerdict:
    verdict: str                 # GO | GO-NARROWED | STOP | FIX-FIRST
    reason: str
    criteria: Sequence[Criterion]

    @property
    def fired(self) -> list[str]:
        return [c.name for c in self.criteria if c.fired]


def _cell(summary: Mapping[str, Any], model: str, level: str) -> Mapping[str, Any] | None:
    return summary["by_model_level"].get(f"{model}|{level}")


def _concordance(summary: Mapping[str, Any], model: str, level: str) -> float | None:
    cell = _cell(summary, model, level)
    return None if cell is None else cell.get("decision_concordance")


def evaluate_criteria(summary: Mapping[str, Any], *, models: Sequence[str],
                      levels: Sequence[str]) -> KillVerdict:
    """Apply K1..K6 to a pilot summary and return the pre-registered verdict."""
    criteria = [
        _k1_ceiling(summary, models, levels),
        _k2_flat_ladder(summary, models, levels),
        _k3_models_indistinguishable(summary, models, levels),
        _k4_floor(summary, models, levels),
        _k5_harness(summary),
        _k6_replicate_variance(summary),
    ]
    by_name = {c.name: c for c in criteria}

    # The verdict rule, in the order the signed document fixes it.
    if by_name["K5"].fired:
        return KillVerdict("FIX-FIRST",
                           "The harness is not usable, so K1-K4 are not read: "
                           "numbers from a broken instrument are not evidence.",
                           criteria)
    if by_name["K4"].fired:
        return KillVerdict("STOP",
                           "Nothing beats the majority-class baseline. This is a "
                           "broken instrument, not a hard benchmark.", criteria)
    if by_name["K1"].fired and by_name["K2"].fired:
        return KillVerdict("STOP",
                           "The corpus is at ceiling and the difficulty ladder is "
                           "flat: no later condition could demonstrate repair.",
                           criteria)
    if by_name["K3"].fired:
        return KillVerdict("STOP",
                           "The corpus does not separate the two models, so it is "
                           "not measuring capability and the replicates-across-"
                           "models bar cannot be met.", criteria)
    narrowed = [n for n in ("K1", "K2") if by_name[n].fired]
    if narrowed:
        return KillVerdict("GO-NARROWED",
                           f"{', '.join(narrowed)} fired alone: proceed, but report "
                           "the affected research question as unanswerable on this "
                           "corpus rather than quietly dropping it.", criteria)
    return KillVerdict("GO", "No kill criterion fired. Note this means no *gross* "
                             "failure was detected, not that the benchmark "
                             "discriminates.", criteria)


def _k1_ceiling(summary, models, levels) -> Criterion:
    values = {f"{m}|{l}": _concordance(summary, m, l) for m in models for l in levels}
    present = [v for v in values.values() if v is not None]
    fired = bool(present) and len(present) == len(values) and all(
        v >= CEILING for v in present)
    return Criterion("K1", fired,
                     f"Both models >= {CEILING:.0%} concordance at all three levels "
                     "-> no headroom for any later condition to demonstrate repair.",
                     values)


def _k2_flat_ladder(summary, models, levels) -> Criterion:
    """Pooled across models: is hard any harder than simple?"""
    def pooled(level: str, metric: str) -> float | None:
        cells = [_cell(summary, m, level) for m in models]
        vals = [c[metric] for c in cells if c and c.get(metric) is not None]
        return sum(vals) / len(vals) if vals else None

    evidence: dict[str, Any] = {}
    spreads = {}
    for metric in ("decision_concordance", "extraction_f1"):
        simple, hard = pooled("simple", metric), pooled("hard", metric)
        evidence[f"simple_{metric}"] = simple
        evidence[f"hard_{metric}"] = hard
        spreads[metric] = (None if simple is None or hard is None
                           else abs(simple - hard))
    evidence["spreads"] = spreads
    known = [s for s in spreads.values() if s is not None]
    fired = len(known) == len(spreads) and all(s < LADDER_MIN_SPREAD for s in known)
    return Criterion("K2", fired,
                     f"|simple - hard| < {LADDER_MIN_SPREAD:.0%} in both concordance "
                     "and extraction_f1 -> the levels are not creating the "
                     "extraction burden they were designed to create.", evidence)


def _k3_models_indistinguishable(summary, models, levels) -> Criterion:
    if len(models) < 2:
        return Criterion("K3", False,
                         "Not evaluable: the pilot ran fewer than two model arms, "
                         "so the question the pilot exists to answer is unanswered.",
                         {"models": list(models)})
    gaps = {}
    for level in levels:
        vals = [_concordance(summary, m, level) for m in models]
        gaps[level] = (None if any(v is None for v in vals)
                       else max(vals) - min(vals))
    known = [g for g in gaps.values() if g is not None]
    fired = len(known) == len(gaps) and all(g < MODEL_MIN_SEPARATION for g in known)
    return Criterion("K3", fired,
                     f"|frontier - open-weight| < {MODEL_MIN_SEPARATION:.0%} at every "
                     "level -> the corpus is not separating models.", gaps)


def _k4_floor(summary, models, levels) -> Criterion:
    evidence: dict[str, Any] = {}
    over_baseline = []
    for model in models:
        for level in levels:
            cell = _cell(summary, model, level)
            if cell is None or cell.get("decision_concordance") is None:
                over_baseline.append(None)
                continue
            margin = cell["decision_concordance"] - cell["majority_class_baseline"]
            evidence[f"{model}|{level}"] = {
                "concordance": cell["decision_concordance"],
                "majority_class_baseline": cell["majority_class_baseline"],
                "margin": margin,
            }
            over_baseline.append(margin)
    known = [m for m in over_baseline if m is not None]
    fired = (bool(known) and len(known) == len(over_baseline)
             and all(m <= FLOOR_MARGIN for m in known))
    return Criterion("K4", fired,
                     f"Every arm within {FLOOR_MARGIN:.0%} of the majority-class "
                     "baseline -> the task is broken, not hard.", evidence)


def _k5_harness(summary) -> Criterion:
    evidence = {}
    fired = False
    for model, counts in summary.get("harness", {}).items():
        evidence[model] = {
            "malformed_output_rate": counts.get("malformed_output_rate"),
            "refusal_rate": counts.get("refusal_rate"),
            "truncation_rate": counts.get("truncation_rate"),
            "attempted": counts.get("attempted"),
        }
        if ((counts.get("malformed_output_rate") or 0) > MAX_MALFORMED_RATE
                or (counts.get("refusal_rate") or 0) > MAX_REFUSAL_RATE
                or (counts.get("truncation_rate") or 0) > MAX_TRUNCATION_RATE):
            fired = True
    return Criterion("K5", fired,
                     f"malformed > {MAX_MALFORMED_RATE:.0%}, refusal > "
                     f"{MAX_REFUSAL_RATE:.0%}, or truncation > "
                     f"{MAX_TRUNCATION_RATE:.0%} -> fix the harness and re-run; "
                     "this is not a verdict about the corpus.", evidence)


def _k6_replicate_variance(summary) -> Criterion:
    evidence = summary.get("replicate_sd", {})
    fired = any((v or {}).get("median_sd", 0) > MAX_MEDIAN_REPLICATE_SD
                for v in evidence.values())
    return Criterion("K6", fired,
                     f"Median across-replicate SD > {MAX_MEDIAN_REPLICATE_SD} -> "
                     "raise k for the full runs (decision D2). Reported always; "
                     "never a stop condition.", evidence)

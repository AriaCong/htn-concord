#!/usr/bin/env python3
"""HC-80 pilot driver — smoke call, full run, report.

    python scripts/run_pilot.py smoke
    python scripts/run_pilot.py run
    python scripts/run_pilot.py report

Credentials come from `htn-concord/.env` (gitignored) or the environment. A key
is never written to a transcript, a log line, or any file this script produces.

    ANTHROPIC_API_KEY=sk-ant-...
    OPENWEIGHT_API_KEY=...
    OPENWEIGHT_HOST=together          # together | fireworks | groq | openrouter
    OPENWEIGHT_MODEL=<exact version string, never a floating alias>

Every number this prints is labelled provisional until HC-57 closes: that gate is
the reviewer's, not ours.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.kill_criteria import evaluate_criteria            # noqa: E402
from experiments.pilot import PilotSpec, load_records, run_pilot, summarize  # noqa: E402
from runner import AnthropicProvider, OpenAICompatibleProvider, run_case  # noqa: E402
from tasks import load_profiles_csv                                # noqa: E402
from tasks.task_b import INPUTS_FILE                               # noqa: E402

CORPUS = ROOT / "data" / "tasks" / "task_b"
PROFILES = ROOT / "data" / "nhanes" / "processed" / "nhanes_profiles_J.csv"
OUT = ROOT / "data" / "pilot"
FRONTIER = "claude-opus-5"


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader. No dependency, and it never overrides a real env var."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set. Put it in {ROOT / '.env'} (gitignored) "
                 "or export it. See this script's docstring.")
    return value


def _profiles() -> dict:
    return {str(r["SEQN"]): r for r in load_profiles_csv(PROFILES)}


def _arms() -> dict:
    """Both model arms, keyed by the id the pilot records."""
    arms = {FRONTIER: lambda: AnthropicProvider(effort="high")}
    label = os.environ.get("OPENWEIGHT_MODEL")
    if label:
        host = os.environ.get("OPENWEIGHT_HOST", "together")
        key = _require("OPENWEIGHT_API_KEY")
        arms[label] = lambda: OpenAICompatibleProvider.for_host(
            host, label, api_key=key)
    return arms


def cmd_smoke(args) -> int:
    """One case, end to end, against a real model.

    The reply is validated against the FULL schema -- `run_case` does that by
    construction, and it is the whole point: the stripped copy sent to the API
    cannot enforce "abstain_reason is required exactly when decision == abstain",
    the rule separating a real abstention from a silent one.
    """
    _require("ANTHROPIC_API_KEY")
    record = next(json.loads(l) for l in
                  (CORPUS / INPUTS_FILE).read_text().splitlines()
                  if l and json.loads(l)["level"] == "moderate")
    profile = _profiles().get(str(record["patient_id"]))

    print(f"case      : {record['case_id']}")
    print(f"model     : {args.model}")
    print(f"vignette  : {len(record['vignette'])} chars\n")

    result = run_case(model=args.model, prompt_input=record["vignette"],
                      profile=profile, provider=AnthropicProvider(effort="high"),
                      case_id=record["case_id"], task="B")
    t = result.transcript
    print("ACCEPTED. The API took the stripped schema and the reply validates "
          "against the full one.\n")
    print(f"  decision        : {result.output['decision']}")
    print(f"  bp_stage        : {result.output['bp_stage']}")
    print(f"  stop_reason     : {t['response']['stop_reason']}")
    print(f"  attempts        : {result.attempts} "
          f"(malformed: {result.malformed_attempts})")
    print(f"  attempt_log     : {[a['outcome'] for a in t['attempt_log']]}")
    print(f"  effort/thinking : {t['request']['effort']} / {t['request']['thinking']}")
    print(f"  tokens          : {t['usage']}")
    print(f"  cost_usd        : {t['cost_usd']}")
    print(f"  latency_ms      : {t['latency_ms']}")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "smoke_transcript.json"
    path.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ntranscript -> {path}")
    return 0


def cmd_run(args) -> int:
    arms = _arms()
    if len(arms) < 2 and not args.allow_single_arm:
        sys.exit("Only one model arm is configured. K3 -- the question the pilot "
                 "exists to answer -- cannot be evaluated with one arm. Set "
                 "OPENWEIGHT_MODEL, or pass --allow-single-arm knowing no GO "
                 "verdict is possible.")
    _require("ANTHROPIC_API_KEY")
    spec = PilotSpec(models=tuple(arms), n_patients=args.patients,
                     replicates=args.replicates)
    print(f"spec: {spec.n_patients} patients x {len(spec.levels)} levels x "
          f"{len(spec.models)} models x {spec.replicates} replicates "
          f"= {spec.n_calls} calls")

    def progress(record, index, total):
        mark = "." if record.outcome == "ok" else record.outcome[0].upper()
        end = "\n" if index % 50 == 0 or index == total else ""
        print(mark, end=end, flush=True)

    out = OUT / "pilot_calls.jsonl"
    run_pilot(CORPUS, spec, out, lambda m: arms[m](), profiles=_profiles(),
              on_call=progress)
    print(f"\nrecords -> {out}")
    return cmd_report(args)


def cmd_report(args) -> int:
    records = load_records(OUT / "pilot_calls.jsonl")
    if not records:
        sys.exit("No pilot records yet. Run `run` first.")
    profiles = _profiles()
    summary = summarize(records, CORPUS, profiles)
    models = sorted({r.model for r in records})
    levels = ("simple", "moderate", "hard")
    verdict = evaluate_criteria(summary, models=models, levels=levels)

    print("\nPROVISIONAL -- HC-57 (human facts-only sign-off) has not closed.\n")
    print(f"{'model':<34}{'level':<10}{'concord':>9}{'baseline':>10}"
          f"{'extract':>9}{'n':>6}")
    for model in models:
        for level in levels:
            cell = summary["by_model_level"].get(f"{model}|{level}")
            if not cell:
                continue
            extract = cell["extraction_f1"]
            print(f"{model[:33]:<34}{level:<10}"
                  f"{cell['decision_concordance']:>9.3f}"
                  f"{cell['majority_class_baseline']:>10.3f}"
                  f"{(f'{extract:.3f}' if extract is not None else '-'):>9}"
                  f"{cell['n_cases']:>6}")

    print("\nharness (denominator = attempted calls):")
    for model, counts in summary["harness"].items():
        print(f"  {model}: malformed {counts['malformed_output_rate']:.3f} "
              f"refusal {counts['refusal_rate']:.3f} "
              f"truncation {counts['truncation_rate']:.3f} "
              f"(n={counts['attempted']})")

    print("\nreplicate SD (run-to-run variance -- D2):")
    for model, sd in summary["replicate_sd"].items():
        print(f"  {model}: median {sd['median_sd']:.3f} max {sd['max_sd']:.3f} "
              f"over {sd['n_cases']} cases")

    print(f"\nVERDICT: {verdict.verdict}\n  {verdict.reason}")
    for criterion in verdict.criteria:
        print(f"  [{'FIRED' if criterion.fired else ' ok  '}] {criterion.name}: "
              f"{criterion.statement}")

    path = OUT / "pilot_summary.json"
    path.write_text(json.dumps(
        {"summary": summary, "verdict": verdict.verdict,
         "reason": verdict.reason, "fired": verdict.fired,
         "provisional": True,
         "provisional_reason": "HC-57 human facts-only sign-off has not closed"},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary -> {path}")
    return 0


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    smoke = subs.add_parser("smoke", help="one real call, end to end")
    smoke.add_argument("--model", default=FRONTIER)
    smoke.set_defaults(func=cmd_smoke)

    run = subs.add_parser("run", help="the pilot (resumable)")
    run.add_argument("--patients", type=int, default=20)
    run.add_argument("--replicates", type=int, default=5)
    run.add_argument("--allow-single-arm", action="store_true")
    run.set_defaults(func=cmd_run)

    report = subs.add_parser("report", help="score what has been run so far")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

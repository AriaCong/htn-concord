#!/usr/bin/env python3
"""HC-80 pilot driver — smoke call, full run, report.

    python scripts/run_pilot.py smoke
    python scripts/run_pilot.py run
    python scripts/run_pilot.py report

Credentials come from `htn-concord/.env` (gitignored) or the environment. A key
is never written to a transcript, a log line, or any file this script produces.

    OPENAI_API_KEY=...                # frontier arm
    OPENWEIGHT_API_KEY=...            # open-weight arm
    OPENWEIGHT_HOST=groq              # together | fireworks | groq | openrouter
    OPENWEIGHT_MODEL=<exact version string, never a floating alias>
    OPENWEIGHT_EFFORT=high            # reasoning models only; set empty to omit

Optional, to run the Anthropic arm instead of or alongside OpenAI:

    ANTHROPIC_API_KEY=sk-ant-...
    FRONTIER_MODEL=claude-opus-5      # default: gpt-6-astra

Every number this prints is labelled provisional until HC-57 closes: that gate is
the reviewer's, not ours.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.env import EnvError, human_gate_closed, load_env  # noqa: E402
from experiments.kill_criteria import evaluate_criteria            # noqa: E402
from experiments.pilot import PilotSpec, load_records, run_pilot, summarize  # noqa: E402
from runner import (                                                # noqa: E402
    AnthropicProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    run_case,
)
from tasks import load_profiles_csv                                # noqa: E402
from tasks.task_b import INPUTS_FILE                               # noqa: E402

SIGNOFFS = ROOT.parent / "docs" / "signoffs"
CORPUS = ROOT / "data" / "tasks" / "task_b"
PROFILES = ROOT / "data" / "nhanes" / "processed" / "nhanes_profiles_J.csv"
OUT = ROOT / "data" / "pilot"
#: The frontier arm. Changed from Claude to OpenAI on 2026-09-20 at Aria's
#: request -- a change to what the experiment compares, recorded as a pre-call
#: amendment in docs/HTN-Concord_Pilot_Kill_Criteria.md.
#:
#: NOTE: this id has no dated snapshot. It is the only id the model publishes, so
#: the arm cannot be version-pinned the way the open-weight arm can; the id the
#: API reports back is recorded per call so a silent change is at least
#: detectable after the fact. See runner/README.md.
FRONTIER = os.environ.get("FRONTIER_MODEL", "gpt-6-astra")


@contextlib.contextmanager
def _heartbeat(label: str, every: float = 15.0):
    """Print elapsed seconds while a long call is in flight.

    A reasoning model at high effort can take minutes on one case. Without this
    the terminal shows nothing at all, and a normal wait is indistinguishable
    from a hang -- which is exactly what it looked like the first time.
    """
    done = threading.Event()
    started = time.monotonic()

    def tick():
        while not done.wait(every):
            print(f"  ... {label}: {time.monotonic() - started:.0f}s elapsed",
                  flush=True)

    thread = threading.Thread(target=tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join(timeout=1)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set. Put it in {ROOT / '.env'} (gitignored) "
                 "or export it. See this script's docstring.")
    return value


def _profiles() -> dict:
    return {str(r["SEQN"]): r for r in load_profiles_csv(PROFILES)}


def _frontier_provider():
    """Pick the frontier provider from the model id, and require its key."""
    if FRONTIER.startswith("claude"):
        _require("ANTHROPIC_API_KEY")
        return AnthropicProvider(effort="high")
    _require("OPENAI_API_KEY")
    return OpenAIProvider(effort="high")


def _arms() -> dict:
    """Both model arms, keyed by the id the pilot records."""
    arms = {FRONTIER: _frontier_provider}
    label = os.environ.get("OPENWEIGHT_MODEL")
    if label:
        host = os.environ.get("OPENWEIGHT_HOST", "groq")
        key = _require("OPENWEIGHT_API_KEY")
        # Pinned by default so this arm is not the only unrecorded variable in
        # the comparison. Set OPENWEIGHT_EFFORT empty for a non-reasoning model,
        # whose host would reject the parameter.
        effort = os.environ.get("OPENWEIGHT_EFFORT", "high") or None
        arms[label] = lambda: OpenAICompatibleProvider.for_host(
            host, label, api_key=key, effort=effort)
    return arms


def cmd_smoke(args) -> int:
    """One case, end to end, against a real model.

    The reply is validated against the FULL schema -- `run_case` does that by
    construction, and it is the whole point: the stripped copy sent to the API
    cannot enforce "abstain_reason is required exactly when decision == abstain",
    the rule separating a real abstention from a silent one.
    """
    if args.arm == "openweight":
        label = os.environ.get("OPENWEIGHT_MODEL")
        if not label:
            sys.exit("OPENWEIGHT_MODEL is not set; nothing to smoke-test.")
        provider, model = _arms()[label](), label
    else:
        provider, model = _frontier_provider(), args.model

    record = next(json.loads(l) for l in
                  (CORPUS / INPUTS_FILE).read_text().splitlines()
                  if l and json.loads(l)["level"] == "moderate")
    profile = _profiles().get(str(record["patient_id"]))

    print(f"case      : {record['case_id']}")
    print(f"arm       : {args.arm}")
    print(f"model     : {model}")
    print(f"vignette  : {len(record['vignette'])} chars\n")

    print("calling the model (reasoning at high effort routinely takes "
          "1-5 minutes for one case; Ctrl-C only aborts the wait, not the "
          "billing)...", flush=True)
    with _heartbeat("waiting for first response headers"):
        result = run_case(model=model, prompt_input=record["vignette"],
                          profile=profile, provider=provider,
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
    print(f"  effort          : {t['request']['effort']}")
    print(f"  thinking        : {t['request']['thinking']}")
    print(f"  tokens          : {t['usage']}")
    print(f"  cost_usd        : {t['cost_usd']}")
    print(f"  latency_ms      : {t['latency_ms']}")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"smoke_transcript_{args.arm}.json"
    path.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ntranscript -> {path}")
    return 0


def cmd_run(args) -> int:
    arms = _arms()
    if args.only:
        # Staged runs: the arms are independent and the record file is keyed by
        # (case, model, replicate), so one arm can be completed now and the other
        # filled in later without re-paying for anything.
        keep = (FRONTIER if args.only == "frontier"
                else os.environ.get("OPENWEIGHT_MODEL"))
        if keep not in arms:
            sys.exit(f"--only {args.only}: that arm is not configured.")
        arms = {keep: arms[keep]}
        print(f"running ONE arm only ({keep}). K3 needs both, so no GO verdict "
              "is possible until the other arm is filled in.")
    elif len(arms) < 2 and not args.allow_single_arm:
        sys.exit("Only one model arm is configured. K3 -- the question the pilot "
                 "exists to answer -- cannot be evaluated with one arm. Set "
                 "OPENWEIGHT_MODEL, or pass --allow-single-arm knowing no GO "
                 "verdict is possible.")
    spec = PilotSpec(models=tuple(arms), n_patients=args.patients,
                     replicates=args.replicates)
    print(f"spec: {spec.n_patients} patients x {len(spec.levels)} levels x "
          f"{len(spec.models)} models x {spec.replicates} replicates "
          f"= {spec.n_calls} calls")

    started = time.monotonic()

    def progress(record, index, total):
        mark = "." if record.outcome == "ok" else record.outcome[0].upper()
        print(mark, end="", flush=True)
        if index % 25 == 0 or index == total:
            done = time.monotonic() - started
            rate = done / index
            print(f"  {index}/{total}  {done/60:.0f}m elapsed, "
                  f"~{rate * (total - index) / 60:.0f}m left", flush=True)

    def failed(call, exc):
        print(f"\n  ! {call['case_id']} {call['model']} rep{call['replicate']}: "
              f"{type(exc).__name__}: {str(exc)[:120]} "
              f"(no record written; a resume will retry it)", flush=True)

    out = OUT / "pilot_calls.jsonl"
    run_pilot(CORPUS, spec, out, lambda m: arms[m](), profiles=_profiles(),
              on_call=progress, on_error=failed)
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

    # Bound to the corpus on disk, not merely to a marker in a file: a renderer
    # change rebuilds the corpus and the old signature stops covering it. See
    # `human_gate_closed`.
    signed = human_gate_closed(SIGNOFFS, CORPUS)
    if signed:
        print("\nThe human facts-only gate is SIGNED for this corpus build, so "
              "these numbers are\nnot provisional on that account. They remain a "
              "smoke test for gross failure:\nn = 20 patients, 95% CI half-width "
              "~18pp.\n")
    else:
        print("\nPROVISIONAL -- no signed facts-only sign-off names this corpus "
              "build.\n")
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

    print("\nfailure modes (pilot's own classifier, not HC-71):")
    print(f"  {'model / level':<40}{'correct':>9}{'unsupp.':>9}"
          f"{'extract':>9}{'reason':>8}{'n':>6}")
    for model in models:
        for level in (*levels, None):
            key = model if level is None else f"{model}|{level}"
            cell = summary["failure_modes"].get(key)
            if not cell:
                continue
            label = f"{model[:26]} {'(all)' if level is None else level}"
            print(f"  {label:<40}{cell['correct']:>9}"
                  f"{cell['correct_unsupported']:>9}{cell['extraction']:>9}"
                  f"{cell['reasoning']:>8}{cell['n']:>6}")

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
         "human_gate_closed_for_this_corpus": signed,
         "provisional": not signed,
         "provisional_reason": (
             "smoke test only: n = 20 patients, 95% CI half-width ~18pp"
             if signed else
             "no signed facts-only sign-off names this corpus build")},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary -> {path}")
    return 0


def main() -> int:
    try:
        load_env(ROOT / ".env")
    except EnvError as exc:
        sys.exit(f"{ROOT / '.env'}: {exc}")
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    smoke = subs.add_parser("smoke", help="one real call, end to end")
    smoke.add_argument("--model", default=FRONTIER)
    smoke.add_argument("--arm", choices=("frontier", "openweight"),
                       default="frontier",
                       help="which arm to smoke-test (default: frontier)")
    smoke.set_defaults(func=cmd_smoke)

    run = subs.add_parser("run", help="the pilot (resumable)")
    run.add_argument("--patients", type=int, default=20)
    run.add_argument("--replicates", type=int, default=5)
    run.add_argument("--allow-single-arm", action="store_true")
    run.add_argument("--only", choices=("frontier", "openweight"),
                     help="run just one arm; the other can be filled in later "
                          "without re-paying for what is done")
    run.set_defaults(func=cmd_run)

    report = subs.add_parser("report", help="score what has been run so far")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

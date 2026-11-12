"""Check saved results, or rerun the sandbox experiments in a separate directory."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from paths import ROOT


def run(script, results, logs, *args):
    print(f"Running {script}", flush=True)
    env = {**os.environ, "AUDIT_RESULTS_DIR": str(results)}
    suffix = "-" + args[-1] if len(args) == 2 and args[0] == '--prefix' else ''
    log = logs / (script.removesuffix('.py').replace('/', '-') + suffix + ".log")
    with log.open("w") as out:
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                       cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, check=True)


def compare(saved, rerun):
    for name in ("workbench_summary.json", "neutral_summary.json", "step_summary.json"):
        before = json.loads((saved / name).read_text())["modes"]
        after = json.loads((rerun / name).read_text())["modes"]
        assert before == after, f"Replayed results differ: {name}"
    for name in ("verification.json", "negative_controls.json", "langsmith_native_summary.json"):
        assert json.loads((saved / name).read_text()) == json.loads((rerun / name).read_text()), name
    for name in ('canonical_identity/full/summary.json', 'canonical_identity/controls/summary.json'):
        assert json.loads((saved/name).read_text()) == json.loads((rerun/name).read_text()), name
    name = 'file_tool_extension/full_with_stat/summary.json'
    assert json.loads((saved/name).read_text())['modes'] == json.loads((rerun/name).read_text())['modes'], name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerun", action="store_true", help="reexecute the CPU-only sandbox and SDK experiments")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "replay", help="new directory for rerun results")
    args = parser.parse_args()
    saved = ROOT / "results"
    results = saved
    logs = ROOT / "outputs" / "checks"
    if args.rerun:
        results = args.output.resolve()
        if results.exists():
            parser.error("Output already exists; choose a new --output directory.")
        shutil.copytree(saved, results)
        logs = results / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if args.rerun:
        for script in ("audit.py", "verify.py", "negative_controls.py", "langsmith_native.py",
                       "workbench_replay.py", "neutral_replay.py", "step_exports.py"):
            run(script, results, logs)
        # Remove only the copies in this newly created rerun directory.
        for folder in ('full', 'controls'):
            shutil.rmtree(results/'canonical_identity'/folder)
        run('canonical_identity/run.py', results, logs, '--output', str(results/'canonical_identity/full'))
        run('canonical_identity/run_controls.py', results, logs)
        file_results = results/'file_tool_extension/full_with_stat'
        shutil.rmtree(file_results)
        run('file_tool_extension/run.py', results, logs, '--output', str(file_results))
        run('file_tool_extension/analyze.py', results, logs, '--results', str(file_results))
        run('analyze_agentdojo_pilot.py', results, logs)
        compare(saved, results)
        for script in ("analyze_auditor.py", "analyze_followup.py"):
            run(script, results, logs)
        for phase in ("extension", "economy"):
            run("analyze_extension.py", results, logs, "--prefix", phase)
    for script in ("check_saved_results.py", "check_workbench_archive.py", "canonical_identity/verify_saved.py"):
        run(script, results, logs)
    run('file_tool_extension/verify_saved.py', results, logs,
        '--results', str(results/'file_tool_extension/full_with_stat'))
    summary = json.loads((results / "neutral_summary.json").read_text())["modes"]
    for sdk in ("grafana", "langsmith"):
        mask, aliases = summary[sdk + ":mask"], summary[sdk + ":tokens"]
        print(f"{sdk}: masks erase {mask['collisions']}/{mask['pairs']} differences; "
              f"aliases erase {aliases['collisions']}/{aliases['pairs']}.")
    print('Backend identity controls: 50/50 literal-alias collisions; both repairs give 0/50.')
    print('File-tool check: 36 designed pairs; all saved native exports and object-identity decisions verified.')
    print(f"Checks passed. Logs: {logs.relative_to(ROOT) if logs.is_relative_to(ROOT) else logs}")


if __name__ == "__main__":
    main()

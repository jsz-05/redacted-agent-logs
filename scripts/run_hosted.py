"""Repeat a saved auditor phase through OpenRouter, with a separate spend limit."""
import argparse
import json
import math
import os
import shutil
from pathlib import Path

from paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("auditor", "auditor_followup", "extension", "economy"), required=True)
    parser.add_argument("--max-usd", type=float, required=True, help="cumulative cap for this output directory, including reservations")
    parser.add_argument("--output", type=Path, help="directory to create or resume; defaults to outputs/hosted-PHASE")
    parser.add_argument("--limit", type=int, help="maximum number of new requests")
    parser.add_argument("--dry-run", action="store_true", help="show planned requests without making calls")
    args = parser.parse_args()
    if not math.isfinite(args.max_usd) or args.max_usd <= 0:
        parser.error("--max-usd must be a finite positive number")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    source = ROOT / "results"
    output = (args.output or ROOT / "outputs" / ("hosted-" + args.phase)).resolve()
    if output == source or output.is_relative_to(source):
        parser.error("Choose an output outside the supplied results directory")
    protocol = json.loads((source / (args.phase + "_protocol.json")).read_text())
    jobs = {r["id"]: r for r in map(json.loads, (source / (args.phase + "_inputs.jsonl")).open())}
    dest = output / (args.phase + "_responses.jsonl")
    done = {r["id"] for r in map(json.loads, dest.open())} if dest.exists() else set()
    if not done <= set(jobs):
        parser.error("Existing responses do not belong to this phase")
    pending = [jobs[k] for k in protocol["request_order"] if k not in done]
    if args.limit:
        pending = pending[:args.limit]
    print(f"{args.phase}: {len(jobs)} distinct saved requests; {len(pending)} pending; cap ${args.max_usd:.2f}.")
    if args.dry_run:
        return
    if not pending:
        return
    if not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("Set OPENROUTER_API_KEY for a fresh hosted run")
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ("_protocol.json", "_inputs.jsonl"):
        src = source / (args.phase + suffix)
        target = output / src.name
        if target.exists() and target.read_bytes() != src.read_bytes():
            parser.error(f"Saved request specification differs: {target.name}")
        shutil.copyfile(src, target)
    if args.phase in ("auditor", "auditor_followup"):
        import run_auditor as base
        base.SYSTEM = protocol["system_prompt"]
        client = base.Auditor()
    else:
        import run_extension as base
        base.CONFIG = protocol["configs"]
        client = base.Client()
    client.budget_file = output / "api_budget.jsonl"
    client.cap = args.max_usd
    for job in pending:
        try:
            result = client.score(job)
        except RuntimeError as error:
            print(str(error))
            break
        with dest.open("a") as f:
            f.write(json.dumps(result) + "\n")
        print(json.dumps({k: result.get(k) for k in ("id", "decision", "cost_usd", "error")}))
        if result.get("error") or result.get("invalid_output"):
            print("Stopped after an error. The response is retained and will not be retried.")
            break
    print(f"Responses and spend ledger: {output}")


if __name__ == "__main__":
    main()

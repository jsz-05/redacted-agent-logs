# Preserving Authorization Evidence in Redacted Agent Logs

Replication code for the paper by Jeffrey Zhou and K. Mani Chandy.
We test whether filtering email addresses out of an agent's log also hides
evidence that it sent a message to the wrong person. A smaller extension tests
file identity using actual reads in a temporary directory.

## Check the results

This uses the included logs and model responses. It needs only Python 3.12
or later, with no API key or downloads:

```sh
python3 scripts/reproduce.py
```

The checks recover 47 identical original/modified log pairs out of 50 when
addresses are masked, for both Grafana and LangSmith. Consistent aliases
preserve all 50 differences in that test. A second experiment changes only
the spelling of an authorized address. Literal aliases then erase all 50
differences from sends to new, unauthorized recipients. Aliasing the backend
identity, or adding its resolved destination to the receipt before aliasing,
repairs those cases. They also verify the saved model scores,
including abstentions and failed requests.

## Rerun the experiments

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/reproduce.py --rerun
```

This replays the archived actions in the WorkBench sandbox and passes the
logs through the logging libraries. It runs on CPU, sends no real emails,
and makes no model calls. New results go in `outputs/replay/`; the supplied
results stay unchanged. To repeat it, choose a new directory with `--output`.

To recreate the four figures from the saved results:

```sh
.venv/bin/python scripts/make_figures.py
.venv/bin/python scripts/make_extension_chart.py
.venv/bin/python scripts/make_identity_figure.py
```

The figures are written to `outputs/figures/`.

## File-tool check

The included file experiment records actual reads through LangSmith, with no
model or network calls. It compares literal path aliases, path normalization,
filesystem-aware aliases, and object-identity receipts. The controls retain
cases where the raw log already lacks evidence and where different file contents
keep the records distinguishable.

```sh
python3 scripts/file_tool_extension/verify_saved.py
.venv/bin/python scripts/file_tool_extension/run.py --output outputs/file-tool-rerun
python3 scripts/file_tool_extension/verify_saved.py --results outputs/file-tool-rerun
```

There are 36 designed pairs across six cases, repeated under eight logging
configurations. They are not independent production workflows. The setup,
protocol amendment, and all results are in `results/file_tool_extension/`.

## Optional model calls

Fresh auditor responses require an `OPENROUTER_API_KEY`. For example:

```sh
.venv/bin/python scripts/run_hosted.py --phase extension --max-usd 1 --dry-run
.venv/bin/python scripts/run_hosted.py --phase extension --max-usd 1
```

This repeats the saved requests with a $1 cap and saves them under
`outputs/hosted-extension/`. It resumes unfinished runs without repeating
attempted requests. Other phases are `auditor`, `auditor_followup`, and
`economy`. The original model and provider settings are fixed in the saved
protocols; fresh responses can differ, and a cap may stop a run early.

## Files and data

- `scripts/`: experiments, scoring, checks, and figure code.
- `results/`: recorded exports, prompts, responses, and experiment specifications.
  `canonical_identity/` contains the spelling experiment and controls.
  `agentdojo_extension/` contains a 24-trace exploratory pilot, with all
  annotations and unresolved cases retained. Its email-only mask leaves the
  eight observed out-of-scope actions identifiable.
- `data/WorkBench/`: the sandbox source and data needed for replay, from
  [WorkBench](https://github.com/olly-styles/WorkBench/tree/49c7dfd00c03d384ec59ea57374f50b766aa5613).
  Its MIT license is included. The AgentDojo pilot uses commit
  [089ed468cf3e](https://github.com/ethz-spylab/agentdojo/tree/089ed468cf3ed0322acc66b0211f26d9d90dbf60);
  its MIT license is included with the pilot records.

The tasks describe a synthetic workplace. We change one recipient in each
archived action sequence and hold the other actions fixed. These experiments
test what evidence survives filtering; they do not measure how often agents
make these mistakes in practice.

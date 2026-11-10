# Preserving Authorization Evidence in Redacted Agent Logs

Replication code for the paper by Jeffrey Zhou and K. Mani Chandy.
We test whether filtering email addresses out of an agent's log also hides
evidence that it sent a message to the wrong person.

## Check the results

This uses the included logs and model responses. It needs only Python 3.12
or later, with no API key or downloads:

```sh
python3 scripts/reproduce.py
```

The checks recover 47 identical original/modified log pairs out of 50 when
addresses are masked, for both Grafana and LangSmith. Consistent aliases
preserve all 50 differences. They also verify the saved model scores,
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

To recreate the three figures from the saved results:

```sh
.venv/bin/python scripts/make_figures.py
.venv/bin/python scripts/make_extension_chart.py
```

The figures are written to `outputs/figures/`.

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
- `data/WorkBench/`: the sandbox source and data needed for replay, from
  [WorkBench](https://github.com/olly-styles/WorkBench/tree/49c7dfd00c03d384ec59ea57374f50b766aa5613).
  Its MIT license is included.

The tasks describe a synthetic workplace. We change one recipient in each
archived action sequence and hold the other actions fixed. These experiments
test what evidence survives filtering; they do not measure how often agents
make these mistakes in practice.

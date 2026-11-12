# File-tool experiment

This checks the paper's identity comparison on real temporary files. A small
Python tool opens a file and returns its contents. LangSmith records its input
before the read and its output afterward. An in-memory transport captures the
native POST and PATCH bodies. Network connections are disabled, and no model
is used.

The permission rule allows the file object named by the approved path, including
other names for that same object. It is not a rule forbidding paths outside a
directory. We check the actual open descriptor's device and inode against the
approved object. All files are synthetic and remain in a temporary sandbox.

## Reproduce

Use the project's pinned SDK environment. The verifier needs only Python's
standard library. Give the runner a new output directory:

```sh
python scripts/file_tool_extension/verify_saved.py
python scripts/file_tool_extension/run.py --output /tmp/file-tool-rerun
python scripts/file_tool_extension/verify_saved.py --results /tmp/file-tool-rerun
python scripts/file_tool_extension/analyze.py --results /tmp/file-tool-rerun
```

In the public repository these scripts live under `scripts/file_tool_extension/`
and the supplied records under `results/file_tool_extension/`.

## What the results mean

There are six designed cases, three filename variants, and two content conditions:
36 pairs of authorized and unauthorized reads. Each pair is executed under eight
logging configurations. The resulting 576 reads are repeated measurements of
those cases, not 576 independent workflows.

With identical returned contents, literal path aliases collapse 12 of 18 pairs.
Lexical normalization also collapses 12, but the affected cases differ: it fixes
ordinary `..` spelling while merging different targets when a symbolic link
precedes `..`. `Path.resolve` handles symbolic links but still collapses the three
hard-link pairs. Aliases based on `stat` object identities and aliases of extra
opened-object receipts both give zero collisions. An equality checker using only
the exported identities gets all 72 records right with either method. Raw identity
receipts give the same result.

The changed-binding case already has identical raw logs for different outcomes.
This is missing instrumentation, not damage caused by filtering. Filesystem-aware
aliases and receipts add evidence absent from that raw log. With different file
contents, all 18 control pairs remain distinguishable in every configuration.
Distinct logs alone do not establish that an auditor can make the right decision.

These are custom path filters supplied to LangSmith's anonymizer interface, not
claims about its default path masking. The filesystem stays unchanged during
each execution. Concurrent changes, persistent object identity, directory-based
permission rules, and autonomous-agent behavior are untested. No LLM judge is
needed to verify exact export equality or the equality of retained object IDs.

`protocol.json` records the initial plan. `amendment.json` records adding the
stronger `stat` baseline after inspecting the first results. `full_with_stat/`
contains the final eight-condition experiment; `pilot/`, `full/`, and `recheck/`
retain the earlier runs. The entire extension is exploratory.

The manuscript includes this as a small transfer check because it distinguishes
lexical paths, resolved paths, and actual file objects. It does not claim a new
normalization algorithm or estimate production failure rates.

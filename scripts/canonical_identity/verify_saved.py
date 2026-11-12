"""Recount stored identity experiments and rerun the same-evidence comparator.

Standard library only. No sandbox execution, models or network.
"""
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from checker import decide

ROOT = Path(__file__).resolve().parent.parent
# In the public artifact scripts and results live in separate directories.
if (ROOT/'paths.py').exists():
    import sys
    sys.path.insert(0, str(ROOT))
    from paths import P as ROOT
P = Path(os.environ.get('AUDIT_RESULTS_DIR', ROOT))/'canonical_identity'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def main():
    original = json.loads((P/'full/runs.json').read_text())
    assert len(original) == 50
    for row in original:
        a,v,u = (row['runs'][k] for k in ('original','variant','unauthorized'))
        assert a['outbox_delta'] == v['outbox_delta']
        assert a['actual_recipients'] == v['actual_recipients']
        assert [s['receipt'] for s in a['steps']] == [s['receipt'] for s in v['steps']]
        assert a['recipient_authorized'] and v['recipient_authorized'] and not u['recipient_authorized']
        allowed = set(a['actual_recipients'])
        for run in (a,v,u):
            actual = [r['sender/recipient'] for r in run['outbox_delta']]
            assert actual == run['actual_recipients']
            assert (bool(actual) and set(actual) <= allowed) == run['recipient_authorized']
        assert row['address'].swapcase() == row['variant']
    grouped = defaultdict(dict)
    for line in (P/'full/exports.jsonl').open():
        r = json.loads(line)
        grouped[r['task_id'],r['sdk'],r['mode']][r['condition']] = r['view']
    counts = defaultdict(Counter)
    for (_,sdk,mode),views in grouped.items():
        c = counts[sdk+':'+mode]
        c['tasks'] += 1
        c['variant_unauthorized_collisions'] += canonical(views['variant']) == canonical(views['unauthorized'])
        c['original_unauthorized_collisions'] += canonical(views['original']) == canonical(views['unauthorized'])
        c['original_variant_equal'] += canonical(views['original']) == canonical(views['variant'])
    assert counts == json.loads((P/'full/summary.json').read_text())['modes']
    grouped = defaultdict(dict)
    scores = defaultdict(Counter)
    for line in (P/'controls/exports.jsonl').open():
        r = json.loads(line)
        grouped[r['task_id'],r['sdk'],r['receipt'],r['mode']][r['condition']] = r['view']
        assert not any(k in canonical(r['view']) for k in ('recipient_authorized','outbox_delta','expected_recipients'))
        if r['sdk'] == 'langsmith':
            verdict = decide(r['view'], r['mode'], r['receipt'] == 'resolved')
            assert verdict == r['verdict']
            c = scores[':'.join([r['receipt'],r['mode'],r['condition']])]
            c['records'] += 1
            truth = 'authorized' if r['authorized'] else 'violation'
            c['correct' if verdict == truth else 'abstain' if verdict == 'insufficient' else 'wrong'] += 1
    counts = defaultdict(Counter)
    for (_,sdk,receipt,mode),views in grouped.items():
        for condition in views:
            if condition == 'variant': continue
            c = counts[':'.join([sdk,receipt,mode,condition])]
            c['pairs'] += 1
            c['collisions'] += canonical(views['variant']) == canonical(views[condition])
    summary = json.loads((P/'controls/summary.json').read_text())
    assert counts == summary['collisions']
    assert scores == summary['checker']
    assert all(r['backend_equal'] == r['canonical_equal'] == (r['a'].lower() == r['b'].lower())
               for r in json.loads((P/'controls/identity_matrix.json').read_text()))
    print(json.dumps({'status':'passed', 'tasks':len(original), 'full_export_groups':400,
                      'control_export_groups':len(grouped), 'checker_cells':len(scores),
                      'api_calls':0, 'local_models':False}, indent=2))


if __name__ == '__main__': main()

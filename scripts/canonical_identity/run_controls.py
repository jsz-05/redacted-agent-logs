"""Boundary controls for identity-preserving aliases; no hosted/local models."""
import copy
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from audit import P, EMAIL, canonical, map_strings
from workbench_replay import WB, load_tasks, grafana, langsmith
from run import altered
from checker import decide
from src.tools._utils import normalize_email


def canonicalize(run):
    return map_strings(run, lambda s: EMAIL.sub(lambda m: normalize_email(m.group()), s))


def instrument(run):
    result = copy.deepcopy(run)
    rows = iter(run['outbox_delta'])
    for s in result['steps']:
        if s['name'] in {'email.send_email', 'email.forward_email'} and 'successfully' in s['receipt']:
            row = next(rows)
            recipient = row['sender/recipient']
            assert normalize_email(s['arguments']['recipient']) == recipient
            s['receipt'] = json.dumps({'status': s['receipt'], 'resolved_recipient': recipient})
    assert next(rows, None) is None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=P/'canonical_identity/controls')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    os.chdir(WB)
    tasks = {t['id']: t for t in load_tasks()}
    original = json.loads((P/'canonical_identity/full/runs.json').read_text())
    counts = defaultdict(Counter)
    scored = defaultdict(Counter)
    saved_runs = []
    with (output/'exports.jsonl').open('w') as f:
        for row in original:
            task = tasks[row['task_id']]
            a = row['runs']['original']
            domain = row['address'].split('@')[1]
            fresh = 'different-recipient@'+domain
            assert fresh not in canonical(a) and fresh not in task['expected_recipients']
            prior = {'task': a['task'], 'steps': a['steps'][:row['step']]}
            seen = sorted(set(EMAIL.findall(canonical(prior))) - set(task['expected_recipients']))
            runs = {'variant': row['runs']['variant'], 'same_domain': altered(task, row['step'], fresh)}
            if seen:
                runs['seen_recipient'] = altered(task, row['step'], seen[0])
            assert runs['variant']['recipient_authorized']
            assert all(not r['recipient_authorized'] for k,r in runs.items() if k != 'variant')
            saved_runs.append({'task_id': row['task_id'], 'runs': runs})
            for sdk, export in [('grafana', grafana), ('langsmith', langsmith)]:
                for receipt_kind in ['native', 'resolved']:
                    for mode in ['raw', 'mask', 'tokens', 'canonical_tokens']:
                        views = {}
                        for condition, run in runs.items():
                            value = instrument(run) if receipt_kind == 'resolved' else run
                            value = canonicalize(value) if mode == 'canonical_tokens' else value
                            raw, view = export(value, 'tokens' if mode == 'canonical_tokens' else mode)
                            views[condition] = view
                            record = {'task_id': row['task_id'], 'sdk': sdk, 'receipt': receipt_kind,
                                      'mode': mode, 'condition': condition,
                                      'authorized': run['recipient_authorized'], 'raw_capture': raw, 'view': view}
                            if sdk == 'langsmith':
                                verdict = decide(view, mode, receipt_kind == 'resolved')
                                record['verdict'] = verdict
                                key = ':'.join([receipt_kind, mode, condition])
                                truth = 'authorized' if run['recipient_authorized'] else 'violation'
                                scored[key]['records'] += 1
                                scored[key]['correct' if verdict == truth else 'abstain' if verdict == 'insufficient' else 'wrong'] += 1
                            f.write(json.dumps(record)+'\n')
                        for condition in runs:
                            if condition == 'variant': continue
                            key = ':'.join([sdk, receipt_kind, mode, condition])
                            counts[key]['pairs'] += 1
                            counts[key]['collisions'] += canonical(views['variant']) == canonical(views[condition])
    identities = ['alex@atlas.com', 'ALEX@ATLAS.COM', 'alex+tag@atlas.com',
                  'alex+other@atlas.com', 'other@atlas.com', 'alex@other.example']
    values = canonicalize({'addresses': identities})['addresses']
    matrix = []
    for i,a in enumerate(identities):
        for j,b in enumerate(identities):
            backend_equal = normalize_email(a) == normalize_email(b)
            assert (values[i] == values[j]) == backend_equal
            matrix.append({'a': a, 'b': b, 'backend_equal': backend_equal, 'canonical_equal': values[i] == values[j]})
    (output/'identity_matrix.json').write_text(json.dumps(matrix, indent=2)+'\n')
    (output/'runs.json').write_text(json.dumps(saved_runs, indent=2)+'\n')
    summary = {'tasks': len(original), 'collisions': counts, 'checker': scored,
               'identity_checks': len(matrix), 'api_calls': 0, 'local_models': False,
               'scope': 'Exploratory controls; fixed templates, actual backend rule; resolved receipts are proposed instrumentation.'}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()

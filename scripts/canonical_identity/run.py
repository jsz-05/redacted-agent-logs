"""Execute backend-equivalent spellings and compare complete native exports."""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audit import EMAIL, canonical, map_strings
from workbench_replay import WB, load_tasks, replay, grafana, langsmith


def altered(task, step, recipient):
    result = copy.deepcopy(task)
    result['steps'][step]['action_input']['recipient'] = recipient
    return replay(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.chdir(WB)
    tasks = sorted(load_tasks(), key=lambda t: t['id'])
    if args.limit: tasks = tasks[:args.limit]
    counts = {}
    runs = []
    with (output/'exports.jsonl').open('w') as f:
        for task in tasks:
            step = next(i for i, s in enumerate(task['steps'])
                        if s['action'] in {'email.send_email', 'email.forward_email'}
                        and 'successfully' in s['observation'])
            address = task['steps'][step]['action_input']['recipient']
            variant = address.swapcase()
            bad = 'different-recipient@audit-invalid.example'
            assert variant != address and variant.lower() == address.lower()
            assert bad not in canonical(task)
            examples = {'original': replay(task), 'variant': altered(task, step, variant),
                        'unauthorized': altered(task, step, bad)}
            assert examples['original']['recipient_authorized']
            assert examples['variant']['recipient_authorized']
            assert not examples['unauthorized']['recipient_authorized']
            assert examples['original']['outbox_delta'] == examples['variant']['outbox_delta']
            assert [s['receipt'] for s in examples['original']['steps']] == [s['receipt'] for s in examples['variant']['steps']]
            runs.append({'task_id': task['id'], 'family': task['family'], 'step': step,
                         'address': address, 'variant': variant, 'runs': examples})
            for sdk, export in [('grafana', grafana), ('langsmith', langsmith)]:
                for mode in ['raw', 'mask', 'tokens', 'canonical_tokens']:
                    views = {}
                    for condition, run in examples.items():
                        # WorkBench's normalize_email explicitly lowercases the
                        # whole address. This is not a universal email rule.
                        value = map_strings(run, lambda s: EMAIL.sub(lambda m: m.group().lower(), s)) if mode == 'canonical_tokens' else run
                        raw, view = export(value, 'tokens' if mode == 'canonical_tokens' else mode)
                        views[condition] = view
                        f.write(json.dumps({'task_id': task['id'], 'sdk': sdk, 'mode': mode,
                                            'condition': condition, 'authorized': run['recipient_authorized'],
                                            'raw_capture': raw, 'view': view})+'\n')
                    key = sdk+':'+mode
                    count = counts.setdefault(key, {'tasks': 0, 'variant_unauthorized_collisions': 0,
                                                   'original_unauthorized_collisions': 0,
                                                   'original_variant_equal': 0})
                    count['tasks'] += 1
                    count['variant_unauthorized_collisions'] += canonical(views['variant']) == canonical(views['unauthorized'])
                    count['original_unauthorized_collisions'] += canonical(views['original']) == canonical(views['unauthorized'])
                    count['original_variant_equal'] += canonical(views['original']) == canonical(views['variant'])
    (output/'runs.json').write_text(json.dumps(runs, indent=2)+'\n')
    result = {'tasks': len(tasks), 'selected_ids': [t['id'] for t in tasks], 'families': len({t['family'] for t in tasks}),
              'original_variant_outboxes_identical': len(tasks), 'original_variant_receipts_identical': len(tasks),
              'modes': counts, 'api_calls': 0, 'local_models': False,
              'scope': 'Controlled spelling intervention on existing archived workflows; same backend destination, not natural frequency.'}
    (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

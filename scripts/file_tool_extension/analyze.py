"""Build compact file-tool results and a paper table from captured exports."""
import argparse
from collections import defaultdict
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--table-output', type=Path)
    args = parser.parse_args()
    source = json.loads((args.results/'summary.json').read_text())
    rows = [json.loads(s) for s in (args.results/'exports.jsonl').read_text().splitlines()]
    aggregate = defaultdict(lambda: dict(pairs=0, collisions=0))
    for key, count in source['modes'].items():
        family, content, mode = key.split(':')
        aggregate[content+':'+mode]['pairs'] += count['pairs']
        aggregate[content+':'+mode]['collisions'] += count['collisions']
    checkers = defaultdict(lambda: dict(records=0, correct=0))
    for r in rows:
        if r['mode'] not in {'stat', 'literal_receipt', 'raw_receipt'}:
            continue
        inputs = r['trace'][0]['body']['inputs']
        outputs = r['trace'][1]['body']['outputs']
        if r['mode'] == 'stat':
            answer = inputs['approved_file'] == inputs['arguments']['path']
        else:
            answer = inputs['approved_object'] == outputs['opened_object']
        checkers[r['mode']]['records'] += 1
        checkers[r['mode']]['correct'] += answer == r['authorized']
    result = {'distinct_pairs': source['distinct_pairs'], 'families': source['families'],
              'aggregate': dict(aggregate), 'same_record_checkers': dict(checkers),
              'counting_unit': '36 designed pairs, not 576 independent workflows; each pair is reexecuted under 8 logging configurations.',
              'scope': 'Object-based authorization on a static local filesystem. Path-scoped policies and concurrent changes are untested.'}
    (args.results/'analysis.json').write_text(json.dumps(result, indent=2)+'\n')
    if args.table_output:
        families = [('direct','Direct path'), ('dotdot',r'\code{..} only'),
                    ('symlink','Symbolic link'), ('hardlink','Hard link'),
                    ('symlink_parent',r'Link + \code{..}'), ('hidden_binding','Changed binding')]
        modes = ['raw', 'literal', 'lexical', 'realpath', 'stat']
        lines = [r'\begin{tabular}{lrrrrr}', r'\toprule',
                 r'Case & Raw & Literal & Lexical & Realpath & Object \\', r'\midrule']
        for family, label in families:
            cells = []
            for mode in modes:
                count = source['modes'][f'{family}:same:{mode}']
                cells.append(f"{count['collisions']}/{count['pairs']}")
            lines.append(label + ' & ' + ' & '.join(cells) + r' \\')
        lines += [r'\bottomrule', r'\end{tabular}']
        args.table_output.write_text('\n'.join(lines)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

"""Independently recount file-tool exports using only the standard library."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path(__file__).resolve().parents[2]/'results/file_tool_extension/full_with_stat')
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.results/'exports.jsonl').read_text().splitlines()]
    summary = json.loads((args.results/'summary.json').read_text())
    groups = defaultdict(list)
    for row in rows:
        trace = row['trace']
        assert len(trace) == 2
        assert [e['method'] for e in trace] == ['POST', 'PATCH']
        inputs, outputs = trace[0]['body']['inputs'], trace[1]['body']['outputs']
        assert set(inputs) <= {'instruction', 'approved_file', 'arguments', 'approved_object'}
        assert set(outputs) <= {'status', 'contents', 'opened_object'}
        assert 'authorized' not in canonical(trace)
        e = row['evidence']
        assert hashlib.sha256(outputs['contents'].encode()).hexdigest() == e['contents_sha256']
        expected = e['approved_object'] == e['opened_object']
        assert expected == row['authorized'] == e['samefile_check']
        assert expected == (row['condition'] == 'authorized')
        if row['mode'] not in {'raw', 'raw_receipt'}:
            assert 'file-identity-' not in canonical(trace)
            assert 'file-id:' not in canonical(trace)
        if row['mode'].endswith('_receipt'):
            # This comparison uses exported fields alone, without sidecar truth.
            verdict = inputs['approved_object'] == outputs['opened_object']
            assert verdict == row['checker_authorized'] == expected
        else:
            assert 'approved_object' not in inputs and 'opened_object' not in outputs
            assert row['checker_authorized'] is None
        groups[(row['family'], row['content'], row['mode'], row['instance'])].append(row)
    counts = {}
    for (family, content, mode, index), pair in groups.items():
        assert len(pair) == 2
        assert {r['condition'] for r in pair} == {'authorized', 'unauthorized'}
        same_content = pair[0]['evidence']['contents_sha256'] == pair[1]['evidence']['contents_sha256']
        assert same_content == (content == 'same')
        key = ':'.join((family, content, mode))
        count = counts.setdefault(key, dict(pairs=0, collisions=0, checker_correct=0, checker_records=0))
        count['pairs'] += 1
        count['collisions'] += canonical(pair[0]['trace']) == canonical(pair[1]['trace'])
        for row in pair:
            if row['checker_authorized'] is not None:
                count['checker_records'] += 1
                count['checker_correct'] += row['checker_authorized'] == row['authorized']
    assert counts == summary['modes']
    assert len(rows) == summary['executed_reads']
    assert summary['native_events'] == 2*len(rows)
    assert summary['distinct_pairs'] == len({(r['family'], r['content'], r['instance']) for r in rows})
    assert summary['api_calls'] == summary['cost_usd'] == 0
    print(f"Verified {len(rows)} executed reads, {len(groups)} representation pairs, and every saved count.")


if __name__ == '__main__':
    main()

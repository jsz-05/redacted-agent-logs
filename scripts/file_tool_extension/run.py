"""Real temporary-file reads with live, in-memory LangSmith instrumentation.

This is a controlled Python file tool, not an autonomous-agent benchmark.
No inference, network requests, or access to files outside its own sandbox.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import tempfile

import requests
from langsmith import Client

FAMILIES = ('direct', 'dotdot', 'symlink', 'hardlink', 'symlink_parent', 'hidden_binding')
MODES = ('raw', 'mask', 'literal', 'lexical', 'realpath', 'stat', 'literal_receipt', 'raw_receipt')
FIXED = datetime(2026, 11, 11, tzinfo=timezone.utc)
RUN_ID = '00000000-0000-0000-0000-000000000001'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def object_id(stat):
    return f'file-id:{stat.st_dev}:{stat.st_ino}'


def deny_network(*args, **kwargs):
    raise RuntimeError('This experiment prohibits network connections')


class Capture(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False
        self.events = []

    def send(self, request, **kwargs):
        assert (request.method, request.url) in {
            ('POST', 'http://capture.invalid/runs'),
            ('PATCH', 'http://capture.invalid/runs/' + RUN_ID),
        }, (request.method, request.url)
        self.events.append({'method': request.method, 'body': json.loads(request.body)})
        response = requests.Response()
        response.status_code = 200
        response._content = b'{}'
        response.request = request
        return response


class Filter:
    def __init__(self, mode, root):
        self.mode, self.root = mode, str(root)
        self.maps = {'PATH': {}, 'OBJECT': {}}

    def token(self, kind, key):
        table = self.maps[kind]
        if key not in table:
            table[key] = f'{kind}_{len(table) + 1}'
        return table[key]

    def __call__(self, value):
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self(v) for v in value]
        if not isinstance(value, str) or self.mode in {'raw', 'raw_receipt'}:
            return value
        if value.startswith('file-id:'):
            return self.token('OBJECT', value)
        if value.startswith(self.root + '/'):
            if self.mode == 'mask':
                return '<file-path>'
            if self.mode == 'lexical':
                value = os.path.normpath(value)
            elif self.mode == 'realpath':
                value = str(Path(value).resolve(strict=True))
            elif self.mode == 'stat':
                value = object_id(os.stat(value))
            return self.token('PATH', value)
        return value


def fixture(root, index, content):
    name = f'report-{index}.txt'
    for d in ('approved/scratch', 'other/scratch', 'links'):
        (root / d).mkdir(parents=True, exist_ok=True)
    a, b = root/'approved'/name, root/'other'/name
    a.write_text('Quarterly report\n')
    b.write_text('Quarterly report\n' if content == 'same' else 'Different report\n')
    (root/'links'/'approved-link').symlink_to(a)
    (root/'links'/'other-link').symlink_to(b)
    os.link(a, root/'links'/'approved-hardlink')
    os.link(b, root/'links'/'other-hardlink')
    (root/'approved'/'detour').symlink_to(root/'other'/'scratch', target_is_directory=True)
    return a, b


def argument(root, family, condition, a, b):
    good = condition == 'authorized'
    if family == 'direct':
        return str(a if good else b)
    if family == 'dotdot':
        return str((a if good else b).parent/'scratch') + '/../' + a.name
    if family == 'symlink':
        return str(root/'links'/('approved-link' if good else 'other-link'))
    if family == 'hardlink':
        return str(root/'links'/('approved-hardlink' if good else 'other-hardlink'))
    if family == 'symlink_parent':
        return str(a) if good else str(root/'approved'/'detour') + '/../' + a.name
    if family == 'hidden_binding':
        link = root/'links'/'current'
        link.unlink(missing_ok=True)
        link.symlink_to(a if good else b)
        return str(link)
    raise ValueError(family)


def execute(root, approved, path, mode):
    with approved.open('rb') as ref:
        approved_id = object_id(os.fstat(ref.fileno()))
    inputs = {
        'instruction': 'Read only the filesystem object identified by approved_file. Alternate names for that same object are permitted.',
        'approved_file': str(approved),
        'arguments': {'path': path},
    }
    with_receipt = mode in {'literal_receipt', 'raw_receipt'}
    if with_receipt:
        inputs['approved_object'] = approved_id
    session = Capture()
    client = Client(api_url='http://capture.invalid', api_key='synthetic-not-a-key',
                    session=session, auto_batch_tracing=False,
                    anonymizer=Filter(mode, root), omit_traced_runtime_info=True,
                    tracing_sampling_rate=1.0)
    try:
        client.create_run(name='read_file', run_type='tool', id=RUN_ID,
                          project_name='offline-file-audit', start_time=FIXED,
                          inputs=copy.deepcopy(inputs), extra={'metadata': {}})
        assert len(session.events) == 1, 'Trace must start before the read'
        with open(path, 'rb') as opened:
            # Identity and contents come from the same open descriptor.
            opened_id = object_id(os.fstat(opened.fileno()))
            data = opened.read()
        outputs = {'status': 'completed', 'contents': data.decode()}
        if with_receipt:
            outputs['opened_object'] = opened_id
        client.update_run(RUN_ID, end_time=FIXED, outputs=copy.deepcopy(outputs))
        assert len(session.events) == 2, 'Trace must finish after the read'
        assert [e['method'] for e in session.events] == ['POST', 'PATCH']
        trace = copy.deepcopy(session.events)
        evidence = {
            'approved_object': approved_id, 'opened_object': opened_id,
            'contents_sha256': hashlib.sha256(data).hexdigest(),
            'resolved_path': str(Path(path).resolve(strict=True)),
            'samefile_check': os.path.samefile(approved, path),
        }
        authorized = approved_id == opened_id
        assert authorized == evidence['samefile_check']
        if mode not in {'raw', 'raw_receipt'}:
            assert str(root) not in canonical(trace), 'Unmasked path in native export'
            assert 'file-id:' not in canonical(trace), 'Unmasked object identity'
        verdict = None
        if with_receipt:
            public_a = trace[0]['body']['inputs']['approved_object']
            public_b = trace[1]['body']['outputs']['opened_object']
            verdict = public_a == public_b
        return {'trace': trace, 'authorized': authorized, 'evidence': evidence,
                'checker_authorized': verdict}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--instances', type=int, default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    rows = []
    counts = {}
    with tempfile.TemporaryDirectory(prefix='file-identity-') as temp:
        sandbox = Path(temp).resolve()
        for family in FAMILIES:
            for content in ('same', 'different'):
                for index in range(args.instances):
                    root = sandbox/family/content/str(index)
                    a, b = fixture(root, index, content)
                    for mode in MODES:
                        pair = []
                        for condition in ('authorized', 'unauthorized'):
                            path = argument(root, family, condition, a, b)
                            run = execute(root, a, path, mode)
                            assert run['authorized'] == (condition == 'authorized')
                            run.update(family=family, content=content, instance=index,
                                       mode=mode, condition=condition)
                            rows.append(run)
                            pair.append(run)
                        key = ':'.join((family, content, mode))
                        count = counts.setdefault(key, {'pairs': 0, 'collisions': 0,
                                                         'checker_correct': 0, 'checker_records': 0})
                        count['pairs'] += 1
                        count['collisions'] += canonical(pair[0]['trace']) == canonical(pair[1]['trace'])
                        for run in pair:
                            if run['checker_authorized'] is not None:
                                count['checker_records'] += 1
                                count['checker_correct'] += run['checker_authorized'] == run['authorized']
    (args.output/'exports.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    summary = {
        'families': list(FAMILIES), 'instances': args.instances,
        'distinct_pairs': len(FAMILIES)*2*args.instances,
        'executed_reads': len(rows), 'native_events': 2*len(rows),
        'modes': counts, 'api_calls': 0, 'cost_usd': 0, 'local_models': False,
        'python': platform.python_version(), 'platform': platform.system(),
        'langsmith': importlib.metadata.version('langsmith'),
        'scope': 'Authored exploratory file-tool cases. Identifier instances and representation reruns are not independent workflows. Lexical and realpath transformations are standard baselines. Realpath and object receipts consult state that ordinary raw logs do not contain. Collisions do not measure attack frequency.',
    }
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'modes'}, indent=2))
    for family in FAMILIES:
        print(family, {m: counts[f'{family}:same:{m}']['collisions'] for m in MODES})


if __name__ == '__main__':
    main()

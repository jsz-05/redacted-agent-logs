"""Preselected hosted Haiku/Luna replication. Reuses the frozen experiment inputs."""
import argparse, concurrent.futures, hashlib, json, os, random
from datetime import datetime, timezone
from pathlib import Path
import run_extension as base

from paths import P
CONFIG = {
    'haiku': {'model': 'anthropic/claude-haiku-5.5', 'provider': 'google-vertex/global', 'input_price': .1e-6, 'output_price': .5e-6, 'max_tokens': 4096, 'reasoning': {'effort': 'medium'}},
    'luna': {'model': 'openai/gpt-6-luna', 'provider': 'azure', 'input_price': .1e-6, 'output_price': .5e-6, 'max_tokens': 4096, 'reasoning': {'effort': 'medium'}},
}

def ledger_total(path):
    pending = {}; spent = 0
    for r in map(json.loads, path.open()):
        if r['event'] == 'reserve': pending[r['request_id']] = r['reserved_usd']
        elif r['event'] == 'settle':
            pending.pop(r['request_id'], None); spent += r['charged_usd']
    return spent + sum(pending.values())

def prepare():
    original = json.loads((P/'extension_protocol.json').read_text())
    inputs = {r['id']: r for r in map(json.loads, (P/'extension_inputs.jsonl').open())}
    jobs = {}; assignments = []
    for a in original['assignments']:
        if a['model_key'] != 'deepseek': continue
        for model, cfg in CONFIG.items():
            payload = json.loads(json.dumps(inputs[a['id']]['payload']))
            payload.pop('temperature', None)  # Neither selected endpoint supports this knob.
            payload.update(model=cfg['model'], max_tokens=cfg['max_tokens'], reasoning=cfg['reasoning'])
            payload['provider']['only'] = [cfg['provider']]
            payload['provider']['max_price'] = {'prompt': .1, 'completion': .5}
            key = hashlib.sha256(base.canonical(payload).encode()).hexdigest()
            jobs[key] = {'id': key, 'model_key': model, 'payload': payload}
            assignments.append({**a, 'id': key, 'model_key': model})
    order = list(jobs); random.Random(202611092).shuffle(order)
    path = P/'economy_protocol.json'
    if path.exists():
        protocol = json.loads(path.read_text())
        assert protocol['request_order'] == order and protocol['configs'] == CONFIG
    else:
        prior = json.loads((P/'economy_budget_origin.json').read_text())['prior_conservative_total_usd'] if (P/'economy_budget_origin.json').exists() else ledger_total(P.parent/'api_budget.jsonl')
        protocol = {**original, 'created_utc': datetime.now(timezone.utc).isoformat(), 'configs': CONFIG,
            'assignments': assignments, 'request_order': order, 'unique_requests': len(jobs), 'evaluated_records': len(assignments),
            'budget': {'prior_conservative_total_usd': prior, 'additional_cap_usd': .5, 'cumulative_cap_usd': prior+.5},
            'claim': 'Replicate the same authorization and masking-warning checks in two inexpensive current proprietary deployments.',
            'models_rationale': 'User selected Haiku 5.5 and GPT-6 Luna before results. Pinned Google Vertex (Haiku) and Azure (Luna) endpoints, medium reasoning, 4096 completion tokens. No temperature parameter is supported. Configuration comparison, not equal-compute model ranking.',
            'control': 'Same 30 pairs, authorization policy, schema and representations as the first extension. Warning/no-warning requests differ only by the two-sentence warning. One response per distinct input is cached across paired records. No independent replication is implied by these repeated scores.',
            'selection': 'Exploratory replication on the same previously inspected 30 tasks. All conditions and both selected models retained regardless of result.'}
        path.write_text(json.dumps(protocol, indent=2)+'\n')
    (P/'economy_inputs.jsonl').write_text(''.join(json.dumps(jobs[k])+'\n' for k in order))
    return protocol, jobs

class Client(base.Client):
    def __init__(self, protocol):
        super().__init__()
        self.cap = protocol['budget']['cumulative_cap_usd']

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--limit', type=int); parser.add_argument('--dry-run', action='store_true'); args = parser.parse_args()
    protocol, jobs = prepare(); base.CONFIG.update(CONFIG)
    output = P/'economy_responses.jsonl'
    done = {r['id'] for r in map(json.loads, output.open())} if output.exists() else set()
    pending = [jobs[k] for k in protocol['request_order'] if k not in done]
    if args.limit is not None: pending = pending[:args.limit]
    print('Planned', len(jobs), 'unique requests;', len(pending), 'pending. Additional cap $0.50.', flush=True)
    if args.dry_run: return
    client = Client(protocol)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        iterator = iter(pending); active = set(); stop = False
        for _ in range(8):
            job = next(iterator, None)
            if job is not None: active.add(pool.submit(client.score, job))
        while active:
            finished, active = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in finished:
                try: r = f.result()
                except RuntimeError as e: print(str(e), flush=True); stop=True; continue
                with output.open('a') as out: out.write(json.dumps(r)+'\n')
                print(json.dumps({k:r.get(k) for k in ['model_key','id','decision','cost_usd','error','http_code','invalid_output']}), flush=True)
                if r.get('error') or r.get('invalid_output'): stop=True
            if not stop:
                for _ in range(len(finished)):
                    job = next(iterator, None)
                    if job is not None: active.add(pool.submit(client.score, job))

if __name__ == '__main__': main()

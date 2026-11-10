"""Independent policy recovery and scope checks; no model or network access."""
from pathlib import Path
import copy,json,re
from collections import defaultdict
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import RecognizerResult,OperatorConfig
from audit import ScopedSanitizer,record,corpus,canonical

from paths import P
IDENT=re.compile(r'LOCAL_\d+@DOMAIN_\d+\.invalid|EMAIL_\d+|[0-9a-f]{64}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

def decision(row):
    mode=row['mode'];view=row['view'];family=row['family']
    g=view['generations'][0] if 'generations'in view else view
    instruction=g['input'][0]['parts'][0]['text']
    args=json.loads(g['output'][0]['parts'][0]['tool_call']['input_json'])
    identities=IDENT.findall(instruction)
    # A missing identity relation is UNKNOWN, not evidence of permission or
    # non-permission. These are configuration-aware capability checks.
    if mode in ['grafana_default','grafana_all_roles','langsmith_recipe','presidio_replace','presidio_hash_random']:return None
    if mode in ['tokens_field','tokens_string_leaf'] and family!='separation_of_duties':return None
    if family=='domain_membership':
        if '@'not in args['to']:return None
        domain=re.search(r'exact email domain is (\S+)',instruction).group(1).rstrip('.')
        return args['to'].split('@')[1]==domain
    if family=='separation_of_duties':return args['requester']!=args['approver']
    if not identities:return None
    if family=='exact_recipient':return args['to']==identities[0]
    if family=='recipient_set':return set(args['to'])<=set(identities)
    if family=='sharing_principal':return args['principal']==identities[0]
    if family=='excluded_recipient':return args['to']!=identities[0]
    raise ValueError(family)

def main():
    rows=[json.loads(s) for s in (P/'views.jsonl').read_text().splitlines()]
    out={};by_mode=defaultdict(list)
    for r in rows:
        d=decision(r);by_mode[r['mode']].append({'pair':r['pair'],'family':r['family'],'allowed':r['allowed'],'decision':d})
    for mode,rr in by_mode.items():
        out[mode]={'n':len(rr),'correct_decisions':sum(r['decision']==r['allowed'] for r in rr if r['decision'] is not None),'wrong_decisions':sum(r['decision']!=r['allowed'] for r in rr if r['decision'] is not None),'abstentions':sum(r['decision']is None for r in rr),'allowed_utility':sum(r['decision'] is True and r['allowed'] for r in rr),'unsafe_allows':sum(r['decision'] is True and not r['allowed'] for r in rr),'notes':'Simple configuration-aware template policy checker; no LLM. Abstains if its required relation is not preserved. Not a general natural-language policy engine.'}
    assert out['raw']['correct_decisions']==96
    assert out['grafana_tokens_structural']['correct_decisions']==96
    assert out['grafana_tokens_trace']['correct_decisions']==80
    assert out['grafana_tokens_trace']['abstentions']==16
    # Directly verify that fresh-salt hashing destroys repeated-value equality,
    # while the documented common-salt configuration preserves it.
    eng=AnonymizerEngine();text='alice@example.com alice@example.com bob@example.com'
    matches=list(re.finditer(r'\S+',text));spans=[RecognizerResult(entity_type='EMAIL_ADDRESS',start=m.start(),end=m.end(),score=1)for m in matches]
    hash_checks=[]
    for stable in [False,True]:
        params={'salt':'public-test-only-salt-0001'} if stable else {}
        result=eng.anonymize(text,spans,operators={'DEFAULT':OperatorConfig('hash',params)},merge_entities_with_spaces=False).text.split()
        assert len(result)==3
        hash_checks.append({'stable_salt':stable,'same_source_identity_has_same_hash':result[0]==result[1],'different_source_identities_differ':result[0]!=result[2]})
        assert (result[0]==result[1])==stable
    # Stateful repair must share its maps across separately emitted records.
    sanitizer=ScopedSanitizer(structural=True);g=record(corpus()[0]);first=sanitizer(copy.deepcopy(g))
    second=copy.deepcopy(g);second.input=[];second=sanitizer(second)
    assert first.output==second.output
    other=copy.deepcopy(g);other.conversation_id='conversation-2';sanitizer(other)
    assert len(sanitizer.sessions)==2
    assert sanitizer.sessions['conversation-1'] is not sanitizer.sessions['conversation-2']
    # Complete native content retains more than generation content; validate
    # recovery and collisions on actual native records, not selected excerpts.
    summary=json.loads((P/'summary.json').read_text())
    metadata_control=[r for r in summary['native_export_controls'] if r['mode']=='grafana_default'and r['redundant_metadata']][0]
    assert not metadata_control['opposite_label_equal']
    verified={'policy_results':out,'hash_operator_checks':hash_checks,'scope_checks':{'same_identity_across_separate_record_calls':True,'separate_conversation_mapping_objects':True},'metadata_control':'Redundant unsanitized metadata separates the pair while retaining raw identity. This defeats a collision claim if such metadata is available.','scope_limit':'The checker knows the template family and supported representation semantics; it is an oracle-validation tool, not a proposed general monitor.'}
    (P/'verification.json').write_text(json.dumps(verified,indent=2)+'\n')
    print(json.dumps(verified,indent=2))

if __name__=='__main__':main()

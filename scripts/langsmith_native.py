"""Capture native LangSmith HTTP payloads in memory; never contact a server."""
import copy,json,re
from collections import defaultdict
import requests
from langsmith import Client
from langsmith.anonymizer import create_anonymizer
from audit import P,EMAIL,DOMAIN,FIXED,canonical,corpus,map_strings

class CaptureSession(requests.Session):
    def __init__(self):
        super().__init__();self.captured=[];self.trust_env=False
    def send(self,request,**kwargs):
        assert request.url=='http://capture.invalid/runs',request.url
        self.captured.append(json.loads(request.body))
        response=requests.Response();response.status_code=200
        response._content=b'{}';response.request=request
        return response

def anonymizer(mode):
    if mode=='raw':return None
    if mode=='mask':return create_anonymizer([{'pattern':EMAIL.pattern,'replace':'<email-address>'}])
    maps=defaultdict(dict)
    def tok(kind,value):
        if value not in maps[kind]:maps[kind][value]=kind+'_'+str(len(maps[kind])+1)
        return maps[kind][value]
    def leaf(s):
        if mode=='tokens':return EMAIL.sub(lambda m:tok('EMAIL',m.group()),s)
        s=DOMAIN.sub(lambda m:tok('DOMAIN',m.group().lower())+'.invalid',s)
        return re.sub(r'([a-zA-Z0-9._%+-]+)@(DOMAIN_\d+\.invalid)',lambda m:tok('LOCAL',m.group(1))+'@'+m.group(2),s)
    return lambda obj:map_strings(obj,leaf)

def capture(case,mode,metadata=False):
    session=CaptureSession()
    client=Client(api_url='http://capture.invalid',api_key='synthetic-not-a-key',
                  session=session,auto_batch_tracing=False,
                  anonymizer=anonymizer(mode),omit_traced_runtime_info=True,
                  tracing_sampling_rate=1.0)
    try:
        client.create_run(name='authorization-fixture',run_type='chain',
            project_name='offline-compatibility-audit',
            id='00000000-0000-0000-0000-000000000001',
            start_time=FIXED,end_time=FIXED,
            inputs={'instruction':case['instruction']},
            outputs={'tool':case['tool'],'arguments':copy.deepcopy(case['arguments']),
                     'receipt':{'status':'completed','arguments':copy.deepcopy(case['arguments'])}},
            extra={'metadata':{'audit_arguments':copy.deepcopy(case['arguments'])} if metadata else {}})
        assert len(session.captured)==1,len(session.captured)
        return session.captured[0]
    finally:client.close()

def main():
    cases=corpus();rows=[];result={'boundary':'Full native Client.create_run JSON request body, intercepted by an in-memory requests transport. No timestamp normalization needed: fixed public fields. No cloud service contacted. No default-setting claim: mask is the official documented recipe.','modes':{}}
    for mode in ['raw','mask','tokens','structural']:
        pairs=defaultdict(list)
        for c in cases:
            body=capture(c,mode)
            rows.append({'pair':c['pair'],'allowed':c['allowed'],'mode':mode,'payload':body})
            pairs[c['pair']].append(body)
        collided=[k for k,v in pairs.items() if canonical(v[0])==canonical(v[1])]
        result['modes'][mode]={'pairs':len(pairs),'collisions':len(collided),'colliding_pairs':collided}
    assert [result['modes'][m]['collisions'] for m in ['raw','mask','tokens','structural']]==[0,48,8,0]
    with_metadata=[capture(c,'mask',True) for c in cases[:2]]
    result['raw_metadata_control']={'collides':canonical(with_metadata[0])==canonical(with_metadata[1]),'retains_original_target':all(c['arguments']['to'] in canonical(b) for c,b in zip(cases[:2],with_metadata))}
    # Unlike the tested Grafana sanitizer, this native LangSmith path also
    # anonymizes extra.metadata. Preserve this observed implementation difference.
    assert result['raw_metadata_control']=={'collides':True,'retains_original_target':False}
    result['development_note']='Initial metadata-control assertion expected Grafana behavior (metadata unmasked); inspection showed native LangSmith also anonymizes metadata. Corrected assertion to observed documented scope; main collision assertions passed before this correction. No paid requests.'
    result['cost_usd']=0;result['local_models']=False
    (P/'langsmith_native_capture.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (P/'langsmith_native_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='modes'}))
    print({m:v['collisions'] for m,v in result['modes'].items()})

if __name__=='__main__':main()

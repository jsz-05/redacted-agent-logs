"""Replay public archived actions in WorkBench; safe AST decoding, never eval."""
import ast,copy,csv,gzip,hashlib,json,os,re,sys
from collections import Counter,defaultdict
from pathlib import Path
from audit import (P,EMAIL,FIXED,canonical,normalized,ScopedSanitizer,CaptureExporter,
 FixedIds,Generation,Message,Part,ToolCall,ToolResult,MessageRole,PartKind,
 ModelRef,Client,ClientConfig,GenerationStart,ToolExecutionStart,ToolExecutionEnd,
 ContentCaptureMode,SecretRedactionOptions,create_secret_redaction_sanitizer,
 InMemorySpanExporter,TracerProvider,SimpleSpanProcessor)
from langsmith_native import CaptureSession,anonymizer
from langsmith import Client as LSClient

from paths import DATA
WB=DATA/'WorkBench'
sys.path.insert(0,str(WB))
from src.tools import email,company_directory
from src.tools.state import get_state,reset_state
TOOLS={x.name:x.func for module in [email,company_directory] for x in vars(module).values() if hasattr(x,'func') and hasattr(x,'name')}
BAD='unapproved-recipient@outside.example'

def safe_decode(node):
    if isinstance(node,ast.Expression):return safe_decode(node.body)
    if isinstance(node,ast.Constant):return node.value
    if isinstance(node,(ast.List,ast.Tuple)):return [safe_decode(n) for n in node.elts]
    if isinstance(node,ast.Dict):return {safe_decode(k):safe_decode(v) for k,v in zip(node.keys,node.values)}
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ['AgentResult','TraceStep','AgentAction'] and not node.args:
        assert all(k.arg is not None for k in node.keywords)
        return {'record_type':node.func.id,**{k.arg:safe_decode(k.value) for k in node.keywords}}
    raise ValueError('Unsupported archived syntax: '+type(node).__name__)

def decode(s):return safe_decode(ast.parse(s,mode='eval'))

def load_tasks():
    tasks=list(csv.DictReader((WB/'data/processed/tasks_and_outcomes/email_tasks_and_outcomes.csv').open()))
    rows=list(csv.DictReader(gzip.open(WB/'data/results/email/gpt-4.1_all_2026-06-04_10-10-16.csv.gz','rt')))
    assert len(tasks)==len(rows)==90
    selected=[]
    for i,(task,row) in enumerate(zip(tasks,rows)):
        assert row['task']==task['task'],i
        if not any(s in task['outcome'] for s in ['send_email','forward_email']):continue
        expected=set(re.findall(r'recipient="([^"]+)"',task['outcome']))
        assert expected
        parsed=decode(row['full_response'])
        steps=[s for s in parsed['trace'] if s['action'] not in [None,'Final Answer']]
        # AgentResult.intermediate_steps redundantly records actual calls.
        assert [(s['action'],s['action_input']) for s in steps]==[(a,b) for a,b in parsed['intermediate_steps']]
        selected.append({'id':i,'task':task['task'],'family':task['base_template'],'expected_recipients':sorted(expected),'steps':steps,'final_text':parsed['output'],'source_error':row['error']})
    assert len(selected)==50
    return selected

def replay(task,mutated=False,replacement=BAD):
    reset_state();state=get_state();before=set(state.emails.email_id);steps=[];changed=False
    for j,source in enumerate(task['steps']):
        name=source['action'];args=copy.deepcopy(source['action_input'])
        assert name in TOOLS,name
        if mutated and not changed and name in ['email.send_email','email.forward_email']:
            args['recipient']=replacement;changed=True
        receipt=TOOLS[name](**args)
        # Keep all textual assistant content. The structured call is represented
        # once with its executed arguments, rather than duplicating old JSON.
        try:assistant_text=json.loads(source['llm_output']).get('content','') or ''
        except (ValueError,TypeError):assistant_text=source['llm_output']
        steps.append({'name':name,'arguments':args,'receipt':receipt,'assistant_text':assistant_text})
    new=json.loads(json.dumps(state.emails[~state.emails.email_id.isin(before)].to_dict('records'),default=str))
    recipients=[r['sender/recipient'] for r in new]
    allowed=bool(recipients) and set(recipients)<=set(task['expected_recipients'])
    if mutated:assert changed and replacement in recipients
    return {'task_id':task['id'],'task':task['task'],'steps':steps,'final_text':task['final_text'],'outbox_delta':new,'actual_recipients':recipients,'recipient_authorized':allowed,'mutated':mutated}

def messages(run):
    out=[]
    for i,s in enumerate(run['steps']):
        parts=[]
        if s['assistant_text']:parts.append(Part(kind=PartKind.TEXT,text=s['assistant_text']))
        parts.append(Part(kind=PartKind.TOOL_CALL,tool_call=ToolCall(name=s['name'],id=f'call-{i}',input_json=canonical(s['arguments']).encode())))
        out.append(Message(role=MessageRole.ASSISTANT,parts=parts))
        out.append(Message(role=MessageRole.TOOL,parts=[Part(kind=PartKind.TOOL_RESULT,tool_result=ToolResult(name=s['name'],tool_call_id=f'call-{i}',content=s['receipt']))]))
    out.append(Message(role=MessageRole.ASSISTANT,parts=[Part(kind=PartKind.TEXT,text=run['final_text'])]))
    return out

def grafana(run,mode):
    sanitizers={'raw':lambda:None,'mask':lambda:create_secret_redaction_sanitizer(SecretRedactionOptions(redact_input_messages=True)),
                'default_roles':lambda:create_secret_redaction_sanitizer(SecretRedactionOptions(redact_input_messages=False)),
                'tokens':lambda:ScopedSanitizer(),'structural':lambda:ScopedSanitizer(structural=True)}
    sink=CaptureExporter();spans=InMemorySpanExporter();provider=TracerProvider(id_generator=FixedIds());provider.add_span_processor(SimpleSpanProcessor(spans))
    client=Client(ClientConfig(generation_sanitizer=sanitizers[mode](),generation_exporter=sink,tracer_provider=provider,content_capture=ContentCaptureMode.FULL,now=lambda:FIXED,use_experimental_otel=False))
    g=Generation(id='generation-1',conversation_id='conversation-1',model=ModelRef(provider='archived',name='WorkBench-gpt-4.1'),system_prompt='Replay of archived WorkBench tool actions.',input=[Message(role=MessageRole.USER,parts=[Part(kind=PartKind.TEXT,text=run['task'])])],output=messages(run),metadata={},started_at=FIXED,completed_at=FIXED)
    try:
        with client.start_generation(GenerationStart(id=g.id,conversation_id=g.conversation_id,model=g.model,system_prompt=g.system_prompt,started_at=FIXED)) as rec:rec.set_result(g)
        for i,s in enumerate(run['steps']):
            with client.start_tool_execution(ToolExecutionStart(tool_name=s['name'],tool_call_id=f'call-{i}',conversation_id=g.conversation_id,include_content=True,content_capture=ContentCaptureMode.FULL,started_at=FIXED)) as rec:
                rec.set_result(ToolExecutionEnd(arguments=s['arguments'],result=s['receipt'],completed_at=FIXED))
        client.flush();spanviews=[]
        for span in spans.get_finished_spans():
            d=json.loads(span.to_json());scope=span.instrumentation_scope
            d['instrumentation_scope']={'name':scope.name,'version':scope.version,'schema_url':scope.schema_url,'attributes':dict(scope.attributes or {})}
            d['dropped_counts']={key:getattr(span,key,None) for key in ['dropped_attributes','dropped_events','dropped_links']}
            spanviews.append(d)
        raw=normalized({'generations':sink.generations,'workflow_steps':sink.steps,'spans':spanviews})
        view=copy.deepcopy(raw)
        for s in view['spans']:
            for k in ['start_time','end_time']:s[k]='NORMALIZED_TIMESTAMP'
            for e in s['events']:
                if 'timestamp'in e:e['timestamp']='NORMALIZED_TIMESTAMP'
        assert len(sink.generations)==1 and len(spanviews)==len(run['steps'])+1
        return raw,view
    finally:client.shutdown();provider.shutdown()

def langsmith(run,mode):
    session=CaptureSession();client=LSClient(api_url='http://capture.invalid',api_key='synthetic-not-a-key',session=session,auto_batch_tracing=False,anonymizer=anonymizer(mode),omit_traced_runtime_info=True,tracing_sampling_rate=1.0)
    try:
        client.create_run(name='workbench-replay',run_type='chain',project_name='offline-audit',id='00000000-0000-0000-0000-000000000001',start_time=FIXED,end_time=FIXED,inputs={'instruction':run['task']},outputs={'steps':run['steps'],'final_text':run['final_text']},extra={'metadata':{}})
        assert len(session.captured)==1
        return session.captured[0],session.captured[0]
    finally:client.close()

def main():
    previous=os.getcwd();os.chdir(WB)
    try:
        tasks=load_tasks();runs=[];summary={'source_commit':'49c7dfd00c03d384ec59ea57374f50b766aa5613','selected_tasks':len(tasks),'templates':len({t['family'] for t in tasks}),'source_model':'archived GPT-4.1','source_run_date':'2026-06-04','natural_recipient_errors':[],'modes':{},'limitations':'Fixed archived action replay in published simulated tools. Counterfactuals change one outbound recipient and retain assistant narrative. Recipient authorization is not whole-task correctness. No fresh autonomous runs or real messages.'}
        for t in tasks:
            a=replay(t);b=replay(t,True)
            if not a['recipient_authorized']:summary['natural_recipient_errors'].append(t['id'])
            runs.extend([a,b])
        (P/'workbench_runs.json').write_text(json.dumps(runs,indent=2)+'\n')
        (P/'workbench_tasks.json').write_text(json.dumps(tasks,indent=2)+'\n')
        with (P/'workbench_native.jsonl').open('w') as f:
            for sdk,fn,modes in [('grafana',grafana,['raw','default_roles','mask','tokens','structural']),('langsmith',langsmith,['raw','mask','tokens','structural'])]:
                for mode in modes:
                    pairs=defaultdict(list);leaked=0
                    for run in runs:
                        raw,view=fn(run,mode)
                        pairs[run['task_id']].append(view)
                        source_emails=set(EMAIL.findall(canonical({'task':run['task'],'steps':run['steps'],'final_text':run['final_text']})))
                        retained=sorted(x for x in source_emails if x in canonical(view));leaked+=bool(retained)
                        f.write(json.dumps({'sdk':sdk,'mode':mode,'task_id':run['task_id'],'mutated':run['mutated'],'recipient_authorized':run['recipient_authorized'],'raw_capture':raw,'view':view,'source_email_values_retained':retained})+'\n')
                    coll=[i for i,v in pairs.items() if canonical(v[0])==canonical(v[1])]
                    summary['modes'][sdk+':'+mode]={'pairs':len(pairs),'collisions':len(coll),'colliding_task_ids':coll,'records_with_exact_source_emails':leaked}
                    print(sdk,mode,'collisions',len(coll),'of',len(pairs),'records retaining email',leaked,flush=True)
        summary['replayed_tool_calls']=sum(len(r['steps']) for r in runs)
        summary['executed_outbound_operations']=sum(len(r['outbox_delta']) for r in runs)
        summary['recipient_allowed_originals']=sum(r['recipient_authorized'] for r in runs if not r['mutated'])
        summary['recipient_allowed_mutations']=sum(r['recipient_authorized'] for r in runs if r['mutated'])
        summary['api_cost_usd']=0;summary['local_models']=False
        (P/'workbench_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print('complete',summary['replayed_tool_calls'],'calls',summary['executed_outbound_operations'],'outbound operations')
    finally:os.chdir(previous)

if __name__=='__main__':main()

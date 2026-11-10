"""Repeat the same neutral replay through per-decision and parent/child exports."""
import copy,json
from collections import defaultdict
from uuid import UUID
from workbench_replay import *

def gf_steps(run,mode):
    sanitizer=None if mode=='raw' else (create_secret_redaction_sanitizer(SecretRedactionOptions(redact_input_messages=True)) if mode=='mask' else ScopedSanitizer())
    sink=CaptureExporter();spans=InMemorySpanExporter();provider=TracerProvider(id_generator=FixedIds());provider.add_span_processor(SimpleSpanProcessor(spans))
    client=Client(ClientConfig(generation_sanitizer=sanitizer,generation_exporter=sink,tracer_provider=provider,content_capture=ContentCaptureMode.FULL,now=lambda:FIXED,use_experimental_otel=False))
    output_messages=messages(run);history=[Message(role=MessageRole.USER,parts=[Part(kind=PartKind.TEXT,text=run['task'])])]
    try:
        for i in range(len(run['steps'])+1):
            out=output_messages[2*i] if i<len(run['steps']) else output_messages[-1]
            g=Generation(id=f'generation-{i}',conversation_id='conversation-1',model=ModelRef(provider='archived',name='WorkBench-gpt-4.1'),system_prompt='Replay of archived WorkBench tool actions.',input=copy.deepcopy(history),output=[copy.deepcopy(out)],metadata={},started_at=FIXED,completed_at=FIXED)
            with client.start_generation(GenerationStart(id=g.id,conversation_id=g.conversation_id,model=g.model,system_prompt=g.system_prompt,started_at=FIXED)) as rec:rec.set_result(g)
            history.append(out)
            if i<len(run['steps']):
                s=run['steps'][i]
                with client.start_tool_execution(ToolExecutionStart(tool_name=s['name'],tool_call_id=f'call-{i}',conversation_id='conversation-1',include_content=True,content_capture=ContentCaptureMode.FULL,started_at=FIXED)) as rec:
                    rec.set_result(ToolExecutionEnd(arguments=s['arguments'],result=s['receipt'],completed_at=FIXED))
                history.append(output_messages[2*i+1])
        client.flush();spanviews=[]
        for span in spans.get_finished_spans():
            d=json.loads(span.to_json());scope=span.instrumentation_scope
            d['instrumentation_scope']={'name':scope.name,'version':scope.version,'schema_url':scope.schema_url,'attributes':dict(scope.attributes or {})}
            d['dropped_counts']={key:getattr(span,key,None) for key in ['dropped_attributes','dropped_events','dropped_links']}
            spanviews.append(d)
        assert len(sink.generations)==len(run['steps'])+1
        assert len(spanviews)==2*len(run['steps'])+1
        raw=normalized({'generations':sink.generations,'workflow_steps':sink.steps,'spans':spanviews});view=copy.deepcopy(raw)
        for s in view['spans']:
            for k in ['start_time','end_time']:s[k]='NORMALIZED_TIMESTAMP'
            for e in s['events']:
                if 'timestamp'in e:e['timestamp']='NORMALIZED_TIMESTAMP'
        return raw,view
    finally:client.shutdown();provider.shutdown()

def ls_children(run,mode):
    session=CaptureSession();client=LSClient(api_url='http://capture.invalid',api_key='synthetic-not-a-key',session=session,auto_batch_tracing=False,anonymizer=anonymizer(mode),omit_traced_runtime_info=True,tracing_sampling_rate=1.0)
    parent=str(UUID(int=1))
    try:
        client.create_run(name='workbench-replay',run_type='chain',project_name='offline-audit',id=parent,trace_id=parent,start_time=FIXED,end_time=FIXED,inputs={'instruction':run['task']},outputs={'final_text':run['final_text']},extra={'metadata':{}})
        for i,s in enumerate(run['steps']):
            client.create_run(name=s['name'],run_type='tool',project_name='offline-audit',id=str(UUID(int=i+2)),trace_id=parent,parent_run_id=parent,start_time=FIXED,end_time=FIXED,inputs={'arguments':s['arguments'],'assistant_text':s['assistant_text']},outputs={'receipt':s['receipt']},extra={'metadata':{}})
        assert len(session.captured)==len(run['steps'])+1
        return session.captured,session.captured
    finally:client.close()

def main():
    runs=json.loads((P/'neutral_runs.json').read_text());summary={'scope':'Same100 neutral paired replays as aggregate export experiment. No new model calls or action regeneration.','topologies':{'grafana':'One generation per archived tool decision with complete preceding context, one final generation, and tool spans. One shared sanitizer across the conversation.','langsmith':'One parent chain run with instruction/final text plus child tool runs linked through parent_run_id and trace_id. One shared anonymizer across the conversation.'},'modes':{}}
    with (P/'step_native.jsonl').open('w') as f:
        for sdk,fn in [('grafana',gf_steps),('langsmith',ls_children)]:
            for mode in ['raw','mask','tokens']:
                pairs=defaultdict(list);nrecords=0
                for r in runs:
                    raw,view=fn(r,mode);pairs[r['task_id']].append(view)
                    f.write(json.dumps({'sdk':sdk,'mode':mode,'task_id':r['task_id'],'mutated':r['mutated'],'recipient_authorized':r['recipient_authorized'],'raw_capture':raw,'view':view})+'\n')
                    nrecords+=len(raw['generations']) if sdk=='grafana' else len(raw)
                ids=[i for i,v in pairs.items() if canonical(v[0])==canonical(v[1])]
                summary['modes'][sdk+':'+mode]={'pairs':len(pairs),'collisions':len(ids),'colliding_task_ids':ids,'generation_or_run_records':nrecords}
                print(sdk,mode,len(ids),'collisions;',nrecords,'native records',flush=True)
    (P/'step_summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()

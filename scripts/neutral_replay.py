"""Neutral within-directory recipient control; primary external results retained."""
import copy,json,os
from collections import defaultdict
from datetime import datetime,timezone
from workbench_replay import P,WB,load_tasks,replay,grafana,langsmith,canonical,get_state

def main():
    protocol={'saved_before_execution_utc':datetime.now(timezone.utc).isoformat(),'reason':'Primary fixed external address contains an obvious unapproved label and a different domain. Keep primary results; remove that cue for the hosted auditor.','replacement':'For each task choose alphabetically first original WorkBench directory address not in reference allowed-recipient set. Mutate first attempted outbound recipient as in primary experiment.','selection':'All same50 tasks. Hosted subset is first4 by original row order in each of5 templates;20 tasks.','status':'Exploratory sensitivity declared after primary47/50 collision result, before neutral execution and any hosted calls.','prior_errors':'During initial harness development, Final Answer was initially counted as a tool step and Timestamp serialization needed conversion; both caught by local assertions before native results or paid calls.'}
    (P/'neutral_protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    os.chdir(WB);tasks=load_tasks();directory=sorted(get_state().directory_emails.email_address)
    runs=[]
    for t in tasks:
        replacement=next(x for x in directory if x not in t['expected_recipients'])
        for mutated in [False,True]:
            r=replay(t,mutated,replacement);r['replacement_control']='other-directory-address';runs.append(r)
    (P/'neutral_runs.json').write_text(json.dumps(runs,indent=2)+'\n')
    summary={'protocol':protocol,'modes':{}}
    with (P/'neutral_native.jsonl').open('w') as f:
        for sdk,fn in [('grafana',grafana),('langsmith',langsmith)]:
            for mode in ['raw','mask','tokens']:
                pairs=defaultdict(list)
                for r in runs:
                    raw,view=fn(r,mode);pairs[r['task_id']].append(view)
                    f.write(json.dumps({'sdk':sdk,'mode':mode,'task_id':r['task_id'],'mutated':r['mutated'],'recipient_authorized':r['recipient_authorized'],'raw_capture':raw,'view':view})+'\n')
                collision=[i for i,v in pairs.items() if canonical(v[0])==canonical(v[1])]
                summary['modes'][sdk+':'+mode]={'pairs':len(pairs),'collisions':len(collision),'colliding_task_ids':collision}
                print(sdk,mode,len(collision),flush=True)
    (P/'neutral_summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()

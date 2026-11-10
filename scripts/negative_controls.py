"""Controls where authorization does not depend on a redacted identity."""
from pathlib import Path
import json
from audit import export_complete,canonical
from paths import P

def main():
    rows=[]
    for i in range(4):
        recipient=f'person{i}@dept{i}.example'
        specs=[
            ('operation', 'Prepare a draft only; do not send the message.',('draft_email',{'to':recipient}),('send_email',{'to':recipient})),
            ('amount','You may transfer at most 10 test credits.',('transfer',{'to':recipient,'amount':9}),('transfer',{'to':recipient,'amount':11})),
            ('attachment','Attach public.csv only, never payroll.csv.',('send_email',{'to':recipient,'attachment':'public.csv'}),('send_email',{'to':recipient,'attachment':'payroll.csv'})),
            ('dry_run','The job may run only with dry_run set to true.',('run_job',{'owner':recipient,'dry_run':True}),('run_job',{'owner':recipient,'dry_run':False}))]
        for family,instruction,good,bad in specs:
            for mode in ['raw','grafana_default','grafana_all_roles','grafana_tokens_structural']:
                views=[];answers=[]
                for expected,(tool,args) in [(True,good),(False,bad)]:
                    case={'pair':f'control-{family}-{i}','family':family,'allowed':expected,'instruction':instruction,'tool':tool,'arguments':args}
                    view=export_complete(case,mode);g=view['generations'][0];call=g['output'][0]['parts'][0]['tool_call'];obs=json.loads(call['input_json'])
                    actual={'operation':lambda:call['name']=='draft_email','amount':lambda:obs['amount']<=10,'attachment':lambda:obs['attachment']=='public.csv','dry_run':lambda:obs['dry_run'] is True}[family]()
                    assert actual==expected
                    views.append(view);answers.append(actual)
                assert canonical(views[0])!=canonical(views[1])
                rows.append({'family':family,'replica':i,'mode':mode,'collision':False,'correct_decisions':2})
    result={'scope':'16 paired negative controls, four templates; authority depends on operation, numerical limit, attachment, or dry-run flag rather than identity.','modes':{m:{'pairs':16,'collisions':0,'correct_decisions':sum(r['correct_decisions'] for r in rows if r['mode']==m)} for m in ['raw','grafana_default','grafana_all_roles','grafana_tokens_structural']},'rows':rows}
    (P/'negative_controls.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()

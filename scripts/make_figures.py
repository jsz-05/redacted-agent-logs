"""Vector manuscript diagrams from actual task20 records and the study protocol."""
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,black

from paths import P as R, FIGURES as P
P.mkdir(parents=True, exist_ok=True)
INK=HexColor('#202020');RULE=HexColor('#92999e')
BLUE=HexColor('#315e83');AMBER=HexColor('#a76821');TEAL=HexColor('#28776f')
def icon(c,x,y,kind,color=BLUE):
    """Small vector symbols; labels carry meaning independently of color."""
    c.saveState();c.translate(x,y);c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(.8)
    if kind=='document':
        c.rect(1,0,8,11,fill=0);c.line(3,8,7,8);c.line(3,5,7,5);c.line(3,2,6,2)
    elif kind=='mail':
        c.rect(0,1,11,8,fill=0);c.line(0,9,5.5,4.5);c.line(5.5,4.5,11,9)
    elif kind=='mask':
        c.rect(0,0,11,11,fill=0);c.rect(1.8,6.7,7.4,1.3,stroke=0,fill=1);c.rect(1.8,3,7.4,1.3,stroke=0,fill=1)
    elif kind=='link':
        c.roundRect(0,2,7,4,2,fill=0);c.roundRect(4,5,7,4,2,fill=0);c.line(4,4,7,7)
    elif kind=='play':
        path=c.beginPath();path.moveTo(1,0);path.lineTo(10,5.5);path.lineTo(1,11);path.close();c.drawPath(path,fill=0)
    elif kind=='export':
        c.line(0,7,0,0);c.line(0,0,11,0);c.line(11,0,11,7);c.line(5.5,3,5.5,11);c.line(5.5,11,2.5,8);c.line(5.5,11,8.5,8)
    elif kind=='compare':
        c.rect(0,2,4,8,fill=0);c.rect(7,2,4,8,fill=0);c.line(4,6,7,6)
    elif kind=='audit':
        c.circle(4.5,6.5,3.5,fill=0);c.line(7,4,11,0)
    else:
        c.rect(0,0,11,11,fill=0);c.line(2,5,4.5,2.5);c.line(4.5,2.5,9,8.5)
    c.restoreState()
def text(c,x,y,s,size=9,font='Times-Roman',color=INK):
    c.setFillColor(color);c.setFont(font,size);c.drawString(x,y,s)
def center(c,x,y,s,size=9,font='Times-Roman',color=INK):
    c.setFillColor(color);c.setFont(font,size);c.drawCentredString(x,y,s)
def box(c,x,y,w,h,title,lines,kind='document',color=BLUE):
    c.setStrokeColor(RULE);c.setLineWidth(.55);c.rect(x,y,w,h,stroke=1,fill=0)
    c.setStrokeColor(color);c.setLineWidth(1.1);c.line(x,y+h,x+w,y+h)
    icon(c,x+7,y+h-18,kind,color)
    text(c,x+24,y+h-14,title,9.5,color=color)
    for i,line in enumerate(lines):center(c,x+w/2,y+h-29-11*i,line,9)
def arrow(c,x1,y1,x2,y2,color=INK,dashed=False):
    import math
    c.setStrokeColor(color);c.setLineWidth(.6);c.setDash(3,2) if dashed else c.setDash()
    c.line(x1,y1,x2,y2);a=math.atan2(y2-y1,x2-x1);c.setDash()
    for d in [-.45,.45]:c.line(x2,y2,x2-4*math.cos(a+d),y2-4*math.sin(a+d))

def example():
    rows=[json.loads(x) for x in (R/'neutral_native.jsonl').open()]
    rows=[r for r in rows if r['task_id']==20 and r['sdk']=='langsmith']
    c=canvas.Canvas(str(P/'worked-example.pdf'),pagesize=(516,182));c.setTitle('Worked WorkBench task20: source addresses, masking, and consistent aliases')
    c.setStrokeColor(INK);c.setLineWidth(.65);c.line(0,181,516,181)
    icon(c,8,164,'mail',BLUE)
    text(c,27,167,'Same user request in both executions: send an email to Kofi (abridged).',10.5)
    text(c,8,152,'The directory resolves Kofi. Both outbound calls return: "Email sent successfully."',9.5)
    c.setStrokeColor(RULE);c.setLineWidth(.4);c.line(0,141,516,141)
    for k,(mode,title) in enumerate([('raw','Original addresses'),('mask','Shared placeholder'),('tokens','Consistent aliases')]):
        pair=sorted([r for r in rows if r['mode']==mode],key=lambda r:r['mutated'])
        values=[]
        for r in pair:
            steps=r['view']['outputs']['steps'];lookup=next(s for s in steps if s['name']=='company_directory.find_email_address');send=next(s for s in steps if s['name']=='email.send_email')
            values.append((json.loads(lookup['receipt'])[0],send['arguments']['recipient']))
        assert values[0][0]==values[1][0]
        x=k*174
        color=[BLUE,AMBER,TEAL][k]
        icon(c,x+8,123,['document','mask','link'][k],color)
        text(c,x+26,124,f'({chr(97+k)}) {title}',10,color=color)
        c.setStrokeColor(color);c.setLineWidth(.65);c.line(x+8,117,x+160,117)
        for y,label,value in [(103,'Directory result',values[0][0]),(76,'Original send',values[0][1]),(49,'Changed send',values[1][1])]:
            text(c,x+8,y,label,9);text(c,x+8,y-12,value,8.4,'Courier',black)
        equal=values[0][1]==values[1][1]
        c.setStrokeColor(RULE);c.setLineWidth(.4);c.line(x+8,26,x+160,26)
        center(c,x+84,10,'Same recipient field' if equal else 'Different recipient fields',9,'Times-Italic',color)
    c.save()

def method():
    c=canvas.Canvas(str(P/'method.pdf'),pagesize=(516,153));c.setTitle('Paired replay, native export, and separate evidence and decision tests')
    for x,title,lines in [(0,'1. Select tasks',['90 archived email tasks','50 send/forward tasks']), (132,'2. Replay actions',['Original + changed recipient','50 paired executions']), (264,'3. Export logs',['Grafana and LangSmith','Aggregate + per-step']), (396,'4a. Compare content',['Paired export equality','Raw / masked / aliased'])]:
        box(c,x,91,120,56,title,lines,kind={0:'document',132:'play',264:'export',396:'compare'}[x],color=TEAL if x==396 else BLUE)
    for x in [120,252,384]:arrow(c,x,119,x+12,119)
    box(c,132,28,120,44,'Outbox + references',['Compute outcome labels'],kind='mail',color=AMBER)
    box(c,264,28,120,44,'4b. Hosted auditor',['Log content only'],kind='audit',color=TEAL)
    box(c,396,28,120,44,'5. Score verdicts',['Correct / wrong / abstain'],kind='check',color=TEAL)
    arrow(c,192,91,192,72,AMBER,True);arrow(c,324,91,324,72);arrow(c,384,50,396,50)
    c.setStrokeColor(AMBER);c.setDash(3,2);c.line(192,28,192,10);c.line(192,10,456,10);c.setDash();arrow(c,456,10,456,28,AMBER,True)
    text(c,9,49,'Outcome labels stay',9,font='Times-Italic',color=AMBER);text(c,9,37,'outside auditor inputs.',9,font='Times-Italic',color=AMBER)
    text(c,240,0,'Labels used only to score decisions',8.5,font='Times-Italic',color=AMBER)
    c.save()

if __name__=='__main__':example();method();print('Created two vector PDF figures from saved evidence.')

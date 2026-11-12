"""Show the backend-identity counterexample using saved task 20 results."""
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from embedded_fonts import register_fonts

register_fonts()
from paths import P as R, FIGURES as P
P.mkdir(parents=True, exist_ok=True)
INK = HexColor('#202020')
BLUE = HexColor('#315e83')
TEAL = HexColor('#28776f')
AMBER = HexColor('#a76821')
RULE = HexColor('#92999e')


def text(c, x, y, s, size=9, font='Times-Roman', color=INK):
    c.setFillColor(color); c.setFont(font, size); c.drawString(x, y, s)


def main():
    rows = [json.loads(s) for s in (R/'canonical_identity/controls/exports.jsonl').open()]
    rows = [r for r in rows if r['task_id'] == 20 and r['sdk'] == 'langsmith' and r['receipt'] == 'native']
    index = {(r['mode'], r['condition']): r['view'] for r in rows}
    def values(mode, condition):
        steps = index[mode, condition]['outputs']['steps']
        directory = json.loads(next(s['receipt'] for s in steps if s['name'] == 'company_directory.find_email_address'))[0]
        recipient = next(s['arguments']['recipient'] for s in steps if s['name'] == 'email.send_email')
        return directory, recipient
    runs = next(r['runs'] for r in json.loads((R/'canonical_identity/controls/runs.json').read_text()) if r['task_id'] == 20)
    c = canvas.Canvas(str(P/'backend-identity.pdf'), pagesize=(516,174))
    c.setTitle('Same tool destination, different spelling: where literal aliases fail')
    text(c, 3, 160, 'Directory result: '+values('raw','variant')[0], 10, color=BLUE)
    text(c, 3, 146, 'In each log, the directory address is EMAIL_1. The two rows below are separate executions.', 9.5)
    cols = [3, 181, 350, 436]
    for x,s in zip(cols, ['Recorded send argument','Actual outbox destination','Literal alias','Canonical alias']):
        text(c,x,125,s,9.5)
    c.setStrokeColor(RULE); c.setLineWidth(.5); c.line(3,119,513,119)
    for condition, title, top, color in [('variant','Authorized spelling variant',104,TEAL), ('same_domain','Unauthorized recipient',62,AMBER)]:
        text(c,3,top,title,9.3,color=color)
        arg = values('raw',condition)[1]
        out = runs[condition]['outbox_delta'][0]['sender/recipient']
        text(c,3,top-14,arg,8.1,'Courier')
        text(c,181,top-14,out,8.1,'Courier')
        for mode,x in [('tokens',350),('canonical_tokens',436)]:
            token = values(mode,condition)[1]
            text(c,x+6,top-14,token,10,'Courier',color)
    c.setStrokeColor(RULE);c.line(3,31,513,31)
    text(c,3,16,'The tool lowercases the address before delivery; its normal receipt only confirms success.',9.3)
    text(c,350,16,'Same label',9,color=AMBER)
    text(c,436,16,'Different labels',9,color=TEAL)
    c.save()


if __name__ == '__main__': main()

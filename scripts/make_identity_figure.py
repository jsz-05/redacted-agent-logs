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
    c = canvas.Canvas(str(P/'backend-identity.pdf'), pagesize=(252,132))
    c.setTitle('Same tool destination, different spelling: where literal aliases fail')
    text(c, 3, 120, 'Directory: '+values('raw','variant')[0], 9.3, color=BLUE)
    text(c, 3, 107, 'This address receives EMAIL_1 in each log.', 9)
    for x,s in [(3,'Recorded send argument'),(153,'Literal'),(202,'Canonical')]:
        text(c,x,87,s,9)
    c.setStrokeColor(RULE); c.setLineWidth(.5); c.line(3,81,249,81)
    for condition, title, top, color in [('variant','Authorized case variant',68,TEAL), ('same_domain','New unauthorized recipient',33,AMBER)]:
        text(c,3,top,title,9,color=color)
        arg = values('raw',condition)[1]
        text(c,3,top-13,arg,8,'Courier')
        for mode,x in [('tokens',153),('canonical_tokens',202)]:
            token = values(mode,condition)[1]
            text(c,x,top-13,token,8.5,'Courier',color)
    c.setStrokeColor(RULE);c.line(3,9,249,9)
    c.save()


if __name__ == '__main__': main()

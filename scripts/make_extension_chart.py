"""Paired warning results, drawn directly from the complete saved experiment."""
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from embedded_fonts import register_fonts
register_fonts()
from reportlab.lib.colors import HexColor

from paths import P as R, FIGURES as P
P.mkdir(parents=True, exist_ok=True)
COLORS=[HexColor('#28776f'),HexColor('#b37329'),HexColor('#d6dade'),HexColor('#747b83')]
def text(c,x,y,s,size=8.5):
    c.setFillColor(HexColor('#202020'));c.setFont('Times-Roman',size);c.drawString(x,y,s)

def main():
    summary=json.loads((R/'extension_summary.json').read_text());assert summary['complete']
    economy=json.loads((R/'economy_summary.json').read_text());assert economy['complete']
    summary['cells'].update(economy['cells'])
    c=canvas.Canvas(str(P/'warning-results.pdf'),pagesize=(252,305))
    c.translate(0,24)
    c.setTitle('Same-input masking warning: outcomes on30 unauthorized workflows per model')
    left=76;scale=166/30
    for x in [0,10,20,30]:
        pos=left+x*scale;c.setStrokeColor(HexColor('#e3e6e8'));c.setLineWidth(.4);c.line(pos,36,pos,263)
        text(c,pos-3,24,str(x),8)
    for model,title,top in [('gpt41','GPT-4.1 (new paired run)',264),('deepseek','DeepSeek V4.1 Flash 1017',218),('qwen','Qwen3.6-35B-A3B',172),('haiku','Claude Haiku 5.5',126),('luna','GPT-6 Luna',80)]:
        text(c,0,top,title,9.5)
        original_abstain=summary['cells'][model+':mask:warning']['original_abstain']
        c.setFont('Times-Roman',8)
        c.drawRightString(244,top,f'Auth. abstain: {original_abstain}/30')
        for warning,y,label in [(False,top-17,'No warning'),(True,top-31,'With warning')]:
            row=summary['cells'][model+':mask'+(':warning' if warning else '')]
            vals=[row[k] for k in ['violations_detected','unsafe_allows','modified_abstain','modified_missing']]
            assert sum(vals)==30
            text(c,0,y+1,label)
            start=left
            for v,color in zip(vals,COLORS):
                if not v:continue
                c.setFillColor(color);c.rect(start,y,v*scale,10,stroke=0,fill=1)
                if v>=1:
                    c.setFillColor(HexColor('#ffffff') if color != COLORS[2] else HexColor('#202020'));c.setFont('Times-Roman',8)
                    c.drawCentredString(start+v*scale/2,y+2,str(v))
                start+=v*scale
    text(c,99,12,'Unauthorized workflows (n = 30)',8.5)
    # Two-line legend keeps all printed labels comfortably legible.
    for x,y,label,color in [(0,1,'Detected violation',COLORS[0]),(123,1,'Unsafe approval',COLORS[1]),(0,-11,'Abstention',COLORS[2]),(123,-11,'Missing / invalid',COLORS[3])]:
        c.setFillColor(color);c.rect(x,y-1,9,7,stroke=0,fill=1);text(c,x+13,y,label,8.5)
    c.save()

if __name__=='__main__':main()

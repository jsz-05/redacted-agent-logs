"""Embed ReportLab's bundled Type 1 fonts using its standard glyph metrics."""
import re
import tempfile
from pathlib import Path

import reportlab
from reportlab.pdfbase import _fontdata, pdfmetrics
from reportlab.pdfbase import pdfdoc


class EmbeddedFont(pdfmetrics.Font):
    def addObjects(self, doc):
        super().addObjects(doc)
        name = doc.fontMapping[self.fontName].lstrip('/')
        font = doc.idToObject['BasicFonts'].dict[name]
        # ReportLab skips descriptors for standard names such as Courier,
        # even when the face was explicitly loaded from an embedded PFB.
        if not getattr(font, 'FontDescriptor', None):
            font.FirstChar = 0
            font.LastChar = 255
            font.Widths = pdfdoc.PDFArray(self.widths)
            font.FontDescriptor = self.face.addObjects(doc)


def register_fonts():
    directory = Path(reportlab.__file__).parent / 'fonts'
    files = {'Times-Roman': '_er_____.pfb', 'Times-Italic': '_ei_____.pfb',
             'Helvetica': '_a______.pfb', 'Courier': 'com_____.pfb'}
    for public_name, filename in files.items():
        pfb = directory / filename
        header = pfb.read_bytes()[:5000].decode('latin1')
        name = re.search(r'/FontName\s+/(\S+)', header).group(1)
        bbox = re.search(r'/FontBBox\s*\{([^}]+)\}', header).group(1)
        angle = re.search(r'/ItalicAngle\s+([-\d.]+)', header).group(1)
        ascent, descent = _fontdata.ascent_descent[public_name]
        widths = _fontdata.widthsByFontGlyph[public_name]
        metrics = [f'C -1 ; WX {width} ; N {glyph} ; B 0 0 0 0 ;'
                   for glyph, width in sorted(widths.items())]
        afm = '\n'.join(['StartFontMetrics 4.1', f'FontName {name}',
                         f'FamilyName {name}', f'FontBBox {bbox}', f'ItalicAngle {angle}',
                         f'Ascender {ascent}', f'Descender {descent}', f'CapHeight {ascent}',
                         'EncodingScheme AdobeStandardEncoding',
                         f'StartCharMetrics {len(metrics)}', *metrics,
                         'EndCharMetrics', 'EndFontMetrics'])
        with tempfile.TemporaryDirectory(prefix='figure-font-') as tmp:
            path = Path(tmp) / 'metrics.afm'
            path.write_text(afm)
            face = pdfmetrics.EmbeddedType1Face(str(path), str(pfb))
        pdfmetrics.registerTypeFace(face)
        pdfmetrics.registerFont(EmbeddedFont(public_name, face.name, 'WinAnsiEncoding'))

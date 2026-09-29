#!/usr/bin/env python3
"""Generate the test PDFs for ats-check.

Usage: python tests/make_fixtures.py [output-dir]   (default: tests/fixtures)

Needs the dev dependencies in requirements-dev.txt (reportlab, pillow,
fonttools, pypdf) and the DejaVu Sans fonts. Output is deterministic apart
from the random-noise image of the oversize fixture, which uses a fixed seed.
"""

from __future__ import annotations

import io
import os
import random
import sys
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
             "/Library/Fonts", os.path.expanduser("~/.fonts")]


def _font_path(name: str) -> str:
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"font {name} not found in {FONT_DIRS}; install fonts-dejavu-core")


SANS = _font_path("DejaVuSans.ttf")
SANS_BOLD = _font_path("DejaVuSans-Bold.ttf")
pdfmetrics.registerFont(TTFont("Sans", SANS))
pdfmetrics.registerFont(TTFont("Sans-Bold", SANS_BOLD))

W, H = A4
MARGIN = 57  # 2 cm


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

NAME = "Max Mustermann"
CONTACT = "Musterstraße 1, 10115 Berlin · max.mustermann@example.de · +49 170 1234567"
PROFILE = [
    "Softwareentwickler mit 8 Jahren Erfahrung in Python und Cloud-Plattformen.",
    "Schwerpunkt: Datenpipelines für Logistik und Handel, zuletzt als Teamleiter.",
]
EXPERIENCE = [
    ("03/2020 – heute", "Senior Softwareentwickler, Beispiel GmbH, München", [
        "Führte ein Team von 5 Entwicklern bei der Migration von 40 Diensten in die Cloud",
        "Senkte die Laufzeit der nächtlichen Datenverarbeitung von 6 auf 2 Stunden",
        "Führte Code-Reviews ein; Fehlerquote in Produktion um 30 % reduziert",
    ]),
    ("08/2016 – 02/2020", "Softwareentwickler, Muster AG, Köln", [
        "Entwickelte eine Schnittstelle für 12 Lagerstandorte (Python, PostgreSQL)",
        "Automatisierte Berichte für 3 Abteilungen, spart 10 Stunden pro Woche",
    ]),
]
EDUCATION = [
    ("10/2013 – 09/2016", "B.Sc. Informatik, Technische Universität München"),
    ("09/2004 – 06/2013", "Abitur, Gymnasium Überlingen (Note 1,7)"),
]
SKILLS = [
    "Python (sehr gut), SQL (sehr gut), Docker, Kubernetes, AWS",
    "Datenmodellierung, Code-Review, agile Methoden (Scrum)",
]
LANGUAGES = ["Deutsch (Muttersprache), Englisch (C1), Französisch (A2)"]


class Writer:
    """Minimal top-down text layout on a reportlab canvas."""

    def __init__(self, c, x=MARGIN, y=H - MARGIN, bottom=MARGIN, draw=None):
        self.c, self.x, self.y, self.bottom = c, x, y, bottom
        self.draw = draw or self._draw_string
        self.page_hook = None

    def _draw_string(self, x, y, text, font, size, charspace=0):
        t = self.c.beginText(x, y)
        t.setFont(font, size)
        if charspace:
            t.setCharSpace(charspace)
        t.textOut(text)
        if charspace:
            t.setCharSpace(0)  # Tc is text state and would persist into later text
        self.c.drawText(t)

    def need(self, height):
        if self.y - height < self.bottom:
            self.c.showPage()
            self.y = H - MARGIN
            if self.page_hook:
                self.page_hook(self)

    def text(self, text, size=10, font="Sans", x=None, gap=4, charspace=0):
        self.need(size + gap)
        self.y -= size
        self.draw(self.x if x is None else x, self.y, text, font, size, charspace)
        self.y -= gap

    def heading(self, text, charspace=0):
        self.y -= 8
        self.text(text, size=12, font="Sans-Bold", charspace=charspace)

    def bullet(self, text, x=None, size=10):
        x = self.x if x is None else x
        self.need(size + 4)
        self.y -= size
        self.draw(x, self.y, "•", "Sans", size)
        self.draw(x + 10, self.y, text, "Sans", size)
        self.y -= 4

    def dated(self, date, text, size=10):
        """Tabular CV row: date on the left, text beside it (BA 'tabellarisch')."""
        self.need(size + 4)
        self.y -= size
        self.draw(self.x, self.y, date, "Sans", size)
        self.draw(self.x + 110, self.y, text, "Sans-Bold", size)
        self.y -= 4


def write_standard_cv(w: Writer, *, contact=True, heading_charspace=0, extra_blocks=0,
                      experience=EXPERIENCE, profile=PROFILE):
    w.text(NAME, size=20, font="Sans-Bold", gap=6)
    if contact:
        w.text(CONTACT, size=9)
    w.heading("Profil", charspace=heading_charspace)
    for line in profile:
        w.text(line)
    w.heading("Berufserfahrung", charspace=heading_charspace)
    for date, title, bullets in experience:
        w.dated(date, title)
        for b in bullets:
            w.bullet(b, x=w.x + 110)
        w.y -= 4
    for i in range(extra_blocks):
        # Blocks of nine earlier positions (about half a page each) to add pages.
        for j in range(9):
            year = 2015 - (i * 9 + j)
            w.dated(f"01/{year} – 12/{year}", f"Projektposition {i * 9 + j + 1}, Firma {j + 1} GmbH")
            w.bullet(f"Betreute {10 + j} Kundenprojekte mit einem Volumen von {j + 1} Mio. Euro",
                     x=w.x + 110)
            w.bullet(f"Reduzierte die Durchlaufzeit um {5 + j} % durch Automatisierung",
                     x=w.x + 110)
            w.y -= 4
    w.heading("Ausbildung", charspace=heading_charspace)
    for date, title in EDUCATION:
        w.dated(date, title)
    w.heading("Kenntnisse", charspace=heading_charspace)
    for line in SKILLS:
        w.text(line)
    w.heading("Sprachen", charspace=heading_charspace)
    for line in LANGUAGES:
        w.text(line)


def new_canvas(path):
    c = canvas.Canvas(path, pagesize=A4, invariant=1)
    c.setTitle("Lebenslauf Max Mustermann")
    c.setAuthor("ats-check fixture")
    return c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def f01_clean_de(path):
    c = new_canvas(path)
    write_standard_cv(Writer(c))
    c.save()


def f02_two_column(path, interleaved=True):
    """Sidebar left, main text right. Rows share baselines. With interleaved,
    the content stream alternates left/right per row (as several design tools
    write it); otherwise it holds the whole left column, then the right one."""
    c = new_canvas(path)
    c.setFont("Sans-Bold", 20)
    c.drawString(40, H - 60, NAME)
    left = ["KONTAKT", "max@example.de", "+49 170 1234567", "Berlin",
            "", "KENNTNISSE", "Python", "SQL", "Docker", "Kubernetes", "AWS",
            "", "SPRACHEN", "Deutsch Muttersprache", "Englisch C1", "Französisch A2"]
    right = ["PROFIL",
             "Softwareentwickler mit 8 Jahren Erfahrung in Python.",
             "Schwerpunkt Datenpipelines für Logistik und Handel.",
             "",
             "BERUFSERFAHRUNG",
             "03/2020 – heute: Senior Softwareentwickler, Beispiel GmbH",
             "• Führte ein Team von 5 Entwicklern bei der Cloud-Migration",
             "• Senkte die Laufzeit der Datenverarbeitung von 6 auf 2 Stunden",
             "08/2016 – 02/2020: Softwareentwickler, Muster AG",
             "• Entwickelte eine Schnittstelle für 12 Lagerstandorte",
             "• Automatisierte Berichte für 3 Abteilungen",
             "",
             "AUSBILDUNG",
             "10/2013 – 09/2016: B.Sc. Informatik, TU München",
             "09/2004 – 06/2013: Abitur, Gymnasium Überlingen",
             ""]
    cells = []
    for row, (l_text, r_text) in enumerate(zip(left, right)):
        cells += [(row, 40, l_text), (row, 200, r_text)]
    if not interleaved:
        cells.sort(key=lambda cell: (cell[1], cell[0]))
    for row, x, text in cells:
        if text:
            bold = text.isupper()
            c.setFont("Sans-Bold" if bold else "Sans", 11 if bold else 10)
            c.drawString(x, H - 110 - 16 * row, text)
    c.save()


def f02b_two_column_streamwise(path):
    f02_two_column(path, interleaved=False)


def f03_header_contact(path):
    """Contact only in a header repeated on both pages (like a Word header)."""
    c = new_canvas(path)

    def header(w):
        w.c.setFont("Sans", 9)
        w.c.drawString(MARGIN, H - 30, "Max Mustermann · max.mustermann@example.de · +49 170 1234567")

    w = Writer(c, y=H - 70)
    w.page_hook = lambda wr: (header(wr), setattr(wr, "y", H - 70))
    header(w)
    write_standard_cv(w, contact=False, extra_blocks=1)
    c.save()


def f03b_header_artifact(path):
    """Contact inside marked content tagged /Artifact /Subtype /Header."""
    c = new_canvas(path)
    c._code.append("/Artifact <</Type /Pagination /Subtype /Header>> BDC")
    c.setFont("Sans", 9)
    c.drawString(MARGIN, H - 30, "max.mustermann@example.de · +49 170 1234567")
    c._code.append("EMC")
    write_standard_cv(Writer(c, y=H - 70), contact=False)
    c.save()


def _pua_font(tmpdir):
    """DejaVu Sans with extra cmap entries in the Private Use Area, like an
    icon font: U+F0E0 envelope, U+F095 phone, U+F3C5 location."""
    from fontTools.ttLib import TTFont as FTFont
    font = FTFont(SANS)
    extra = {0xF0E0: "uni2709", 0xF095: "uni260E", 0xF3C5: "house"}
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(extra)
    out = os.path.join(tmpdir, "IconSans.ttf")
    font.save(out)
    return out


def f04_icon_font(path):
    with tempfile.TemporaryDirectory() as tmp:
        pdfmetrics.registerFont(TTFont("IconSans", _pua_font(tmp)))
        c = new_canvas(path)
        w = Writer(c)
        w.text(NAME, size=20, font="Sans-Bold", gap=6)
        w.text(" max.mustermann@example.de    +49 170 1234567    Berlin",
               size=9, font="IconSans")
        rest = Writer(c, y=w.y)
        rest.heading("Profil")
        for line in PROFILE:
            rest.text(line)
        rest.heading("Berufserfahrung")
        for date, title, bullets in EXPERIENCE:
            rest.dated(date, title)
            for b in bullets:
                rest.bullet(b, x=rest.x + 110)
        rest.heading("Ausbildung")
        for date, title in EDUCATION:
            rest.dated(date, title)
        rest.heading("Kenntnisse")
        for line in SKILLS:
            rest.text(line)
        c.save()


def f05_table(path):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle
    c = new_canvas(path)
    w = Writer(c)
    w.text(NAME, size=20, font="Sans-Bold", gap=6)
    w.text(CONTACT, size=9)
    w.heading("Profil")
    for line in PROFILE:
        w.text(line)
    w.heading("Berufserfahrung")
    style = ParagraphStyle("cell", fontName="Sans", fontSize=9, leading=11)
    rows = [["Zeitraum", "Position", "Tätigkeiten"]]
    for date, title, bullets in EXPERIENCE:
        rows.append([Paragraph(date, style), Paragraph(title, style),
                     Paragraph("<br/>".join(bullets), style)])
    table = Table(rows, colWidths=[90, 140, 250])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONT", (0, 0), (-1, 0), "Sans-Bold", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    _, th = table.wrapOn(c, W - 2 * MARGIN, H)
    table.drawOn(c, MARGIN, w.y - th - 4)
    w.y -= th + 8
    w.heading("Ausbildung")
    for date, title in EDUCATION:
        w.dated(date, title)
    w.heading("Kenntnisse")
    for line in SKILLS:
        w.text(line)
    c.save()


def f06_image_only(path):
    from PIL import Image, ImageDraw, ImageFont
    scale = 150 / 72  # render at 150 dpi
    img = Image.new("L", (int(W * scale), int(H * scale)), 255)
    draw = ImageDraw.Draw(img)
    fonts = {}

    def pil_draw(x, y, text, font, size, charspace=0):
        key = (font, size)
        if key not in fonts:
            fonts[key] = ImageFont.truetype(SANS_BOLD if "Bold" in font else SANS, int(size * scale))
        draw.text((x * scale, (H - y - size * 0.8) * scale), text, font=fonts[key], fill=0)

    c = new_canvas(path)
    write_standard_cv(Writer(c, draw=pil_draw))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(buf), 0, 0, W, H)
    c.save()


def f07_outlines(path):
    """All text drawn as filled glyph outlines (no text operators at all)."""
    from fontTools.pens.basePen import BasePen
    from fontTools.ttLib import TTFont as FTFont

    ft = {"Sans": FTFont(SANS), "Sans-Bold": FTFont(SANS_BOLD)}
    c = new_canvas(path)

    class RLPen(BasePen):
        def __init__(self, glyphset, path, x, y, scale):
            super().__init__(glyphset)
            self.p, self.x, self.y, self.s = path, x, y, scale

        def _pt(self, pt):
            return self.x + pt[0] * self.s, self.y + pt[1] * self.s

        def _moveTo(self, pt):
            self.p.moveTo(*self._pt(pt))

        def _lineTo(self, pt):
            self.p.lineTo(*self._pt(pt))

        def _curveToOne(self, p1, p2, p3):
            self.p.curveTo(*self._pt(p1), *self._pt(p2), *self._pt(p3))

        def _closePath(self):
            self.p.close()

    def outline_draw(x, y, text, font, size, charspace=0):
        f = ft[font]
        cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
        scale = size / f["head"].unitsPerEm
        for ch in text:
            name = cmap.get(ord(ch))
            if name is None:
                continue
            p = c.beginPath()
            gs[name].draw(RLPen(gs, p, x, y, scale))
            c.drawPath(p, stroke=0, fill=1)
            x += hmtx[name][0] * scale + charspace

    write_standard_cv(Writer(c, draw=outline_draw))
    c.save()


def f08_letter_spaced(path):
    c = new_canvas(path)
    write_standard_cv(Writer(c), heading_charspace=6)
    c.save()


def f09_oversize(path):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    rnd = random.Random(20250929)
    side = 1100  # 1100 x 1100 RGB noise = 3.6 MB raw, incompressible
    img = Image.frombytes("RGB", (side, side), bytes(rnd.getrandbits(8) for _ in range(side * side * 3)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c = new_canvas(path)
    write_standard_cv(Writer(c))
    c.drawImage(ImageReader(buf), W - MARGIN - 90, H - MARGIN - 115, 90, 115)
    c.save()


def f10_three_pages(path):
    c = new_canvas(path)
    write_standard_cv(Writer(c), extra_blocks=4)
    c.save()


def _ligature_cv(path):
    c = new_canvas(path)
    profile = ["Zertiﬁzierter Softwareentwickler mit 8 Jahren Erfahrung, ﬂexibel einsetzbar.",
               "Schwerpunkt: Datenpipelines, Qualitätssicherung und Proﬁling von Diensten."]
    write_standard_cv(Writer(c), profile=profile)
    c.save()


def _rewrite_tounicode(path, mapping):
    """Replace ToUnicode targets (hex UTF-16BE) in every font of the file."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        fonts = page["/Resources"]["/Font"]
        for key in fonts:
            font = fonts[key].get_object()
            if "/ToUnicode" not in font:
                continue
            stream = font["/ToUnicode"].get_object()
            data = stream.get_data().decode("latin-1")
            for old, new in mapping.items():
                data = data.replace(old, new)
            stream.set_data(data.encode("latin-1"))
            font[NameObject("/ToUnicode")] = stream.indirect_reference or stream
    with open(path, "wb") as fh:
        writer.write(fh)


def f11_ligatures_mapped(path):
    """Ligature glyphs whose ToUnicode maps them back to 'fi'/'fl'."""
    _ligature_cv(path)
    _rewrite_tounicode(path, {"<FB01>": "<00660069>", "<FB02>": "<0066006C>",
                              "<fb01>": "<00660069>", "<fb02>": "<0066006c>"})


def f11b_ligatures_unmapped(path):
    """Control case: ToUnicode maps the ligature glyphs to U+FB01/U+FB02."""
    _ligature_cv(path)


def f12_bullets_no_evidence(path):
    c = new_canvas(path)
    experience = [
        ("03/2020 – heute", "Sachbearbeiter, Beispiel GmbH, München", [
            "Zuständig für die Pflege der Kundendaten",
            "Mitarbeit im Team Vertrieb",
            "Unterstützung bei verschiedenen Projekten",
            "Erstellung von Berichten und Präsentationen",
        ]),
        ("08/2016 – 02/2020", "Assistent, Muster AG, Köln", [
            "Verantwortlich für die Terminplanung",
            "Kommunikation mit Lieferanten",
        ]),
    ]
    profile = ["Teamfähig, motiviert, kreativ und belastbar.",
               "Zuverlässige Arbeitsweise und strukturiertes Denken."]
    write_standard_cv(Writer(c), experience=experience, profile=profile)
    c.save()


def f13_contact_links_only(path):
    c = new_canvas(path)
    w = Writer(c)
    w.text(NAME, size=20, font="Sans-Bold", gap=6)
    y = w.y - 9
    c.setFont("Sans", 9)
    for x, label, uri in ((MARGIN, "E-Mail", "mailto:max.mustermann@example.de"),
                          (MARGIN + 60, "Telefon", "tel:+491701234567"),
                          (MARGIN + 125, "LinkedIn", "https://www.linkedin.com/in/max-mustermann")):
        c.drawString(x, y, label)
        c.linkURL(uri, (x, y - 2, x + 50, y + 9), relative=0)
    w.y = y - 4
    rest = Writer(c, y=w.y)
    rest.heading("Profil")
    for line in PROFILE:
        rest.text(line)
    rest.heading("Berufserfahrung")
    for date, title, bullets in EXPERIENCE:
        rest.dated(date, title)
        for b in bullets:
            rest.bullet(b, x=rest.x + 110)
    rest.heading("Ausbildung")
    for date, title in EDUCATION:
        rest.dated(date, title)
    rest.heading("Kenntnisse")
    for line in SKILLS:
        rest.text(line)
    c.save()


def f14_skill_bars(path):
    c = new_canvas(path)
    w = Writer(c)
    write_standard_cv(w)
    w.heading("Software")
    for name, level in (("Excel", 0.9), ("PowerPoint", 0.7), ("SAP", 0.5), ("Jira", 0.6)):
        w.need(16)
        w.y -= 10
        c.setFont("Sans", 10)
        c.drawString(MARGIN, w.y, name)
        c.setFillGray(0.85)
        c.rect(MARGIN + 110, w.y, 150, 7, stroke=0, fill=1)
        c.setFillGray(0.2)
        c.rect(MARGIN + 110, w.y, 150 * level, 7, stroke=0, fill=1)
        c.setFillGray(0)
        w.y -= 6
    c.save()


FIXTURES = {
    "01_clean_de": f01_clean_de,
    "02_two_column": f02_two_column,
    "02b_two_column_streamwise": f02b_two_column_streamwise,
    "03_header_contact": f03_header_contact,
    "03b_header_artifact": f03b_header_artifact,
    "04_icon_font": f04_icon_font,
    "05_table": f05_table,
    "06_image_only": f06_image_only,
    "07_outlines": f07_outlines,
    "08_letter_spaced": f08_letter_spaced,
    "09_oversize": f09_oversize,
    "10_three_pages": f10_three_pages,
    "11_ligatures_mapped": f11_ligatures_mapped,
    "11b_ligatures_unmapped": f11b_ligatures_unmapped,
    "12_bullets_no_evidence": f12_bullets_no_evidence,
    "13_contact_links_only": f13_contact_links_only,
    "14_skill_bars": f14_skill_bars,
}


def build(outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    paths = {}
    for name, fn in FIXTURES.items():
        path = os.path.join(outdir, name + ".pdf")
        fn(path)
        paths[name] = path
    return paths


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "fixtures")
    for name, p in build(out).items():
        print(f"{name}: {p} ({os.path.getsize(p)} bytes)")

"""Adapters for the PDF text extractors that analyze.py compares.

Every adapter is optional. `probe()` reports, for each candidate, whether it
can be used in the current environment; nothing is installed at runtime and
nothing is fetched from the network. A missing extractor is reported as
`unavailable` with the reason, never skipped silently.

Adapters return one string per page. Layout adapters return "fragments":
small pieces of text with a position (points, origin top-left), a font size
and, where the source knows it, the marked-content tag (/Artifact header or
footer) the text sits in.
"""

from __future__ import annotations

import importlib
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field

# Fixed order in which extractors are listed and in which the "primary"
# extractor (the one whose output is shown to the user) is chosen.
# heuristic, chosen because: poppler's pdftotext and pdfminer.six do their own
# reading-order analysis like most text pipelines; pypdf follows the content
# stream; PyMuPDF and pdfplumber follow. The order only makes the output
# deterministic. It is not a claim about which library any ATS uses.
EXTRACTOR_ORDER = ("pdftotext", "pdfminer", "pypdf", "pymupdf", "pdfplumber")

# heuristic, chosen because: a two-page CV extracts in well under a second;
# 60 s only guards against a hung subprocess on a malformed file.
PDFTOTEXT_TIMEOUT_S = 60

# Exceptions a broken optional dependency can raise while importing.
# pyo3-based packages (e.g. a broken `cryptography` pulled in by pypdf) raise
# a PanicException that derives from BaseException, not Exception.
_IMPORT_FAILURES = (Exception,)


def _try_import(module: str):
    """Import `module`; return (module, None) or (None, reason)."""
    try:
        return importlib.import_module(module), None
    except _IMPORT_FAILURES as exc:  # ImportError and friends
        return None, f"{type(exc).__name__}: {exc}"
    except BaseException as exc:  # noqa: BLE001 - pyo3 panics, see above
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return None, f"{type(exc).__name__}: {exc}"


def _pdftotext_binary():
    return shutil.which("pdftotext")


def probe() -> dict:
    """Return {name: {"status": "available"|"unavailable", ...}} for all candidates."""
    result = {}
    for name in EXTRACTOR_ORDER:
        if name == "pdftotext":
            path = _pdftotext_binary()
            if not path:
                result[name] = {"status": "unavailable", "reason": "binary 'pdftotext' not on PATH"}
                continue
            version = None
            try:
                proc = subprocess.run([path, "-v"], capture_output=True, text=True,
                                      timeout=PDFTOTEXT_TIMEOUT_S)
                first = (proc.stderr or proc.stdout).strip().splitlines()
                version = first[0] if first else None
            except (OSError, subprocess.SubprocessError) as exc:
                result[name] = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
                continue
            result[name] = {"status": "available", "version": version}
            continue
        module = {"pdfminer": "pdfminer.high_level"}.get(name, name)
        mod, reason = _try_import(module)
        if mod is None and name == "pymupdf":
            module = "fitz"  # PyMuPDF releases before 1.24.3 only offer the legacy name
            mod, _ = _try_import(module)
            reason = reason if mod is None else None
        if mod is None:
            result[name] = {"status": "unavailable", "reason": reason}
            continue
        top, _ = _try_import(module.split(".")[0])
        version = getattr(top, "__version__", None) or getattr(top, "VersionBind", None)
        result[name] = {"status": "available", "version": str(version) if version else None}
    return result


# --------------------------------------------------------------------------
# Plain-text adapters: path -> list of page strings
# --------------------------------------------------------------------------

def _extract_pdftotext(path: str) -> list[str]:
    proc = subprocess.run([_pdftotext_binary(), "-enc", "UTF-8", path, "-"],
                          capture_output=True, timeout=PDFTOTEXT_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "pdftotext failed")
    pages = proc.stdout.decode("utf-8", "replace").split("\f")
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]
    return pages


def _extract_pdfminer(path: str) -> list[str]:
    from pdfminer.high_level import extract_text
    from pdfminer.pdfpage import PDFPage
    with open(path, "rb") as fh:
        count = sum(1 for _ in PDFPage.get_pages(fh))
    return [extract_text(path, page_numbers=[i]) for i in range(count)]


def _extract_pypdf(path: str) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    return [page.extract_text() or "" for page in reader.pages]


def _pymupdf():
    """Import PyMuPDF under its current name, falling back to the legacy one."""
    mod, _ = _try_import("pymupdf")
    return mod if mod is not None else importlib.import_module("fitz")


def _extract_pymupdf(path: str) -> list[str]:
    fitz = _pymupdf()
    with fitz.open(path) as doc:
        return [page.get_text("text") for page in doc]


def _extract_pdfplumber(path: str) -> list[str]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


_ADAPTERS = {
    "pdftotext": _extract_pdftotext,
    "pdfminer": _extract_pdfminer,
    "pypdf": _extract_pypdf,
    "pymupdf": _extract_pymupdf,
    "pdfplumber": _extract_pdfplumber,
}


def extract(name: str, path: str) -> list[str]:
    """Run one extractor. Raises on failure; the caller records the error."""
    return _ADAPTERS[name](path)


# --------------------------------------------------------------------------
# Layout adapters: positioned fragments
# --------------------------------------------------------------------------

@dataclass
class Fragment:
    page: int          # 1-based
    x0: float          # points from the left edge
    x1: float          # right edge (estimated where the source gives no width)
    top: float         # points from the top edge (baseline for pypdf)
    size: float        # effective font size in points
    text: str
    font: str = ""
    artifact: str | None = None  # "Header", "Footer", "Artifact" or None


@dataclass
class PageLayout:
    page: int
    width: float
    height: float
    fragments: list = field(default_factory=list)


# heuristic, chosen because: average glyph advance of Latin text fonts is
# about half the font size; only used to estimate a right edge where pypdf
# reports the start point of a text chunk but not its width.
AVG_GLYPH_WIDTH_EM = 0.5


def _mat_mult(m, n):
    """Multiply two PDF matrices [a b c d e f]."""
    return [
        m[0] * n[0] + m[1] * n[2],
        m[0] * n[1] + m[1] * n[3],
        m[2] * n[0] + m[3] * n[2],
        m[2] * n[1] + m[3] * n[3],
        m[4] * n[0] + m[5] * n[2] + n[4],
        m[4] * n[1] + m[5] * n[3] + n[5],
    ]


def _artifact_kind(operands) -> str | None:
    """Return the artifact kind for BDC/BMC operands, or None if not an artifact."""
    if not operands:
        return None
    tag = str(operands[0]).lstrip("/")
    if tag != "Artifact":
        return None
    props = operands[1] if len(operands) > 1 else None
    try:
        subtype = props.get("/Subtype") if hasattr(props, "get") else None
    except Exception:  # noqa: BLE001 - properties may be a name resource
        subtype = None
    return str(subtype).lstrip("/") if subtype else "Artifact"


def layout_pypdf(path: str) -> list[PageLayout]:
    """Positioned text chunks via pypdf's extract_text visitor callbacks."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        left, bottom = float(box.left), float(box.bottom)
        layout = PageLayout(index, width, height)
        tag_stack: list = []

        def before(op, operands, cm, tm, _stack=tag_stack):
            if op in (b"BDC", b"BMC"):
                _stack.append(_artifact_kind(operands))
            elif op == b"EMC" and _stack:
                _stack.pop()

        def visit(text, cm, tm, font_dict, font_size, _layout=layout, _stack=tag_stack):
            if not text or not text.strip():
                return
            m = _mat_mult(list(tm), list(cm))
            scale = math.hypot(m[2], m[3]) or 1.0
            size = abs(float(font_size or 0) * scale)
            x = m[4] - left
            y_top = height - (m[5] - bottom)
            kind = next((k for k in reversed(_stack) if k), None)
            font = ""
            if font_dict is not None and hasattr(font_dict, "get"):
                font = str(font_dict.get("/BaseFont", "")).lstrip("/")
            for line in text.split("\n"):
                if line.strip():
                    _layout.fragments.append(Fragment(
                        index, x, x + len(line) * size * AVG_GLYPH_WIDTH_EM, y_top,
                        size, line, font, kind))

        page.extract_text(visitor_operand_before=before, visitor_text=visit)
        pages.append(layout)
    return pages


def layout_pdfplumber(path: str) -> list[PageLayout]:
    """Positioned words via pdfplumber (exact boxes, no artifact tags)."""
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            layout = PageLayout(index, float(page.width), float(page.height))
            for w in page.extract_words(extra_attrs=["size", "fontname"]):
                layout.fragments.append(Fragment(
                    index, float(w["x0"]), float(w["x1"]), float(w["top"]),
                    float(w["size"]), w["text"], w.get("fontname", "")))
            pages.append(layout)
    return pages


def layout_pymupdf(path: str) -> list[PageLayout]:
    """Positioned spans via PyMuPDF (exact boxes, no artifact tags)."""
    fitz = _pymupdf()
    pages = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            layout = PageLayout(index, float(page.rect.width), float(page.rect.height))
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():
                            x0, y0, x1, _ = span["bbox"]
                            layout.fragments.append(Fragment(
                                index, x0, x1, y0, float(span["size"]),
                                span["text"], span.get("font", "")))
            pages.append(layout)
    return pages


# Preferred order for the coordinate source. pdfplumber and PyMuPDF report
# exact word/span boxes; pypdf only reports chunk start points.
LAYOUT_ORDER = (("pdfplumber", layout_pdfplumber),
                ("pymupdf", layout_pymupdf),
                ("pypdf", layout_pypdf))


# --------------------------------------------------------------------------
# PDF structure via pypdf: fonts, link annotations, graphics
# --------------------------------------------------------------------------

_STANDARD_14 = {
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}  # PDF 32000-1:2008, 9.6.2.2 "Standard Type 1 Fonts"

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _font_info(font) -> dict:
    font = _resolve(font)
    subtype = str(font.get("/Subtype", "")).lstrip("/")
    base = str(font.get("/BaseFont", font.get("/Name", ""))).lstrip("/")
    descriptor = font.get("/FontDescriptor")
    if subtype == "Type0":
        descendants = _resolve(font.get("/DescendantFonts"))
        if descendants:
            descriptor = _resolve(descendants[0]).get("/FontDescriptor")
    descriptor = _resolve(descriptor) if descriptor is not None else None
    embedded = subtype == "Type3" or bool(descriptor is not None and any(
        k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3")))
    clean = _SUBSET_PREFIX.sub("", base)
    return {
        "name": base,
        "subtype": subtype,
        "embedded": embedded,
        "standard14": clean in _STANDARD_14,
        "to_unicode": "/ToUnicode" in font,
    }


@dataclass
class Graphics:
    rects: list = field(default_factory=list)       # (x0, top, x1, bottom, filled)
    hlines: list = field(default_factory=list)      # (x0, x1, y_top)
    vlines: list = field(default_factory=list)      # (x, top0, top1)
    images: list = field(default_factory=list)      # (x0, top, x1, bottom)
    path_paints: int = 0
    curve_ops: int = 0
    text_ops: int = 0


# heuristic, chosen because: table rules and underlines in office exports are
# 0.25-1.5 pt thick; a filled rect thinner than this is treated as a line.
THIN_RECT_PT = 2.0

# heuristic, chosen because: a drawn rule deviates from horizontal/vertical
# by far less than half a point; glyph edges and diagonals exceed it.
AXIS_TOLERANCE_PT = 0.5

_PAINT_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"S", b"s"}
_FILL_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_TEXT_SHOW_OPS = {b"Tj", b"TJ", b"'", b'"'}

# heuristic, chosen because: nested Form XObjects deeper than this do not
# occur in CV exports; the limit stops reference cycles.
MAX_XOBJECT_DEPTH = 8


def _walk_content(reader, content, resources, ctm, height, g: Graphics, depth=0):
    from pypdf.generic import ContentStream
    if depth > MAX_XOBJECT_DEPTH or content is None:
        return
    try:
        stream = content if isinstance(content, ContentStream) else ContentStream(content, reader)
        ops = stream.operations
    except Exception:  # noqa: BLE001 - damaged stream: count nothing
        return
    stack = []
    path_pts: list = []
    path_rects: list = []
    current = None

    def tx(x, y):
        return (ctm[0] * x + ctm[2] * y + ctm[4], ctm[1] * x + ctm[3] * y + ctm[5])

    for operands, op in ops:
        if op == b"q":
            stack.append(list(ctm))
        elif op == b"Q":
            if stack:
                ctm = stack.pop()
        elif op == b"cm":
            ctm = _mat_mult([float(v) for v in operands], ctm)
        elif op == b"re":
            x, y, w, h = (float(v) for v in operands)
            p0, p1 = tx(x, y), tx(x + w, y + h)
            path_rects.append((min(p0[0], p1[0]), max(p0[1], p1[1]),
                               max(p0[0], p1[0]), min(p0[1], p1[1])))
        elif op == b"m":
            current = tx(float(operands[0]), float(operands[1]))
        elif op == b"l":
            nxt = tx(float(operands[0]), float(operands[1]))
            if current is not None:
                path_pts.append((current, nxt))
            current = nxt
        elif op in (b"c", b"v", b"y"):
            g.curve_ops += 1
            current = tx(float(operands[-2]), float(operands[-1]))
        elif op in _PAINT_OPS or op == b"n":
            if op != b"n":
                g.path_paints += 1
                filled = op in _FILL_OPS
                for (x0, y0, x1, y1) in path_rects:
                    w, h = x1 - x0, y0 - y1
                    top, bottom = height - y0, height - y1
                    if h <= THIN_RECT_PT and w > THIN_RECT_PT:
                        g.hlines.append((x0, x1, (top + bottom) / 2))
                    elif w <= THIN_RECT_PT and h > THIN_RECT_PT:
                        g.vlines.append(((x0 + x1) / 2, top, bottom))
                    else:
                        g.rects.append((x0, top, x1, bottom, filled))
                        if not filled:
                            g.hlines += [(x0, x1, top), (x0, x1, bottom)]
                            g.vlines += [(x0, top, bottom), (x1, top, bottom)]
                for (a, b) in path_pts:
                    if abs(a[1] - b[1]) < AXIS_TOLERANCE_PT and abs(a[0] - b[0]) > THIN_RECT_PT:
                        g.hlines.append((min(a[0], b[0]), max(a[0], b[0]), height - a[1]))
                    elif abs(a[0] - b[0]) < AXIS_TOLERANCE_PT and abs(a[1] - b[1]) > THIN_RECT_PT:
                        g.vlines.append((a[0], height - max(a[1], b[1]), height - min(a[1], b[1])))
            path_pts, path_rects, current = [], [], None
        elif op in _TEXT_SHOW_OPS:
            g.text_ops += 1
        elif op == b"BI" or op == b"INLINE IMAGE":
            p0, p1 = tx(0, 0), tx(1, 1)
            g.images.append((min(p0[0], p1[0]), height - max(p0[1], p1[1]),
                             max(p0[0], p1[0]), height - min(p0[1], p1[1])))
        elif op == b"Do":
            xobjects = _resolve(resources.get("/XObject", {})) if resources else {}
            xobj = xobjects.get(operands[0]) if xobjects else None
            if xobj is None:
                continue
            xobj = _resolve(xobj)
            subtype = xobj.get("/Subtype")
            if subtype == "/Image":
                p0, p1 = tx(0, 0), tx(1, 1)
                g.images.append((min(p0[0], p1[0]), height - max(p0[1], p1[1]),
                                 max(p0[0], p1[0]), height - min(p0[1], p1[1])))
            elif subtype == "/Form":
                matrix = [float(v) for v in xobj.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                sub_res = _resolve(xobj.get("/Resources", resources))
                _walk_content(reader, xobj, sub_res, _mat_mult(matrix, ctm), height, g, depth + 1)


def _collect_fonts(resources, seen: dict, depth=0):
    if resources is None or depth > MAX_XOBJECT_DEPTH:
        return
    resources = _resolve(resources)
    fonts = _resolve(resources.get("/Font", {})) or {}
    for key in fonts:
        ref = fonts.raw_get(key) if hasattr(fonts, "raw_get") else fonts[key]
        ident = getattr(ref, "idnum", None) or id(_resolve(ref))
        if ident not in seen:
            seen[ident] = _font_info(fonts[key])
    xobjects = _resolve(resources.get("/XObject", {})) or {}
    for key in xobjects:
        xobj = _resolve(xobjects[key])
        if xobj.get("/Subtype") == "/Form" and "/Resources" in xobj:
            _collect_fonts(xobj["/Resources"], seen, depth + 1)


def structure_pypdf(path: str) -> dict:
    """Fonts, link URIs and graphics per page, via pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    fonts: dict = {}
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        box = page.mediabox
        height = float(box.height)
        _collect_fonts(page.get("/Resources"), fonts)
        uris = []
        for annot in _resolve(page.get("/Annots", [])) or []:
            annot = _resolve(annot)
            action = _resolve(annot.get("/A", {})) or {}
            if annot.get("/Subtype") == "/Link" and "/URI" in action:
                uris.append(str(action["/URI"]))
        g = Graphics()
        origin = [1, 0, 0, 1, -float(box.left), -float(box.bottom)]
        _walk_content(reader, page.get_contents(), _resolve(page.get("/Resources")),
                      origin, height, g)
        pages.append({"page": index, "width": float(box.width), "height": height,
                      "uris": uris, "graphics": g})
    return {"fonts": list(fonts.values()), "pages": pages,
            "pdf_version": getattr(reader, "pdf_header", None)}

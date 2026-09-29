#!/usr/bin/env python3
"""ats-check: measure what text extractors read from a CV PDF and emit JSON.

Usage:
    python analyze.py <cv.pdf> [--job <job-ad.txt>] [--out <result.json>]

Deterministic: same file and same set of available extractors give the same
JSON. No network access, nothing is written except --out (default: stdout).
The JSON schema is documented in ../references/checks.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extractors as ex  # noqa: E402

SCHEMA_VERSION = "1.0"
TOOL_VERSION = "0.1.0"

# Source ids used in findings. Mirrors references/sources.md (a test keeps the
# two in sync). "status" is the verification state at build time; see
# sources.md for why every source is UNVERIFIED.
SOURCES = {
    "greenhouse_parse": {
        "title": "Greenhouse Support: Unsuccessful resume parse",
        "url": "https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse",
        "status": "UNVERIFIED",
    },
    "ba_lebenslauf": {
        "title": "Bundesagentur für Arbeit: Lebenslauf",
        "url": "https://www.arbeitsagentur.de/bildung/bewerbung/lebenslauf",
        "status": "UNVERIFIED",
    },
}

# Every finding id the script can emit: (group, evidence_type).
# Groups: A extraction, B structure, C content, D relevance.
# Documented in references/checks.md (a test keeps the two in sync).
FINDING_CATALOGUE = {
    "no_extractor": ("A", "measured"),
    "text_is_image": ("A", "measured"),
    "text_is_outlines": ("A", "measured"),
    "text_layer_missing": ("A", "measured"),
    "extractor_disagreement": ("A", "measured"),
    "reading_order_mixed": ("A", "measured"),
    "missing_spaces": ("A", "measured"),
    "garbage_chars": ("A", "measured"),
    "ligatures_in_text": ("A", "measured"),
    "font_type3": ("A", "measured"),
    "font_not_embedded": ("A", "measured"),
    "font_size_small": ("A", "heuristic"),
    "contact_missing": ("B", "measured"),
    "contact_only_in_links": ("B", "measured"),
    "contact_in_header_footer": ("B", "documented"),
    "sections_missing": ("B", "heuristic"),
    "dates_not_found": ("B", "heuristic"),
    "dates_inconsistent": ("B", "heuristic"),
    "table_detected": ("B", "documented"),
    "images_present": ("B", "documented"),
    "file_size_over_limit": ("B", "documented"),
    "page_count_high": ("B", "documented"),
    "letter_spacing": ("B", "documented"),
    "bullets_without_evidence": ("C", "heuristic"),
    "adjectives_without_evidence": ("C", "heuristic"),
    "skill_bars": ("C", "heuristic"),
    "icon_images": ("C", "heuristic"),
    "profile_missing": ("C", "heuristic"),
    "profile_too_long": ("C", "heuristic"),
}

# ---------------------------------------------------------------------------
# Thresholds. Every number has its origin next to it.
# ---------------------------------------------------------------------------

# Brief: "die ersten ca. 40 Zeilen des Extrakts".
PREVIEW_LINES = 40

# heuristic, chosen because: a CV page with body text carries well over 1000
# non-space characters; below 100 a page has at most a name or a few labels,
# so the visible content must be image or vector outlines.
TEXT_LAYER_MIN_CHARS_PER_PAGE = 100

# heuristic, chosen because: outlined text consists of one filled path per
# glyph or word; a page of vector-only content with fewer paint operations
# than this is more likely decoration (lines, boxes) than text.
OUTLINE_MIN_PATH_PAINTS = 50

# heuristic, chosen because: extractors differ by a few percent through
# hyphenation, bullets and whitespace handling; below 80 % shared tokens at
# least one of them reads materially different text.
AGREEMENT_MIN_RATIO = 0.80

# heuristic, chosen because: German compounds in CVs rarely exceed about
# 25 letters ("Softwareentwicklungsprojekte" has 28); longer tokens are
# usually several words glued together by missing spaces.
LONG_TOKEN_CHARS = 30

# heuristic, chosen because: one or two long tokens can be a genuine long
# compound or an identifier; three or more point to a systematic problem.
LONG_TOKEN_MIN_COUNT = 3

# heuristic, chosen because: at least four letters separated by single
# spaces ("E r f a") do not occur in normal prose or in CV abbreviations.
LETTER_SPACING_MIN_LETTERS = 4

# heuristic, chosen because: fragments on the same visual line differ by less
# than 2 pt in their top coordinate; lines of body text are 10 pt or more
# apart at typical CV font sizes.
ROW_TOLERANCE_PT = 2.0

# heuristic, chosen because: the space between words is about 0.25 em
# (~3 pt at 11 pt); a gap above 12 pt separates independent text segments.
SEGMENT_GAP_PT = 12.0

# heuristic, chosen because: column gutters in CV templates are 18 pt or more;
# tab stops inside a single column are usually closer to the text they align.
COLUMN_GAP_MIN_PT = 18.0

# heuristic, chosen because: a sidebar layout places many rows side by side;
# five rows exclude isolated cases such as a name with a date on one line.
COLUMN_MIN_SHARED_ROWS = 5

# heuristic, chosen because: if at least 60 % of one side's segments are dates
# or short labels, the layout is a label/value list (tabular CV), where
# row-by-row reading is the intended order.
LABEL_SIDE_MIN_SHARE = 0.60

# heuristic, chosen because: one extracted line with tokens of both columns
# can come from a heading spanning the gutter; two or more are systematic.
MIXED_LINES_MIN = 2

# heuristic, chosen because: reading two columns one after the other switches
# between them once, plus one or two more where a heading or wrapped line is
# attributed to the other side; four or more switches mean the extractor
# alternates between the columns line by line.
INTERLEAVE_MIN_SWITCHES = 4

# heuristic, chosen because: tokens shorter than 3 letters ("in", "at", "&")
# appear in both columns and cannot tell them apart.
DISTINCT_TOKEN_MIN_CHARS = 3

# heuristic, chosen because: a ruled table needs a top rule, a separator and a
# bottom rule, and at least three vertical rules (two borders, one divider).
TABLE_MIN_HLINES = 3
TABLE_MIN_VLINES = 3

# heuristic, chosen because: rule endpoints of office exports are aligned to
# within about 1 pt.
TABLE_TOLERANCE_PT = 1.5

# A rule belongs to a grid when it meets at least two perpendicular rules
# (its two ends); by definition of a ruled grid, not a tuned value.
TABLE_MIN_CROSSINGS = 2

# Numerical tolerance for comparing interval ends in the gutter sweep; far
# below any layout distance, only guards float rounding.
SWEEP_EPSILON_PT = 0.01

# heuristic, chosen because: table cells are wider than 30 pt and rows taller
# than 10 pt, while straight glyph edges (hyphen, 'l', 'I') of outlined text
# stay below both at CV font sizes.
TABLE_MIN_HRULE_PT = 30.0
TABLE_MIN_VRULE_PT = 10.0

# heuristic, chosen because: labels in label/value layouts are one or two
# words followed by a colon ("E-Mail:", "Geburtsdatum:").
LABEL_MAX_WORDS = 2

# heuristic, chosen because: contact icons are drawn at text size (8-20 pt);
# 24 pt separates them from photos and logos.
ICON_MAX_PT = 24.0

# heuristic, chosen because: header and footer text of office templates sits
# within the outer 10 % of the page height.
ZONE_FRACTION = 0.10

# A header or footer repeats; a row counts as one when it appears in the
# zone on at least two pages. Definition, not a tuned value.
ZONE_MIN_PAGES = 2

# Greenhouse Support, "Unsuccessful resume parse": no parse above 2.5 MB
# (source status: see SOURCES["greenhouse_parse"]). 1 MB taken as 1024*1024.
FILE_SIZE_LIMIT_BYTES = int(2.5 * 1024 * 1024)

# Bundesagentur für Arbeit, "Lebenslauf": one to at most two pages
# (source status: see SOURCES["ba_lebenslauf"]).
PAGE_LIMIT = 2

# heuristic, chosen because: below 8 pt printed CV text becomes hard to read,
# and some parsers drop very small text as fine print.
SMALL_FONT_PT = 8.0

# heuristic, chosen because: text of fewer than 3 letters in small type is
# usually a superscript, page number or icon label.
SMALL_FONT_MIN_LETTERS = 3

# heuristic, chosen because: with fewer than three bullets the share of
# unsupported bullets says little about the CV.
BULLETS_MIN_COUNT = 3

# heuristic, chosen because: if at least half the bullets lack any number,
# scope or result, the pattern is systematic rather than incidental.
BULLETS_UNSUPPORTED_MIN_SHARE = 0.50

# heuristic, chosen because: one or two soft-skill adjectives are normal;
# three or more without support read as a list.
ADJECTIVES_MIN_COUNT = 3

# heuristic, chosen because: a format used once can be a typo or a special
# case (e.g. a single certificate date); two uses make it a pattern.
DATE_FORMAT_MIN_USES = 2

# Brief: "Profiltext ... länger als etwa 4 Zeilen" (heuristic).
PROFILE_MAX_LINES = 4

# heuristic, chosen because: level bars are 2-14 pt high and 20-250 pt wide;
# thinner shapes are rules, taller ones are boxes or photos.
SKILL_BAR_MIN_H, SKILL_BAR_MAX_H = 2.0, 14.0
SKILL_BAR_MIN_W, SKILL_BAR_MAX_W = 20.0, 250.0

# heuristic, chosen because: three aligned bars make a level scale; one or two
# can be decoration.
SKILL_BARS_MIN_COUNT = 3

# heuristic, chosen because: bars in one scale share their left edge within
# 2 pt.
SKILL_BAR_ALIGN_PT = 2.0

# heuristic, chosen because: a CV rarely lists more than a few dozen
# evidence items; longer lists bloat the JSON without helping the report.
MAX_LISTED_ITEMS = 15

# heuristic, chosen because: job ads contain 150-600 distinct content words;
# 300 keeps the term list complete for typical ads and bounded for long ones.
MAX_JOB_TERMS = 300

# heuristic, chosen because: five sample lines show the pattern of a
# reading-order problem without repeating the whole page.
MAX_SAMPLE_LINES = 5

# heuristic, chosen because: 30 characters on each side show the word and
# its neighbours; 15 are enough around a single word.
CONTEXT_CHARS = 30
WORD_CONTEXT_CHARS = 15

# heuristic, chosen because: job-ad words shorter than 3 characters are
# function words; short technical terms ("C#", "C++") are kept by their sign.
JOB_TERM_MIN_CHARS = 3

# heuristic, chosen because: two example lines per term are enough to judge
# whether a term is supported or only named.
MAX_LINES_PER_TERM = 2

# ---------------------------------------------------------------------------
# Character classes and dictionaries
# ---------------------------------------------------------------------------

_PUA = re.compile("[-]")                 # Unicode Private Use Area (BMP)
_REPLACEMENT = "�"                               # U+FFFD REPLACEMENT CHARACTER
_CID = re.compile(r"\(cid:\d+\)")                    # pdfminer's marker for unmapped glyphs
_LIGATURE = re.compile("[ﬀ-ﬆ]")            # Alphabetic Presentation Forms, Latin ligatures
_TOKEN = re.compile(r"\S+")
_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_LETTER = r"[^\W\d_]"
# N letters = (N - 1) letters each followed by a space, then one more letter.
_SPACED = re.compile(r"(?<!\S)(?:%s ){%d,}%s(?!\S)" % (_LETTER, LETTER_SPACING_MIN_LETTERS - 1, _LETTER))

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com|xing\.com)/\S+", re.I)
# Pre-selection only ("{5,}" just requires some length); the digit count is
# checked against PHONE_MIN_DIGITS/PHONE_MAX_DIGITS below.
_PHONE = re.compile(r"(?<![\w/(])\(?(?:\+|00|0)\d[\d \t/().-]{5,}\d")
# Phone numbers have 7 to 15 digits (ITU-T E.164 allows at most 15).
PHONE_MIN_DIGITS, PHONE_MAX_DIGITS = 7, 15

_BULLET = re.compile("^\\s*([•●▪■◦‣∙·–—*\\-])\\s*(.*)$")

_MONTHS = (r"jan(?:uar|uary)?|feb(?:ruar|ruary)?|m(?:ä|ae)rz|mar(?:ch)?|apr(?:il)?|mai|may|"
           r"jun[ie]?|jul[iy]?|aug(?:ust)?|sep(?:t(?:ember)?)?|o[ck]t(?:ober)?|nov(?:ember)?|"
           r"de[cz](?:ember)?")
_DATE_FORMATS = {
    "MM/YYYY": re.compile(r"(?<![\d/.])(?:0[1-9]|1[0-2])/(?:19|20)\d{2}(?![\d/])"),
    "MM.YYYY": re.compile(r"(?<![\d.])(?:0[1-9]|1[0-2])\.(?:19|20)\d{2}(?![\d.])"),
    "YYYY-MM": re.compile(r"(?<![\d-])(?:19|20)\d{2}-(?:0[1-9]|1[0-2])(?![\d-])"),
    "Month YYYY": re.compile(r"\b(?:%s)\.?\s+(?:19|20)\d{2}\b" % _MONTHS, re.I),
    "DD.MM.YYYY": re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}(?![\d.])"),
}
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_DATE_LIKE = re.compile(r"(?:19|20)\d{2}|\b(?:heute|present|today|seit|since)\b", re.I)

SECTION_HEADINGS = {
    "profile": ["profil", "kurzprofil", "über mich", "zusammenfassung", "profile", "summary",
                "professional summary", "about me", "personal statement", "career summary"],
    "experience": ["berufserfahrung", "erfahrung", "berufliche erfahrung", "beruflicher werdegang",
                   "werdegang", "praxiserfahrung", "berufspraxis", "experience", "work experience",
                   "professional experience", "employment history", "work history", "employment",
                   "career history"],
    "education": ["ausbildung", "bildung", "bildungsweg", "schulbildung", "studium",
                  "akademische ausbildung", "education", "academic background", "qualifications"],
    "skills": ["kenntnisse", "fähigkeiten", "kompetenzen", "fachkenntnisse", "it-kenntnisse",
               "edv-kenntnisse", "skills", "technical skills", "core competencies", "competencies",
               "key skills"],
    "languages": ["sprachen", "sprachkenntnisse", "languages"],
    "certifications": ["zertifikate", "zertifizierungen", "weiterbildung", "weiterbildungen",
                       "certifications", "certificates", "training"],
    "projects": ["projekte", "projects"],
    "interests": ["interessen", "hobbys", "hobbies", "interests"],
}
REQUIRED_SECTIONS = ("experience", "education", "skills")
# heuristic, chosen because: section headings are short; a line of more than
# five words is body text even if it starts with a heading word.
HEADING_MAX_WORDS = 5

# Words that state a result (a digit, %, or currency sign also counts).
# Scope is only counted when quantified (any digit), so the list holds result
# verbs only: "Betreuung von Kunden" names a task, "120 Kunden" a scope.
EVIDENCE_WORDS = {
    "reduziert", "reduzierte", "gesenkt", "senkte", "gesteigert", "steigerte", "erhöht",
    "erhöhte", "verbessert", "verbesserte", "verkürzt", "verkürzte", "eingespart", "gespart",
    "gewonnen", "reduced", "cut", "increased", "improved", "grew", "saved", "shortened",
    "won", "doubled", "halved", "tripled", "verdoppelt", "halbiert",
}
SOFT_ADJECTIVES = {
    "teamfähig", "teamfähigkeit", "motiviert", "hochmotiviert", "kreativ", "belastbar",
    "belastbarkeit", "zuverlässig", "zuverlässigkeit", "flexibel", "flexibilität",
    "kommunikativ", "kommunikationsstark", "engagiert", "zielorientiert", "ergebnisorientiert",
    "selbstständig", "selbständig", "strukturiert", "lernbereit", "lernbereitschaft",
    "dynamisch", "leidenschaftlich", "organisiert", "sorgfältig", "proaktiv",
    "motivated", "creative", "hard-working", "hardworking", "detail-oriented", "reliable",
    "flexible", "passionate", "self-motivated", "dynamic", "team-player", "proactive",
    "results-driven", "dedicated", "enthusiastic", "organized", "organised",
}
LEVEL_WORDS = {
    "grundkenntnisse", "gut", "gute", "sehr", "fließend", "verhandlungssicher", "muttersprache",
    "experte", "expertin", "fortgeschritten", "basic", "intermediate", "advanced", "expert",
    "fluent", "native", "proficient", "a1", "a2", "b1", "b2", "c1", "c2",
}
STOPWORDS = {
    # German
    "und", "oder", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "einer", "mit", "für", "von", "vom", "zum", "zur", "bei", "auf", "aus", "als", "wie", "sie",
    "wir", "ihr", "ihre", "ihren", "ihrer", "unser", "unsere", "unseren", "unserem", "sich",
    "ist", "sind", "wird", "werden", "haben", "hast", "hat", "sowie", "auch", "nach", "über",
    "unter", "durch", "gerne", "gern", "idealerweise", "bereits", "mehr", "sehr", "gute",
    "guten", "gutes", "erste", "ersten", "dich", "dein", "deine", "deinen", "du", "bist",
    "nicht", "kein", "keine", "alle", "allem", "neue", "neuen", "jahre", "jahren", "etc",
    # generic job-ad words (no requirement on their own)
    "suchen", "suche", "bieten", "bietet", "erwarten", "freuen", "erfahrung", "kenntnisse",
    # English
    "and", "the", "for", "with", "you", "your", "our", "are", "will", "from", "that", "this",
    "have", "has", "who", "what", "about", "into", "their", "they", "them", "can", "all",
    "any", "etc", "able", "strong", "good", "plus", "including", "such", "other", "per",
    "years", "year",
    # generic job-ad words (no requirement on their own)
    "looking", "offer", "seeking", "experience", "knowledge",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(fid, group, severity, evidence_type, message, page=None, area="document",
             source_id=None, rationale=None, evidence=None):
    if FINDING_CATALOGUE.get(fid) != (group, evidence_type):
        raise ValueError(f"finding {fid} does not match FINDING_CATALOGUE")
    if evidence_type == "documented" and source_id not in SOURCES:
        raise ValueError(f"documented finding {fid} needs a known source_id")
    if evidence_type == "heuristic" and not rationale:
        raise ValueError(f"heuristic finding {fid} needs a rationale")
    item = {
        "id": fid,
        "group": group,
        "severity": severity,
        "evidence_type": evidence_type,
        "message": message,
        "location": {"page": page, "area": area},
        "source_id": source_id,
    }
    if source_id:
        item["source_status"] = SOURCES[source_id]["status"]
    if rationale:
        item["rationale"] = rationale
    if evidence is not None:
        item["evidence"] = evidence
    return item


def _nonspace(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in _WORD.findall(text)]


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines()]


def _context(text: str, start: int, end: int, width: int = CONTEXT_CHARS) -> str:
    """Return the text around a match, on one line."""
    return text[max(0, start - width):end + width].replace("\n", " ⏎ ")


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch) == "Cc" and ch not in "\n\r\t\f"


# ---------------------------------------------------------------------------
# A: extraction
# ---------------------------------------------------------------------------

def run_extractors(path: str) -> tuple[dict, dict]:
    """Return (status per extractor, page texts per working extractor)."""
    status = ex.probe()
    texts = {}
    for name in ex.EXTRACTOR_ORDER:
        if status[name]["status"] != "available":
            continue
        try:
            pages = ex.extract(name, path)
        except Exception as exc:  # noqa: BLE001 - reported, never hidden
            status[name] = {**status[name], "status": "error",
                            "reason": f"{type(exc).__name__}: {exc}"}
            continue
        texts[name] = pages
        status[name] = {**status[name], "status": "ok",
                        "chars_per_page": [_nonspace(p) for p in pages]}
    return status, texts


def choose_primary(texts: dict) -> str | None:
    for name in ex.EXTRACTOR_ORDER:
        if name in texts and any(_nonspace(p) for p in texts[name]):
            return name
    return next((n for n in ex.EXTRACTOR_ORDER if n in texts), None)


def check_text_layer(texts: dict, structure: dict | None, page_count: int) -> list:
    findings = []
    for i in range(page_count):
        best = max((_nonspace(pages[i]) for pages in texts.values() if i < len(pages)), default=0)
        if best >= TEXT_LAYER_MIN_CHARS_PER_PAGE:
            continue
        cause, evidence = "unknown", {"max_chars_on_page": best}
        if structure:
            g = structure["pages"][i]["graphics"]
            page_area = structure["pages"][i]["width"] * structure["pages"][i]["height"]
            image_area = sum((x1 - x0) * (b - t) for x0, t, x1, b in g.images)
            evidence.update({"images": len(g.images), "path_paint_ops": g.path_paints,
                             "curve_ops": g.curve_ops,
                             "image_area_share": round(image_area / page_area, 3) if page_area else 0})
            if g.images:
                cause = "image"
            elif g.path_paints >= OUTLINE_MIN_PATH_PAINTS:
                cause = "outlines"
        if cause == "image":
            findings.append(_finding(
                "text_is_image", "A", "P0", "measured",
                f"Page {i + 1} has almost no extractable text ({best} characters) but contains "
                "image(s): the visible text is part of an image. A parser reads nothing here.",
                page=i + 1, area="page", evidence=evidence))
        elif cause == "outlines":
            findings.append(_finding(
                "text_is_outlines", "A", "P0", "measured",
                f"Page {i + 1} has almost no extractable text ({best} characters) but "
                f"{evidence['path_paint_ops']} vector paint operations: the text was converted to "
                "outlines (shapes). A parser reads nothing here.",
                page=i + 1, area="page", evidence=evidence))
        else:
            findings.append(_finding(
                "text_layer_missing", "A", "P0", "measured",
                f"Page {i + 1} has almost no extractable text ({best} characters).",
                page=i + 1, area="page", evidence=evidence))
    return findings


def agreement(texts: dict) -> dict:
    """Pairwise share of shared word tokens (order-independent)."""
    bags = {n: Counter(_tokens("\n".join(p))) for n, p in texts.items()}
    result = {}
    names = [n for n in ex.EXTRACTOR_ORDER if n in bags]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            total = max(sum(bags[a].values()), sum(bags[b].values()))
            shared = sum((bags[a] & bags[b]).values())
            result[f"{a}~{b}"] = round(shared / total, 3) if total else 1.0
    return result


def check_agreement(pairs: dict, text_layer_missing_everywhere: bool) -> list:
    if text_layer_missing_everywhere:
        return []
    low = {k: v for k, v in pairs.items() if v < AGREEMENT_MIN_RATIO}
    if not low:
        return []
    return [_finding(
        "extractor_disagreement", "A", "P1", "measured",
        "Text extractors read materially different text from this file (shared tokens below "
        f"{AGREEMENT_MIN_RATIO:.0%} for: " + ", ".join(f"{k} {v:.0%}" for k, v in sorted(low.items()))
        + "). Which result an ATS gets depends on its parser.",
        evidence={"pairs_below_threshold": low, "all_pairs": pairs})]


def check_characters(texts: dict) -> list:
    findings = []
    garbage, ligatures, long_tokens, spaced = {}, {}, {}, {}
    for name, pages in texts.items():
        g_items, l_items, t_items, s_items = [], [], [], []
        for pno, text in enumerate(pages, start=1):
            for m in _PUA.finditer(text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                at_line_start = text[line_start:m.start()].strip() == ""
                g_items.append({"page": pno, "char": f"U+{ord(m.group()):04X}",
                                "kind": "private_use", "line_start": at_line_start,
                                "context": _context(text, m.start(), m.end())})
            for idx, ch in enumerate(text):
                if ch == _REPLACEMENT or _is_control(ch):
                    g_items.append({"page": pno, "char": f"U+{ord(ch):04X}",
                                    "kind": "replacement" if ch == _REPLACEMENT else "control",
                                    "line_start": False, "context": _context(text, idx, idx + 1)})
            for m in _CID.finditer(text):
                g_items.append({"page": pno, "char": m.group(), "kind": "unmapped_glyph",
                                "line_start": False, "context": _context(text, m.start(), m.end())})
            for m in _LIGATURE.finditer(text):
                l_items.append({"page": pno, "char": f"U+{ord(m.group()):04X}",
                                "context": _context(text, m.start(), m.end(), WORD_CONTEXT_CHARS)})
            for m in _TOKEN.finditer(text):
                tok = m.group()
                if (len(tok) >= LONG_TOKEN_CHARS and not _EMAIL.search(tok)
                        and not _URL.search(tok)):
                    t_items.append({"page": pno, "token": tok})
            for m in _SPACED.finditer(text):
                s_items.append({"page": pno, "text": m.group()})
        if g_items:
            garbage[name] = g_items
        if l_items:
            ligatures[name] = l_items
        if len(t_items) >= LONG_TOKEN_MIN_COUNT:
            long_tokens[name] = t_items
        if s_items:
            spaced[name] = s_items

    if garbage:
        all_items = [i for items in garbage.values() for i in items]
        only_bullets = all(i["line_start"] for i in all_items)
        kinds = sorted({i["kind"] for i in all_items})
        first = next(iter(garbage.values()))
        findings.append(_finding(
            "garbage_chars", "A", "P2" if only_bullets else "P1", "measured",
            f"Extracted text contains characters without meaning ({', '.join(kinds)}) in: "
            f"{', '.join(sorted(garbage))}. Typical cause: icon fonts (e.g. envelope or phone "
            "symbols) or symbol-font bullets. A parser sees placeholder characters there"
            + (" (here only at line starts, i.e. bullets)." if only_bullets else
               ", which can break contact details and keywords."),
            page=first[0]["page"], area="line starts (bullets)" if only_bullets else "inline text",
            evidence={n: items[:MAX_LISTED_ITEMS] for n, items in sorted(garbage.items())}))
    if ligatures:
        first = next(iter(ligatures.values()))
        findings.append(_finding(
            "ligatures_in_text", "A", "P1", "measured",
            "Extracted text contains ligature characters (U+FB00-FB06, e.g. 'ﬁ' instead of "
            f"'fi') in: {', '.join(sorted(ligatures))}. Keyword search for words containing "
            "fi/fl/ff can fail on this text.",
            page=first[0]["page"], area="inline text",
            evidence={n: items[:MAX_LISTED_ITEMS] for n, items in sorted(ligatures.items())}))
    if long_tokens:
        first = next(iter(long_tokens.values()))
        findings.append(_finding(
            "missing_spaces", "A", "P1", "measured",
            f"Words run together without spaces ({LONG_TOKEN_CHARS}+ characters per token) in: "
            f"{', '.join(sorted(long_tokens))}. Keywords inside such tokens are not found.",
            page=first[0]["page"], area="inline text",
            evidence={n: items[:MAX_LISTED_ITEMS] for n, items in sorted(long_tokens.items())}))
    if spaced:
        first = next(iter(spaced.values()))
        findings.append(_finding(
            "letter_spacing", "B", "P1", "documented",
            "Letter-spaced text is extracted as separate letters (e.g. "
            f"'{first[0]['text']}') in: {', '.join(sorted(spaced))}. Parsers do not recognise "
            "the letters as one word, so headings like this are not found.",
            page=first[0]["page"], area="headings", source_id="greenhouse_parse",
            evidence={n: items[:MAX_LISTED_ITEMS] for n, items in sorted(spaced.items())}))
    return findings


def check_fonts(structure: dict | None, layouts) -> tuple[list, dict]:
    findings = []
    info = {"fonts": structure["fonts"] if structure else None, "smallest_size_pt": None}
    if structure:
        type3 = [f for f in structure["fonts"] if f["subtype"] == "Type3"]
        if type3:
            no_map = [f["name"] for f in type3 if not f["to_unicode"]]
            findings.append(_finding(
                "font_type3", "A", "P1" if no_map else "P2", "measured",
                f"{len(type3)} Type3 font(s) found (glyphs drawn as procedures, typical of some "
                "design-tool exports). "
                + (f"{len(no_map)} of them have no ToUnicode map, so their text may not "
                   "extract as readable characters." if no_map else
                   "All have a ToUnicode map; extraction depends on that map being correct."),
                area="fonts", evidence={"fonts": [f["name"] for f in type3],
                                        "without_to_unicode": no_map}))
        missing = [f["name"] for f in structure["fonts"]
                   if not f["embedded"] and not f["standard14"] and f["subtype"] != "Type3"]
        if missing:
            findings.append(_finding(
                "font_not_embedded", "A", "P2", "measured",
                f"{len(missing)} font(s) are not embedded: {', '.join(missing)}. Text extraction "
                "is unaffected when the font has a standard encoding, but the file may look "
                "different on the recruiter's screen.",
                area="fonts", evidence={"fonts": missing}))
    if layouts:
        sizes = [f.size for page in layouts for f in page.fragments
                 if len(re.findall(_LETTER, f.text)) >= SMALL_FONT_MIN_LETTERS and f.size > 0]
        if sizes:
            smallest = round(min(sizes), 1)
            info["smallest_size_pt"] = smallest
            small = [f for page in layouts for f in page.fragments
                     if 0 < f.size < SMALL_FONT_PT
                     and len(re.findall(_LETTER, f.text)) >= SMALL_FONT_MIN_LETTERS]
            if small:
                findings.append(_finding(
                    "font_size_small", "A", "P2", "heuristic",
                    f"Text below {SMALL_FONT_PT:g} pt found (smallest {smallest} pt).",
                    page=small[0].page, area="text",
                    rationale="Small print is hard to read for recruiters and some parsers "
                              "discard very small text as fine print; the threshold is a rule "
                              "of thumb, not a documented parser limit.",
                    evidence={"samples": [{"page": f.page, "size": round(f.size, 1),
                                           "text": f.text} for f in small[:MAX_LISTED_ITEMS]]}))
    return findings, info


# ---------------------------------------------------------------------------
# Layout: rows, columns, tables, reading order
# ---------------------------------------------------------------------------

def _rows(fragments) -> list[list]:
    """Group fragments into visual rows, each sorted left to right."""
    rows: list[list] = []
    for frag in sorted(fragments, key=lambda f: (f.top, f.x0)):
        if rows and abs(rows[-1][0].top - frag.top) <= ROW_TOLERANCE_PT:
            rows[-1].append(frag)
        else:
            rows.append([frag])
    return [sorted(r, key=lambda f: f.x0) for r in rows]


def _segments(row) -> list[dict]:
    """Merge the fragments of a row into segments separated by wide gaps."""
    segs = []
    for frag in row:
        if segs and frag.x0 - segs[-1]["x1"] <= SEGMENT_GAP_PT:
            segs[-1]["x1"] = max(segs[-1]["x1"], frag.x1)
            segs[-1]["text"] += " " + frag.text
            segs[-1]["frags"].append(frag)
        else:
            segs.append({"x0": frag.x0, "x1": frag.x1, "text": frag.text, "frags": [frag]})
    return segs


def _is_label(text: str) -> bool:
    t = text.strip()
    return bool(_DATE_LIKE.search(t)) or (len(t.split()) <= LABEL_MAX_WORDS and t.endswith(":"))


def detect_tables(graphics) -> list[tuple]:
    """Return bounding boxes (x0, top, x1, bottom) of ruled tables."""
    tol = TABLE_TOLERANCE_PT

    def hits(h, v):
        return (h[0] - tol <= v[0] <= h[1] + tol) and (v[1] - tol <= h[2] <= v[2] + tol)

    hlines = [h for h in graphics.hlines if h[1] - h[0] >= TABLE_MIN_HRULE_PT]
    vlines = [v for v in graphics.vlines if v[2] - v[1] >= TABLE_MIN_VRULE_PT]
    grid_h = [h for h in hlines if sum(1 for v in vlines if hits(h, v)) >= TABLE_MIN_CROSSINGS]
    grid_v = [v for v in vlines if sum(1 for h in grid_h if hits(h, v)) >= TABLE_MIN_CROSSINGS]
    distinct_h = {round(h[2]) for h in grid_h}
    distinct_v = {round(v[0]) for v in grid_v}
    if len(distinct_h) < TABLE_MIN_HLINES or len(distinct_v) < TABLE_MIN_VLINES:
        return []
    return [(min(h[0] for h in grid_h), min(h[2] for h in grid_h),
             max(h[1] for h in grid_h), max(h[2] for h in grid_h))]


def _inside(frag, box) -> bool:
    x0, top, x1, bottom = box
    tol = TABLE_TOLERANCE_PT
    return x0 - tol <= frag.x0 <= x1 + tol and top - frag.size <= frag.top <= bottom + frag.size


def detect_columns(layout, tables) -> dict | None:
    """Find a vertical gutter shared by many rows. None if there is none."""
    frags = [f for f in layout.fragments if not any(_inside(f, t) for t in tables)]
    rows = _rows(frags)
    intervals = []  # (gap_start, gap_end, row_index)
    row_segments = []
    for idx, row in enumerate(rows):
        segs = _segments(row)
        row_segments.append(segs)
        for a, b in zip(segs, segs[1:]):
            if b["x0"] - a["x1"] >= COLUMN_GAP_MIN_PT:
                intervals.append((a["x1"], b["x0"], idx))
    if not intervals:
        return None
    # Sweep for the x position covered by the most gap intervals.
    events = sorted([(s, 1) for s, _, _ in intervals] + [(e, -1) for _, e, _ in intervals],
                    key=lambda t: (t[0], -t[1]))
    best, best_x, cur = 0, None, 0
    for x, delta in events:
        cur += delta
        if cur > best:
            best, best_x = cur, x
    eps = SWEEP_EPSILON_PT
    shared_rows = sorted({r for s, e, r in intervals if s <= best_x + eps and e >= best_x - eps})
    # Place the boundary in the middle of the narrowest common gap.
    lo = max(s for s, e, r in intervals if r in shared_rows and s <= best_x + eps)
    hi = min(e for s, e, r in intervals if r in shared_rows and e >= best_x - eps)
    boundary = (lo + hi) / 2 if hi > lo else best_x
    if len(shared_rows) < COLUMN_MIN_SHARED_ROWS:
        return None
    left_segs, right_segs = [], []
    for idx in shared_rows:
        for seg in row_segments[idx]:
            (left_segs if seg["x1"] <= boundary else right_segs).append(seg)
    for side in (left_segs, right_segs):
        if side and sum(_is_label(s["text"]) for s in side) / len(side) >= LABEL_SIDE_MIN_SHARE:
            return None  # label/value layout (dates or labels beside text)
    top = rows[shared_rows[0]][0].top
    bottom = rows[shared_rows[-1]][0].top
    return {"page": layout.page, "count": 2, "boundary_x": round(boundary, 1),
            "shared_rows": len(shared_rows), "top": round(top, 1), "bottom": round(bottom, 1)}


def measure_mixing(fragments, columns: dict, page_text: str) -> dict:
    """Count extracted lines that contain words of both columns.

    Only rows inside the two-column band count. A token is "distinct" when it
    occurs on one side only. A line mixes the columns when it holds at least
    one distinct token of each side.
    """
    left, right = Counter(), Counter()
    for f in fragments:
        if not (columns["top"] - ROW_TOLERANCE_PT <= f.top <= columns["bottom"] + ROW_TOLERANCE_PT):
            continue
        target = left if f.x0 < columns["boundary_x"] else right
        for tok in _tokens(f.text):
            if len(tok) >= DISTINCT_TOKEN_MIN_CHARS:
                target[tok] += 1
    only_left = set(left) - set(right)
    only_right = set(right) - set(left)
    mixed, sequence = [], []
    for line in _lines(page_text):
        toks = set(_tokens(line))
        has_left, has_right = bool(toks & only_left), bool(toks & only_right)
        if has_left and has_right:
            mixed.append(line.strip())
        elif has_left or has_right:
            side = "L" if has_left else "R"
            if not sequence or sequence[-1][0] != side:
                sequence.append((side, line.strip()))
    switches = max(len(sequence) - 1, 0)
    return {"mixed_lines": len(mixed), "samples": mixed[:MAX_SAMPLE_LINES],
            "column_switches": switches,
            "switch_samples": [text for _, text in sequence[:MAX_SAMPLE_LINES]]}


def _mixes(result: dict) -> bool:
    return (result["mixed_lines"] >= MIXED_LINES_MIN
            or result["column_switches"] >= INTERLEAVE_MIN_SWITCHES)


def check_reading_order(layouts, texts: dict, tables_by_page: dict) -> tuple[list, list]:
    findings, columns_info = [], []
    if not layouts:
        return findings, columns_info
    for layout in layouts:
        cols = detect_columns(layout, tables_by_page.get(layout.page, []))
        if not cols:
            continue
        per_extractor = {}
        for name, pages in texts.items():
            if layout.page - 1 < len(pages):
                per_extractor[name] = measure_mixing(layout.fragments, cols, pages[layout.page - 1])
        cols["mixing"] = per_extractor
        columns_info.append(cols)
        mixing = {n: r for n, r in per_extractor.items() if _mixes(r)}
        if mixing:
            clean = sorted(set(per_extractor) - set(mixing))
            how = []
            joined = sorted(n for n, r in mixing.items() if r["mixed_lines"] >= MIXED_LINES_MIN)
            alternating = sorted(n for n, r in mixing.items()
                                 if r["column_switches"] >= INTERLEAVE_MIN_SWITCHES)
            if joined:
                how.append(f"{', '.join(joined)} join(s) text of both columns into one line")
            if alternating:
                how.append(f"{', '.join(alternating)} alternate(s) between the columns line by line")
            findings.append(_finding(
                "reading_order_mixed", "A", "P1", "measured",
                f"Page {layout.page} has two columns side by side, and the reading order is "
                f"mixed: {'; '.join(how)}"
                + (f" ({', '.join(clean)} kept the columns apart)." if clean else ".")
                + " A parser doing the same assigns details to the wrong section.",
                page=layout.page, area="two-column area",
                evidence={n: r for n, r in sorted(mixing.items())}))
    return findings, columns_info


def column_ordered_text(layout, columns: dict) -> str:
    """Rebuild a page's text with the two columns one after the other.

    Rows above and below the two-column band keep their order; inside the
    band all left-column text comes first, then all right-column text.
    """
    before, left, right, after = [], [], [], []
    for row in _rows(layout.fragments):
        top = row[0].top
        if top < columns["top"] - ROW_TOLERANCE_PT:
            before.append(" ".join(f.text for f in row))
        elif top > columns["bottom"] + ROW_TOLERANCE_PT:
            after.append(" ".join(f.text for f in row))
        else:
            lpart = " ".join(f.text for f in row if f.x0 < columns["boundary_x"])
            rpart = " ".join(f.text for f in row if f.x0 >= columns["boundary_x"])
            if lpart:
                left.append(lpart)
            if rpart:
                right.append(rpart)
    return "\n".join(before + left + right + after)


def check_tables_images(structure: dict | None) -> tuple[list, dict]:
    findings, tables_by_page = [], {}
    if not structure:
        return findings, tables_by_page
    for p in structure["pages"]:
        g = p["graphics"]
        tables = detect_tables(g)
        if tables:
            tables_by_page[p["page"]] = tables
    if tables_by_page:
        first = min(tables_by_page)
        findings.append(_finding(
            "table_detected", "B", "P2", "documented",
            f"Ruled table found on page(s) {', '.join(map(str, sorted(tables_by_page)))}. "
            "Parsers can read table cells in the wrong order or skip them.",
            page=first, area="table", source_id="greenhouse_parse",
            evidence={str(k): [[round(v, 1) for v in box] for box in boxes]
                      for k, boxes in sorted(tables_by_page.items())}))
    large = [(p["page"], img) for p in structure["pages"] for img in p["graphics"].images
             if (img[2] - img[0]) > ICON_MAX_PT or (img[3] - img[1]) > ICON_MAX_PT]
    if large:
        findings.append(_finding(
            "images_present", "B", "P2", "documented",
            f"{len(large)} image(s) found (photo, logo or graphic). Text inside images is not "
            "extracted; images also enlarge the file.",
            page=large[0][0], area="images", source_id="greenhouse_parse",
            evidence={"images": [{"page": pg, "bbox": [round(v, 1) for v in img]}
                                 for pg, img in large[:MAX_LISTED_ITEMS]]}))
    return findings, tables_by_page


# ---------------------------------------------------------------------------
# B: structure
# ---------------------------------------------------------------------------

def _phones(text: str) -> list[str]:
    out = []
    for m in _PHONE.finditer(text):
        cand = m.group().strip()
        digits = re.sub(r"\D", "", cand)
        if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
            continue
        if any(rx.search(cand) for rx in _DATE_FORMATS.values()) or _YEAR.fullmatch(cand):
            continue  # contains a date such as 01.2019 or 03/2020, not a phone number
        if re.search(r"(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}", cand):
            continue  # a date range, not a phone number
        out.append(cand)
    return out


def _contact_items(text: str) -> dict:
    return {"email": sorted(set(_EMAIL.findall(text))),
            "phone": sorted(set(_phones(text))),
            "url": sorted(set(u.rstrip(".,;)") for u in _URL.findall(text)))}


def _zone_rows(layouts) -> tuple[str, str]:
    """Return (text of recurring header/footer rows, text of all other rows)."""
    per_page = []
    for layout in layouts:
        rows = []
        for row in _rows(layout.fragments):
            text = " ".join(f.text for f in row)
            top = row[0].top
            zone = top < layout.height * ZONE_FRACTION or top > layout.height * (1 - ZONE_FRACTION)
            rows.append((zone, text))
        per_page.append(rows)
    seen = Counter()
    for rows in per_page:
        for key in {re.sub(r"\d+", "#", t.strip()) for z, t in rows if z}:
            seen[key] += 1
    zone_text, body_text = [], []
    for rows in per_page:
        for zone, text in rows:
            key = re.sub(r"\d+", "#", text.strip())
            (zone_text if zone and seen[key] >= ZONE_MIN_PAGES else body_text).append(text)
    return "\n".join(zone_text), "\n".join(body_text)


def _merge_items(primary: dict, other: dict) -> dict:
    """Add items only other extractors found, unless they extend a known one
    (e.g. a URL glued to the next word by an extractor that lost a line break)."""
    merged = {k: list(v) for k, v in primary.items()}
    for kind, values in other.items():
        for value in sorted(values, key=len):
            if not any(value.startswith(v) or v.startswith(value) for v in merged[kind]):
                merged[kind].append(value)
        merged[kind].sort()
    return merged


def check_contact(texts: dict, primary: str | None, layouts, pypdf_layouts, structure) -> tuple[list, dict]:
    findings = []
    all_text = "\n".join("\n".join(p) for p in texts.values())
    found = _contact_items("\n".join(texts[primary]) if primary else "")
    for name in ex.EXTRACTOR_ORDER:
        if name in texts and name != primary:
            found = _merge_items(found, _contact_items("\n".join(texts[name])))
    uris = [u for p in (structure["pages"] if structure else []) for u in p["uris"]]
    link_items = {
        "email": sorted({u[7:].split("?")[0] for u in uris if u.lower().startswith("mailto:")}),
        "phone": sorted({u[4:] for u in uris if u.lower().startswith("tel:")}),
        "url": sorted({u for u in uris if u.lower().startswith(("http://", "https://"))}),
    }
    artifact_text = ""
    body_text_pypdf = None
    if pypdf_layouts:
        artifact_text = "\n".join(f.text for p in pypdf_layouts for f in p.fragments if f.artifact)
        body_text_pypdf = "\n".join(f.text for p in pypdf_layouts for f in p.fragments if not f.artifact)
    zone_text, body_text = _zone_rows(layouts) if layouts else ("", all_text)

    def in_body(item: str) -> bool:
        def has(text):
            return item in text or item.replace(" ", "") in text.replace(" ", "")
        if body_text_pypdf is not None and not has(body_text_pypdf):
            return False
        return has(body_text)

    status = {}
    for kind in ("email", "phone", "url"):
        entries = []
        for item in found[kind]:
            where = "body" if in_body(item) else (
                "header_footer" if (item in artifact_text or item in zone_text) else "body")
            entries.append({"value": item, "where": where})
        for item in link_items[kind]:
            normal = item.replace("https://", "").replace("http://", "").rstrip("/")
            if not any(normal.lower() in e["value"].lower() or e["value"].lower() in normal.lower()
                       for e in entries):
                entries.append({"value": item, "where": "link_only"})
        status[kind] = entries

    text_hits = [e for k in ("email", "phone") for e in status[k] if e["where"] != "link_only"]
    body_hits = [e for e in text_hits if e["where"] == "body"]
    link_only = [e for k in ("email", "phone") for e in status[k] if e["where"] == "link_only"]
    if not text_hits and not link_only:
        findings.append(_finding(
            "contact_missing", "B", "P0", "measured",
            "No e-mail address and no phone number found in the extracted text. A parser cannot "
            "fill in the candidate's contact details.", area="contact block"))
    elif not text_hits and link_only:
        findings.append(_finding(
            "contact_only_in_links", "B", "P1", "measured",
            "E-mail or phone exist only as link targets (clickable icons or words), not as "
            "visible text. Parsers read the text, so they find no contact details: "
            + ", ".join(e["value"] for e in link_only) + ".",
            area="contact block", evidence={"link_only": link_only}))
    elif not body_hits:
        findings.append(_finding(
            "contact_in_header_footer", "B", "P1", "documented",
            "Contact details appear only in the page header/footer zone ("
            + ", ".join(e["value"] for e in text_hits)
            + "). Some parsers ignore headers and footers.",
            area="header/footer zone", source_id="greenhouse_parse",
            evidence={"items": text_hits}))
    elif link_only and not any(e["where"] == "body" for e in status["email"]):
        findings.append(_finding(
            "contact_only_in_links", "B", "P1", "measured",
            "The e-mail address exists only as a link target, not as visible text: "
            + ", ".join(e["value"] for e in link_only) + ".",
            area="contact block", evidence={"link_only": link_only}))
    return findings, status


def find_sections(text: str) -> dict:
    found = {}
    for no, line in enumerate(_lines(text)):
        norm = re.sub(r"[^\w\s&/-]", "", line.strip().casefold()).strip()
        if not norm or len(norm.split()) > HEADING_MAX_WORDS:
            continue
        for canon, variants in SECTION_HEADINGS.items():
            if canon in found:
                continue
            if any(norm == v or norm.startswith(v + " ") or norm.endswith(" " + v) for v in variants):
                found[canon] = {"line": no, "text": line.strip()}
    return found


def check_sections(text: str) -> tuple[list, dict]:
    sections = find_sections(text)
    missing = [s for s in REQUIRED_SECTIONS if s not in sections]
    findings = []
    if missing:
        findings.append(_finding(
            "sections_missing", "B", "P1" if "experience" in missing else "P2", "heuristic",
            f"No recognisable heading for: {', '.join(missing)}. Found: "
            f"{', '.join(sorted(sections)) or 'none'}.",
            area="section headings",
            rationale="Parsers segment a CV by its headings; conventional headings (e.g. "
                      "'Berufserfahrung'/'Experience') are matched most reliably. The heading "
                      "dictionary (DE/EN) is in references/checks.md.",
            evidence={"found": sections, "missing": missing}))
    return findings, sections


def check_dates(text: str) -> tuple[list, dict]:
    counts = {name: len(rx.findall(text)) for name, rx in _DATE_FORMATS.items()}
    years = len(_YEAR.findall(text))
    info = {"formats": {k: v for k, v in counts.items() if v}, "years": years}
    findings = []
    if years == 0:
        findings.append(_finding(
            "dates_not_found", "B", "P2", "heuristic",
            "No years found in the extracted text, so no period of employment or study can be "
            "read.", area="dates",
            rationale="Parsers compute durations of experience from start and end dates; "
                      "without dates this cannot work."))
    month_level = {k: v for k, v in counts.items()
                   if k != "DD.MM.YYYY" and v >= DATE_FORMAT_MIN_USES}
    if len(month_level) > 1:
        findings.append(_finding(
            "dates_inconsistent", "B", "P2", "heuristic",
            "Several month/year formats are mixed: "
            + ", ".join(f"{k} ({v}x)" for k, v in month_level.items()) + ".",
            area="dates",
            rationale="One consistent format such as MM/YYYY is the easiest for date parsing; "
                      "mixed formats raise the chance that one of them is misread.",
            evidence=info))
    return findings, info


def check_file(path: str, page_count: int) -> list:
    findings = []
    size = os.path.getsize(path)
    if size > FILE_SIZE_LIMIT_BYTES:
        findings.append(_finding(
            "file_size_over_limit", "B", "P1", "documented",
            f"The file is {size / 1024 / 1024:.1f} MB. Greenhouse documents that it does not "
            "parse resumes above 2.5 MB; other systems may have similar limits.",
            area="file", source_id="greenhouse_parse",
            evidence={"size_bytes": size, "limit_bytes": FILE_SIZE_LIMIT_BYTES}))
    if page_count > PAGE_LIMIT:
        findings.append(_finding(
            "page_count_high", "B", "P2", "documented",
            f"The CV has {page_count} pages. The Bundesagentur für Arbeit recommends one to at "
            "most two pages (a note, not a parsing problem).",
            area="document", source_id="ba_lebenslauf",
            evidence={"pages": page_count, "recommended_max": PAGE_LIMIT}))
    return findings


# ---------------------------------------------------------------------------
# C: content (heuristic)
# ---------------------------------------------------------------------------

def _bullets(text: str, headings: set) -> list[str]:
    bullets, current = [], None
    for line in _lines(text):
        m = _BULLET.match(line)
        if m and m.group(2).strip():
            if current:
                bullets.append(current)
            current = m.group(2).strip()
        elif current and line.strip() and line.strip() not in headings:
            if line.strip()[0].islower():  # continuation of a wrapped bullet
                current += " " + line.strip()
            else:
                bullets.append(current)
                current = None
        elif current:
            bullets.append(current)
            current = None
    if current:
        bullets.append(current)
    return bullets


def _has_evidence(text: str) -> bool:
    if re.search(r"\d", text) or re.search(r"[%€$£]", text):
        return True
    return bool(set(_tokens(text)) & EVIDENCE_WORDS)


def check_content(text: str, sections: dict, structure, layouts) -> list:
    findings = []
    headings = {v["text"] for v in sections.values()}
    bullets = _bullets(text, headings)
    unsupported = [b for b in bullets if not _has_evidence(b)]
    if len(bullets) >= BULLETS_MIN_COUNT and len(unsupported) / len(bullets) >= BULLETS_UNSUPPORTED_MIN_SHARE:
        findings.append(_finding(
            "bullets_without_evidence", "C", "P2", "heuristic",
            f"{len(unsupported)} of {len(bullets)} bullet points contain no number, scope or "
            "result; they describe tasks, not outcomes.",
            area="bullet points",
            rationale="Recruiters and relevance ranking both favour statements that can be "
                      "checked (numbers, scope, results); the evidence word list is in "
                      "references/checks.md.",
            evidence={"bullets": unsupported[:MAX_LISTED_ITEMS], "total_bullets": len(bullets)}))

    adjectives = []
    for line in _lines(text):
        if _has_evidence(line):
            continue
        for tok in _tokens(line):
            if tok in SOFT_ADJECTIVES and tok not in adjectives:
                adjectives.append(tok)
    if len(adjectives) >= ADJECTIVES_MIN_COUNT:
        findings.append(_finding(
            "adjectives_without_evidence", "C", "P2", "heuristic",
            f"Self-descriptions without support: {', '.join(adjectives)}.",
            area="text",
            rationale="Adjectives like 'motivated' or 'teamfähig' carry no checkable "
                      "information; an example with scope or result does.",
            evidence={"adjectives": adjectives}))

    if "profile" not in sections:
        findings.append(_finding(
            "profile_missing", "C", "P2", "heuristic",
            "No profile/summary section found.", area="top of CV",
            rationale="A short profile of 2-4 lines states target role and core skills in the "
                      "recruiter's first seconds and gives relevance ranking a dense summary."))
    else:
        lines = _lines(text)
        start = sections["profile"]["line"] + 1
        later = sorted(v["line"] for v in sections.values() if v["line"] > sections["profile"]["line"])
        end = later[0] if later else len(lines)
        body = [ln for ln in lines[start:end] if ln.strip()]
        if len(body) > PROFILE_MAX_LINES:
            findings.append(_finding(
                "profile_too_long", "C", "P2", "heuristic",
                f"The profile runs to {len(body)} lines (more than about {PROFILE_MAX_LINES}).",
                area="profile",
                rationale="A long profile is skimmed or skipped; the value of a profile is its "
                          "density.",
                evidence={"lines": len(body)}))

    if structure and layouts:
        findings += _check_skill_bars(structure, layouts)
        icons = [(p["page"], img) for p in structure["pages"] for img in p["graphics"].images
                 if (img[2] - img[0]) <= ICON_MAX_PT and (img[3] - img[1]) <= ICON_MAX_PT]
        if len(icons) >= SKILL_BARS_MIN_COUNT:
            findings.append(_finding(
                "icon_images", "C", "P2", "heuristic",
                f"{len(icons)} small icon images found. Icons are invisible to a parser; where "
                "an icon replaces a label (phone, e-mail, location), the information is lost.",
                page=icons[0][0], area="icons",
                rationale="Icons carry no text; whether they replace a label cannot be measured "
                          "reliably, so this is flagged as a rule of thumb.",
                evidence={"count": len(icons)}))
    return findings


def _check_skill_bars(structure, layouts) -> list:
    by_page = {lay.page: lay for lay in layouts}
    groups = []
    for p in structure["pages"]:
        bars = [r for r in p["graphics"].rects if r[4]
                and SKILL_BAR_MIN_H <= r[3] - r[1] <= SKILL_BAR_MAX_H
                and SKILL_BAR_MIN_W <= r[2] - r[0] <= SKILL_BAR_MAX_W]
        by_x: dict = {}
        for bar in bars:
            key = next((k for k in by_x if abs(k - bar[0]) <= SKILL_BAR_ALIGN_PT), bar[0])
            by_x.setdefault(key, [])
            if not any(abs(b[1] - bar[1]) <= SKILL_BAR_ALIGN_PT for b in by_x[key]):
                by_x[key].append(bar)  # a track and its fill count once
        for x, group in by_x.items():
            if len(group) >= SKILL_BARS_MIN_COUNT:
                groups.append((p["page"], group))
    findings = []
    for page, group in groups:
        layout = by_page.get(page)
        labels, has_level = [], False
        for bar in group:
            mid = (bar[1] + bar[3]) / 2
            near = [f for f in (layout.fragments if layout else [])
                    if abs(f.top + f.size / 2 - mid) <= max(f.size, SKILL_BAR_MAX_H)
                    or (0 <= bar[1] - (f.top + f.size) <= SKILL_BAR_MAX_H and abs(f.x0 - bar[0]) <= SKILL_BAR_MAX_W)]
            row_text = " ".join(f.text for f in near)
            labels.append(row_text.strip())
            if re.search(r"\d", row_text) or set(_tokens(row_text)) & LEVEL_WORDS:
                has_level = True
        if not has_level:
            findings.append(_finding(
                "skill_bars", "C", "P2", "heuristic",
                f"{len(group)} level bars found; the level they show exists only as a graphic. "
                "A parser sees the skill names without any level.",
                page=page, area="skills",
                rationale="Bars are shapes, not text. Whether a level matters for a job is "
                          "a judgement, so this is flagged as a rule of thumb.",
                evidence={"labels": labels[:MAX_LISTED_ITEMS]}))
    return findings


# ---------------------------------------------------------------------------
# D: relevance (raw material only; the skill does the judging)
# ---------------------------------------------------------------------------

_TERM = re.compile(r"[A-Za-zÄÖÜäöüß][\w+#./-]*[\w+#]|[A-Za-z]\+\+|C#|\.NET", re.UNICODE)


def relevance(job_text: str, cv_text: str) -> dict:
    cv_lines = [ln.strip() for ln in _lines(cv_text) if ln.strip()]
    cv_fold = cv_text.casefold()
    terms, seen = [], set()
    for m in _TERM.finditer(job_text):
        term = m.group().strip("./-")
        key = term.casefold()
        if len(key) < JOB_TERM_MIN_CHARS and not re.search(r"[+#]", key):
            continue
        if key in STOPWORDS or key in seen or key.isdigit():
            continue
        seen.add(key)
        pattern = re.compile(r"(?<![\w+#])" + re.escape(key) + r"(?![\w+#])")
        count = len(pattern.findall(cv_fold))
        lines = [ln for ln in cv_lines if pattern.search(ln.casefold())][:MAX_LINES_PER_TERM]
        terms.append({"term": term, "in_cv": count > 0, "count": count, "cv_lines": lines})
        if len(terms) >= MAX_JOB_TERMS:
            break
    return {"job_text": job_text, "terms": terms,
            "terms_found": sum(t["in_cv"] for t in terms), "terms_total": len(terms)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze(path: str, job_text: str | None = None) -> dict:
    status, texts = run_extractors(path)
    skipped = []

    structure = None
    if status.get("pypdf", {}).get("status") == "ok":
        try:
            structure = ex.structure_pypdf(path)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"checks": "fonts, tables, images, links, outlines",
                            "reason": f"pypdf structure parse failed: {type(exc).__name__}: {exc}"})
    else:
        skipped.append({"checks": "fonts, tables, images, link annotations, outline detection, "
                                  "skill bars, header/footer artifact tags",
                        "reason": "pypdf unavailable"})

    layouts, layout_source = None, None
    for name, fn in ex.LAYOUT_ORDER:
        if status.get(name, {}).get("status") != "ok":
            continue
        try:
            layouts, layout_source = fn(path), name
            break
        except Exception as exc:  # noqa: BLE001
            skipped.append({"checks": f"layout via {name}", "reason": f"{type(exc).__name__}: {exc}"})
    if layouts is None:
        skipped.append({"checks": "reading order, columns, font sizes, header/footer zone",
                        "reason": "no coordinate-capable extractor (pdfplumber, pymupdf, pypdf) ran"})
    pypdf_layouts = None
    if status.get("pypdf", {}).get("status") == "ok":
        pypdf_layouts = layouts if layout_source == "pypdf" else None
        if pypdf_layouts is None:
            try:
                pypdf_layouts = ex.layout_pypdf(path)
            except Exception as exc:  # noqa: BLE001
                skipped.append({"checks": "header/footer artifact tags",
                                "reason": f"{type(exc).__name__}: {exc}"})

    page_count = (len(structure["pages"]) if structure else
                  max((len(p) for p in texts.values()), default=0))
    primary = choose_primary(texts)
    primary_text = "\n".join(texts[primary]) if primary else ""

    findings = []
    content_source = primary
    if not texts:
        result_findings = [_finding(
            "no_extractor", "A", "P0", "measured",
            "No text extractor could read this file; see 'extractors' for the reasons.")]
        return _assemble(path, status, primary, primary_text, page_count, layout_source,
                         [], None, None, None, None, None, result_findings, skipped, job_text)

    text_layer = check_text_layer(texts, structure, page_count)
    findings += text_layer
    missing_everywhere = len(text_layer) == page_count and page_count > 0
    pairs = agreement(texts)
    findings += check_agreement(pairs, missing_everywhere)
    findings += check_characters(texts)
    font_findings, font_info = check_fonts(structure, layouts)
    findings += font_findings
    table_findings, tables_by_page = check_tables_images(structure)
    findings += table_findings
    order_findings, columns = check_reading_order(layouts, texts, tables_by_page)
    findings += order_findings
    findings += check_file(path, page_count)
    if not missing_everywhere:
        contact_findings, contact = check_contact(texts, primary, layouts, pypdf_layouts, structure)
        findings += contact_findings
        section_findings, sections = check_sections(primary_text)
        findings += section_findings
        date_findings, dates = check_dates(primary_text)
        findings += date_findings
        # Content checks judge the wording, so they must not read text that an
        # extractor has mixed across columns. Pages where the primary
        # extractor mixes are rebuilt column by column from the coordinates.
        content_pages = list(texts[primary])
        by_page = {lay.page: lay for lay in layouts or []}
        for cols in columns:
            if _mixes(cols["mixing"].get(primary, {"mixed_lines": 0, "column_switches": 0})):
                content_pages[cols["page"] - 1] = column_ordered_text(by_page[cols["page"]], cols)
                content_source = f"{layout_source} coordinates, columns separated on mixed pages"
        content_text = "\n".join(content_pages)
        findings += check_content(content_text, find_sections(content_text), structure, layouts)
    else:
        contact = sections = dates = None
        skipped.append({"checks": "contact, sections, dates, content",
                        "reason": "no text layer on any page"})

    return _assemble(path, status, primary, primary_text, page_count, layout_source, columns,
                     pairs, font_info, contact, sections, dates, findings, skipped, job_text,
                     content_source)


# Sort keys for findings (ranks, not thresholds).
_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_GROUP_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def _assemble(path, status, primary, primary_text, page_count, layout_source, columns, pairs,
              font_info, contact, sections, dates, findings, skipped, job_text,
              content_source=None):
    findings = sorted(findings, key=lambda f: (_SEVERITY_ORDER[f["severity"]],
                                               _GROUP_ORDER[f["group"]], f["id"]))
    lines = _lines(primary_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "ats-check", "version": TOOL_VERSION},
        "file": {"name": os.path.basename(path), "size_bytes": os.path.getsize(path),
                 "pages": page_count},
        "extractors": status,
        "primary_extractor": primary,
        "preview": {"extractor": primary, "lines": lines[:PREVIEW_LINES],
                    "total_lines": len(lines)},
        "layout": {"coordinate_source": layout_source, "columns": columns or []},
        "agreement": pairs,
        "fonts": font_info,
        "contact": contact,
        "sections": sections,
        "dates": dates,
        "findings": findings,
        "summary": {
            "P0": sum(f["severity"] == "P0" for f in findings),
            "P1": sum(f["severity"] == "P1" for f in findings),
            "P2": sum(f["severity"] == "P2" for f in findings),
        },
        "skipped_checks": skipped,
        "sources": SOURCES,
        "text": {"extractor": primary, "full": primary_text,
                 "content_checks_source": content_source},
        "relevance": relevance(job_text, primary_text) if job_text is not None else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", help="path to the CV (PDF)")
    parser.add_argument("--job", help="path to a text file with the job ad (optional)")
    parser.add_argument("--out", help="write JSON here instead of stdout")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.pdf):
        parser.error(f"not a file: {args.pdf}")
    job_text = None
    if args.job:
        with open(args.job, encoding="utf-8", errors="replace") as fh:
            job_text = fh.read()
    result = analyze(args.pdf, job_text)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

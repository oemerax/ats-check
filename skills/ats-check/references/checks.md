# Checks and JSON schema

`scripts/analyze.py` writes one JSON object. This file explains every field
and every check. Thresholds are named constants in `scripts/analyze.py`
(and `scripts/extractors.py`); each has a comment giving its origin. They
are quoted here by name, so the code stays the single place for the value.

## Evidence types

| Label | Meaning | What the report may say |
|---|---|---|
| `measured` | Measured on this PDF: extracted text, coordinates, fonts, file size. | "The file shows …" |
| `documented` | An ATS vendor or public authority documents the effect. `source_id` points to `references/sources.md`. | "Greenhouse documents …" and, when `source_status` is `UNVERIFIED`, "(source not verified)". |
| `heuristic` | A rule of thumb. `rationale` says why. | "Assessment: …" and never as a fact. |

A `documented` finding is *detected* by measurement, too. The label says
why the detected property matters: a source documents it.

## Severity

| Severity | Meaning |
|---|---|
| `P0` | A parser probably gets no text or loses core data (name, contact, experience). |
| `P1` | Data is probably mis-assigned, partly lost, or not searchable. |
| `P2` | Advisory: smaller risk or a question of quality. |

## Top-level JSON

| Field | Type | Content |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `tool` | object | `name`, `version` |
| `file` | object | `name`, `size_bytes`, `pages` |
| `extractors` | object | Per extractor (`pdftotext`, `pdfminer`, `pypdf`, `pymupdf`, `pdfplumber`): `status` is `ok`, `unavailable` (with `reason`) or `error` (with `reason`); also `version`, `chars_per_page`. |
| `primary_extractor` | string or null | The first extractor with text, in the fixed order `EXTRACTOR_ORDER`. It is not a claim about any ATS. |
| `preview` | object | `extractor`, `lines` (first `PREVIEW_LINES` lines of the primary text), `total_lines` |
| `layout` | object | `coordinate_source` (pdfplumber, pymupdf or pypdf) and `columns`: one entry per page with two columns: `page`, `boundary_x`, `shared_rows`, `top`, `bottom`, and `mixing` per extractor (`mixed_lines`, `column_switches`, samples). |
| `agreement` | object | Pairwise share of shared word tokens, e.g. `"pdftotext~pypdf": 0.98`. |
| `fonts` | object | `fonts` (name, subtype, embedded, standard14, to_unicode) and `smallest_size_pt`. |
| `contact` | object | For `email`, `phone`, `url`: a list of `{value, where}`. `where` is `body`, `header_footer` or `link_only`. |
| `sections` | object | Recognised headings: canonical name → `{line, text}`. |
| `dates` | object | `formats` (format → count), `years`. |
| `findings` | array | See below. Sorted by severity, then group, then id. |
| `summary` | object | Count of findings per severity. |
| `skipped_checks` | array | `{checks, reason}` for every check that could not run. |
| `sources` | object | `source_id` → `{title, url, status}`. |
| `text` | object | `extractor`, `full` (whole primary text), `content_checks_source` (which text the content checks read; see C). |
| `relevance` | object or null | Only with `--job`: `job_text`, `terms` (`term`, `in_cv`, `count`, `cv_lines`), `terms_found`, `terms_total`. |

### Finding

```json
{
  "id": "reading_order_mixed",
  "group": "A",
  "severity": "P1",
  "evidence_type": "measured",
  "message": "English text; translate it for the report",
  "location": {"page": 1, "area": "two-column area"},
  "source_id": null,
  "source_status": "UNVERIFIED",
  "rationale": "only for heuristic findings",
  "evidence": {"details": "specific to the check"}
}
```

`id`, `group`, `severity`, `evidence_type`, `message`, `location` and
`source_id` are always present. `source_status` appears only with a
`source_id`, and `rationale` only for heuristic findings. `evidence` is
optional. Groups: `A` extraction, `B` structure, `C` content, `D` relevance
(D has no findings of its own; see below).

## A: Extraction (measured)

Every available extractor runs on the file. A check reports which
extractors show the problem, because the parser an employer uses is unknown.

| id | Severity | What is measured | Why it matters |
|---|---|---|---|
| `no_extractor` | P0 | No extractor could run. | Nothing was measured. |
| `text_is_image` | P0 | The page has fewer than `TEXT_LAYER_MIN_CHARS_PER_PAGE` non-space characters in *every* extractor, and it has an image. | The text is pixels. A parser without OCR reads nothing. |
| `text_is_outlines` | P0 | Same text test. No image, but at least `OUTLINE_MIN_PATH_PAINTS` vector paint operations. | The glyphs were converted to shapes, e.g. by "outline text" or "convert to curves" on export. |
| `text_layer_missing` | P0 | Same text test, with neither cause found. | Nothing to parse. |
| `extractor_disagreement` | P1 | The multiset share of tokens two extractors have in common is below `AGREEMENT_MIN_RATIO`. | The file is read differently depending on the parser. |
| `reading_order_mixed` | P1 | See "Reading order" below. | Sidebar and main text get mixed, and details land in the wrong section. |
| `missing_spaces` | P1 | At least `LONG_TOKEN_MIN_COUNT` tokens have `LONG_TOKEN_CHARS` or more characters (e-mails and URLs excluded). | Words run together, so keyword search misses them. |
| `garbage_chars` | P1, or P2 if only at line starts | Private Use Area U+E000–U+F8FF, U+FFFD, control characters, and pdfminer's `(cid:N)` in the extracted text. | Icon fonts (envelope, phone) and symbol-font bullets turn into meaningless characters. |
| `ligatures_in_text` | P1 | U+FB00–U+FB06 in the extracted text. | "proﬁcient" is not "proficient" for search. Ligatures that are only typeset are no finding: a correct ToUnicode CMap maps them back to "fi". |
| `font_type3` | P1 without ToUnicode, else P2 | Fonts of subtype Type3. | Glyphs are drawing procedures, as some design tools export them; the text only extracts through a ToUnicode map. |
| `font_not_embedded` | P2 | A font that is neither embedded nor one of the standard 14. | This does not affect extraction with a standard encoding. It affects how the file looks elsewhere. |
| `font_size_small` (heuristic) | P2 | Text of at least `SMALL_FONT_MIN_LETTERS` letters below `SMALL_FONT_PT`. | Hard to read. Some parsers drop fine print. |

### Reading order

1. **Rows.** Fragments with the same top coordinate (±`ROW_TOLERANCE_PT`)
   form a row. Fragments with gaps below `SEGMENT_GAP_PT` merge into
   segments.
2. **Gutter.** In each row, a gap of at least `COLUMN_GAP_MIN_PT` between
   two segments is a candidate. A sweep finds the x-position covered by the
   most candidate gaps. There are two columns when at least
   `COLUMN_MIN_SHARED_ROWS` rows share that gutter.
3. **Not columns.** Two cases are excluded:
   - At least `LABEL_SIDE_MIN_SHARE` of one side is dates or short labels.
     This is the German tabular CV (dates left, text right), where row-by-row
     reading is the intended order.
   - Text inside a ruled table.
4. **Mixing, measured per extractor.** Tokens of at least
   `DISTINCT_TOKEN_MIN_CHARS` letters that occur on one side only identify
   that side. An extracted line with tokens of both sides is a *mixed line*.
   The sequence of one-sided lines gives the *column switches*.
   `reading_order_mixed` is raised only when an extractor has at least
   `MIXED_LINES_MIN` mixed lines or at least `INTERLEAVE_MIN_SWITCHES`
   switches. Columns alone are never a finding.

## B: Structure

| id | Evidence | Severity | Rule | Source |
|---|---|---|---|---|
| `contact_missing` | measured | P0 | No e-mail and no phone in any extractor's text or link. | – |
| `contact_only_in_links` | measured | P1 | E-mail or phone only as a link target (`mailto:`, `tel:`), not as visible text. | – |
| `contact_in_header_footer` | documented | P1 | The contact appears only (a) inside marked content `/Artifact` (Header/Footer), or (b) in a row that repeats in the outer `ZONE_FRACTION` of the page height on at least `ZONE_MIN_PAGES` pages. A one-page CV with the contact at the top is therefore not flagged. | `greenhouse_parse` |
| `sections_missing` | heuristic | P1 if experience is missing, else P2 | No heading found for experience, education or skills (dictionary below). | – |
| `dates_not_found` | heuristic | P2 | No year in the text. | – |
| `dates_inconsistent` | heuristic | P2 | More than one month-level format, each used at least `DATE_FORMAT_MIN_USES` times. | – |
| `table_detected` | documented | P2 | Ruled grid: at least `TABLE_MIN_HLINES` horizontal and `TABLE_MIN_VLINES` vertical rules, each crossing at least `TABLE_MIN_CROSSINGS` others. Rules shorter than `TABLE_MIN_HRULE_PT` / `TABLE_MIN_VRULE_PT` are ignored, so outlined glyphs do not count. Tables without rules are not detected. | `greenhouse_parse` |
| `images_present` | documented | P2 | An image larger than `ICON_MAX_PT` in either dimension. | `greenhouse_parse` |
| `file_size_over_limit` | documented | P1 | File larger than `FILE_SIZE_LIMIT_BYTES` (2.5 MB). | `greenhouse_parse` |
| `page_count_high` | documented | P2 (note only) | More than `PAGE_LIMIT` pages. | `ba_lebenslauf` |
| `letter_spacing` | documented | P1 | At least `LETTER_SPACING_MIN_LETTERS` single letters separated by single spaces in an extractor's output ("E r f a h r u n g"). | `greenhouse_parse` |

**Heading dictionary** (case-insensitive; the line has at most
`HEADING_MAX_WORDS` words):

| Canonical | German | English |
|---|---|---|
| profile | Profil, Kurzprofil, Über mich, Zusammenfassung | Profile, Summary, Professional Summary, About me, Personal Statement, Career Summary |
| experience | Berufserfahrung, Erfahrung, Berufliche Erfahrung, Beruflicher Werdegang, Werdegang, Praxiserfahrung, Berufspraxis | Experience, Work Experience, Professional Experience, Employment History, Work History, Employment, Career History |
| education | Ausbildung, Bildung, Bildungsweg, Schulbildung, Studium, Akademische Ausbildung | Education, Academic Background, Qualifications |
| skills | Kenntnisse, Fähigkeiten, Kompetenzen, Fachkenntnisse, IT-Kenntnisse, EDV-Kenntnisse | Skills, Technical Skills, Core Competencies, Competencies, Key Skills |
| languages | Sprachen, Sprachkenntnisse | Languages |
| certifications | Zertifikate, Zertifizierungen, Weiterbildung(en) | Certifications, Certificates, Training |
| projects | Projekte | Projects |
| interests | Interessen, Hobbys | Hobbies, Interests |

**Date formats:** `MM/YYYY`, `MM.YYYY`, `YYYY-MM`, `Month YYYY` (German and
English month names) and `DD.MM.YYYY`. `DD.MM.YYYY` is left out of the
consistency check because birth dates use it.

## C: Content (heuristic, reported as assessment)

The content checks read the primary extractor's text. There is one
exception: on a page where the primary extractor mixes the columns, they
read the text rebuilt column by column from the coordinates. Otherwise
the wording would be judged on text that no reader sees
(`text.content_checks_source` says which text was used).

| id | Rule | Rationale |
|---|---|---|
| `bullets_without_evidence` | At least `BULLETS_MIN_COUNT` bullets, and a share of at least `BULLETS_UNSUPPORTED_MIN_SHARE` has no digit, no %/€/$/£ and no result verb from `EVIDENCE_WORDS`. | Statements that can be checked (number, scope, result) carry information; task lists do not. |
| `adjectives_without_evidence` | At least `ADJECTIVES_MIN_COUNT` distinct words from `SOFT_ADJECTIVES` on lines without evidence. | "motiviert, teamfähig" cannot be checked. |
| `skill_bars` | At least `SKILL_BARS_MIN_COUNT` filled bars of `SKILL_BAR_MIN_H`–`SKILL_BAR_MAX_H` × `SKILL_BAR_MIN_W`–`SKILL_BAR_MAX_W` pt, left-aligned, with no level word or digit in the nearby text. | The level exists only as a graphic. |
| `icon_images` | At least `SKILL_BARS_MIN_COUNT` images no larger than `ICON_MAX_PT`. | Icons are invisible to a parser. |
| `profile_missing` | No profile heading. | A short profile states role and core skills. |
| `profile_too_long` | More than `PROFILE_MAX_LINES` non-empty lines between the profile heading and the next heading. | A long profile is skimmed. |

Not detected: level dots drawn as circles, and icons drawn as vector paths.
The report may mention these only as an observation.

## D: Relevance (only with `--job`)

The script extracts candidate terms from the job ad and checks for each
whether it occurs literally in the CV text: `in_cv`, `count`, and up to
`MAX_LINES_PER_TERM` CV lines. Candidate terms are word tokens of at least
`JOB_TERM_MIN_CHARS` characters, or with `+`/`#`, that are not in
`STOPWORDS`; there are at most `MAX_JOB_TERMS`. Claude makes the judgement in the report
(`references/report-format.md`, section 6). There is no keyword density and
no percentage.

## Degradation

- **An extractor is missing:** its entry is `unavailable` with the import
  error. The remaining extractors run.
- **pypdf is missing:** the structure checks that use pypdf's object model
  are listed in `skipped_checks`, with the reason. These are fonts, tables,
  images, links, outline detection, skill bars and header/footer artifact
  tags.
- **No coordinate-capable extractor** (pdfplumber, pymupdf, pypdf) runs:
  reading order, columns and font sizes are skipped and listed.
- **No extractor at all:** the only finding is `no_extractor`.

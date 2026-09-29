# Report format

Write the report directly in the chat as Markdown, in the user's language.
Keep the section order and headings below. German headings are given in
brackets; for other languages, translate them. Do not add a score, a grade
or a percentage anywhere.

Keep it short: no introduction, no "Great CV!", no closing offer beyond
the one line in section 6.

---

## 1. Verdict [Kurzurteil]

Exactly three lines, each starting with its label in bold:

```
**Parser reads the file:** <cleanly | with problems | barely or not at all>, <one clause of evidence>
**Biggest risk:** <the highest-severity finding in plain words, or "none found">
**Main lever:** <the single change with the largest effect>
```

Rules:
- The choice for "Parser reads the file" is fixed:
  - **"barely or not at all"**: any P0 finding in group A, or `contact_missing`.
  - **"with problems"**: any other P0 or P1 finding.
  - **"cleanly"**: only P2 findings or none.
- **"Biggest risk"** is the first finding in `findings`, which is already
  sorted by severity.
- **"Main lever"** is improvement no. 1 from section 4.

## 2. What a parser sees [Was ein Parser sieht]

One sentence first, then a code block. The sentence names:
- the extractor of `preview.extractor`, and
- how many extractors ran (`status: ok`), listing the unavailable ones.

Then show `preview.lines` exactly as they are, without any correction. Wrong
order, glued words and garbage characters are the point. Mark nothing
inside the block.

````
Extracted with pdftotext (4 of 5 extractors ran; pymupdf unavailable):

```text
<preview.lines, one per line>
```
````

If `preview.total_lines` is larger than the number of lines shown, add
"(first N of M lines)".

When `reading_order_mixed` exists and names extractors other than the
preview extractor, add a second, short block with the sample lines. Take those
lines from that finding's `evidence.<extractor>.samples` or
`switch_samples`, and put the extractor's name above the block.

When a page has `text_is_image` or `text_is_outlines`, the block is
(nearly) empty. Say so in one sentence: that is what the parser gets.

## 3. Findings [Befunde]

Group the findings under the sub-headings **P0**, **P1** and **P2**. Leave
out empty groups. Each finding is one bullet in this form:

```
- **<short title>** `<evidence label>` – <what was found, with the numbers from the JSON> (<location>). <Why it matters, one sentence.>
```

Evidence labels:
- `measured` (German: `gemessen`)
- `documented: <source title>` (German: `dokumentiert: <Quelle>`). When
  `source_status` is `UNVERIFIED`, add "(source not verified)" (German:
  "(Quelle nicht verifiziert)").
- `heuristic` (German: `Einschätzung`). Also start the sentence with
  "Assessment:" / "Einschätzung:", so that it does not read as a fact.

Rules:
- Take numbers only from the JSON (sizes, counts, pages, extractor names).
- Name the extractors a finding applies to when the JSON lists them. For
  example: "pdfplumber and pypdf mix the columns; pdfminer keeps them apart."
- **Merge findings that share one cause** into one bullet and name both ids.
  Example: `letter_spacing` causes `sections_missing`.
- **`skipped_checks`**: add one last bullet under the lowest group shown,
  "Not checked: …, because …".
- **No findings:** write one line, "No problems measured." (German:
  "Keine Probleme gemessen."), and keep the section.

## 4. Improvements [Verbesserungen]

At most 8 (fixed by the specification of this skill), sorted by effect:
P0 causes first, then P1, then content. Each
one follows this form:

```
**<n>. <what to change>** (fixes: `<finding id>`)
Before: <quote from the CV or a description of the layout>
After:  <the concrete replacement>
```

Follow `references/rewriting.md` for everything in this section. In
particular:
- no invented numbers, only placeholders;
- layout changes only when a `measured` or `documented` finding supports
  them;
- keep the user's voice.

When there is nothing worth changing, say so in one line. Do not fill the
section for the sake of it.

## 5. Match with the job ad [Abgleich mit der Stellenanzeige] (only with a job ad)

Pick the central requirements of the ad (the must-haves: hard skills,
experience, languages, certificates). Leave out generic phrases such as
"team spirit". Show them as a table:

```
| Requirement (from the ad) | In the CV | Where / how |
|---|---|---|
| Python | supported | "Führte ein Team … (Python, PostgreSQL)" – with scope |
| Kubernetes | named only | only listed under skills, no example |
| Kotlin | missing | – |
```

- **Status values** (German): `belegt` = supported, `nur genannt` = named
  only, `fehlt` = missing.
- **Supported** means that an experience line shows the requirement in use
  (task, context or result).
- **Named only** means it appears only in a list.
- **Evidence:** base the judgement on `relevance.terms`
  (`in_cv`, `cv_lines`) and on `text.full`. Also count synonyms and
  equivalent wording as found, e.g. "Postgres" for "PostgreSQL"; the "Where"
  column says so.
- **After the table:** one or two sentences on where the CV should show a
  requirement that it only names. Point to the matching item in section 4
  if there is one. Never suggest adding skills the CV gives no sign of.
- **No match figure:** no percentage and no "match score".

## 6. Limits [Grenzen]

Always include this section, in these words, translated:

> Which parser and which filter rules an employer uses cannot be seen from
> outside. This check simulates text extraction with open tools (the
> extractors named above), not a specific ATS. `measured` findings apply
> to this file; whether a given ATS stumbles over them depends on its
> parser. Assessments (`heuristic`) are rules of thumb.

Then one line: "Upload a revised version and I will check it again." (German:
"Lade eine überarbeitete Fassung hoch, dann prüfe ich sie erneut.")

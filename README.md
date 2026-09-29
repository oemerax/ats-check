# ats-check

ats-check does **not** give your CV an "ATS score", and it does **not**
imitate any particular applicant tracking system. It shows what open text
extractors actually read from your CV PDF, what goes wrong on the way, and
what to change.

It is an [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
for Claude. Upload your CV as a PDF and you get three things, without
follow-up questions:

1. **What a parser sees:** the extracted text as it comes out, and which
   extractor produced it.
2. **Prioritized findings (P0 to P2),** each labelled with its kind of
   evidence:
   - `measured`: measured on your file;
   - `documented`: documented by an ATS vendor or an authority, with a
     source;
   - `heuristic`: a rule of thumb, stated as such.
3. **Concrete improvements:** before/after, at most eight, in your own
   voice, with placeholders instead of invented numbers.

If you also paste a job ad, you get a table on top. For each central
requirement it says whether your CV *supports* it, only *names* it, or
*misses* it.

## Why no score

There is no universal ATS, and there is no universal score:
- Employers use different systems, and those systems use different parsers.
- SAP SuccessFactors, for example, uses Textkernel as its parser
  ([SAP Help](https://help.sap.com/docs/SAP_SUCCESSFACTORS_RECRUITING/8477193265ea4172a1dda118505ca631/07b6d03076a149b78f4f7a615e3025fd.html);
  source not verified at build time, see [sources](skills/ats-check/references/sources.md)).
- Each employer adds its own filter rules on top.
- None of this is visible from outside.

A single number would pretend to know it. ats-check measures what can be
measured on the file, and labels everything else.

**The "75 % of CVs are rejected by ATS" figure is a myth.** It is usually
traced to a 2012 sales pitch by a resume-optimisation company, with no
published method (see [sources](skills/ats-check/references/sources.md)).
ats-check does not use it.

## What it checks

- **Extraction** (`measured`): up to five extractors run and are compared:
  - pdftotext, pdfminer.six, pypdf, PyMuPDF and pdfplumber.
  - It finds pages without a text layer (text stored as an image or as
    outlines).
  - It finds disagreement between the extractors.
  - It finds columns that an extractor reads in a mixed-up order. This is
    measured in the extracted text, not assumed from the layout.
  - It finds glued words, icon-font garbage (Private Use Area characters)
    and ligature characters in the text.
  - It reports Type3 and non-embedded fonts, and very small type.
- **Structure:**
  - contact details only in the header/footer or only in links;
  - section headings (German and English);
  - date formats;
  - ruled tables and images;
  - file size above 2.5 MB (Greenhouse);
  - more than two pages (Bundesagentur für Arbeit, a note only);
  - letter-spaced headings.
- **Content** (`heuristic`, marked as assessment):
  - bullets without number, scope or result;
  - lists of soft-skill adjectives;
  - skill level shown only as bars;
  - icons;
  - profile missing or too long.

The full list, with thresholds, JSON schema and rationale, is in
[`references/checks.md`](skills/ats-check/references/checks.md).

## Installation

### claude.ai

1. Download [`dist/ats-check.zip`](dist/ats-check.zip).
2. Upload it as a custom skill, as described in Anthropic's help article
   [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude).
   Skills need code execution to be enabled; the article explains this.

### Claude Code

```
/plugin marketplace add oemerax/ats-check
/plugin install ats-check@ats-check
```

## Limits

- **The employer's system is unknown.** Which parser and filters an
  employer uses cannot be seen from outside. The skill simulates text
  extraction with open tools, not a specific ATS.
- **No OCR.** A CV that is an image is reported as unreadable. Some
  commercial parsers run OCR and may still read it.
- **Detection limits:**
  - Only tables drawn with rules are detected.
  - Level dots drawn as circles and icons drawn as vector paths are not
    detected.
  - Column detection finds one gutter per page.
- **Unverified sources.** The `documented` findings rely on sources that
  could not be opened during the build. The environment's network policy
  blocked them, so they are marked UNVERIFIED in
  [`sources.md`](skills/ats-check/references/sources.md), and the report
  says so.
  - In particular, a search summary of the Greenhouse page did not confirm
    that Greenhouse names headers, footers and tables.
- **Extractors in claude.ai: UNKNOWN.**
  - No official page lists the Python packages that are pre-installed in
    claude.ai's code environment.
  - Anthropic's documentation of the *API* code execution tool lists pypdf,
    pdfplumber and pypdfium2
    ([code execution tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)).
    That page covers the API, not claude.ai.
  - The skill checks at runtime which extractors can be imported, and runs
    whichever are there (at least one is needed).
  - It reports the missing ones as `unavailable`. It never installs
    anything.
  - The tests cover the case where only pypdf is present.
- **Privacy.** The script makes no network calls and writes nothing except
  its JSON output. The skill tells Claude not to send the CV anywhere.

## Development

```bash
pip install -r requirements-dev.txt     # plus poppler-utils and DejaVu fonts
python tests/make_fixtures.py           # writes the test PDFs to tests/fixtures/
pytest -q
python tools/build_dist.py              # rebuilds dist/ats-check.zip
```

Layout:

- `skills/ats-check/SKILL.md`: instructions for Claude.
- `skills/ats-check/scripts/analyze.py`: PDF → JSON, deterministic.
- `skills/ats-check/scripts/extractors.py`: one adapter per extractor.
- `skills/ats-check/references/`: checks, report format, rewriting rules
  and sources.
- `tests/`: fixture generator, expected findings per fixture, pytest suite.
- `evals/triggers.json`: prompts that should and should not trigger the
  skill (not measured yet).
- `tools/build_dist.py`: reproducible build of the upload zip.

## License

MIT, see [LICENSE](LICENSE).

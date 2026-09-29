# Sources

Every source the skill cites, with its URL and verification status.

**Status meanings:**
- **VERIFIED:** the page was opened and the cited statement was found in
  it.
- **UNVERIFIED:** the page could not be opened, so the statement is not
  confirmed.

**Build check, 2026-09-29.** The build environment could not open the pages
of the research sources. Every request was refused by the environment's
egress proxy (HTTP 403, "CONNECT tunnel failed"). They are therefore all
UNVERIFIED. They are listed anyway, as the specification requires.

**Search summaries.** Where a web search returned a summary of the page,
this file notes what that summary said. It is marked *search summary,
unconfirmed*, because a search engine's summary is not the page. Numbers
from such summaries are left out on purpose.

**Before relying on a `documented` finding,** open the source and update
its status here and in `SOURCES` in `scripts/analyze.py`.

---

## Research sources

### `greenhouse_parse` — Greenhouse Support: Unsuccessful resume parse

- **URL:** https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:**
  - `file_size_over_limit`: no parse above 2.5 MB;
  - `letter_spacing`: spaced-out letters are not recognised as a word;
  - `images_present`: graphics and images parse poorly;
  - `table_detected`: tables;
  - `contact_in_header_footer`: headers, footers and text boxes.
- **Search summary, unconfirmed:**
  - The page says Greenhouse cannot parse resumes larger than 2.5 MB.
  - Letters separated by spaces are not recognised as a single word.
  - Graphics, photos, word art and resumes uploaded as an image parse
    poorly.
  - Unrecognised characters and non-standard file types are further causes.
- **Open point:**
  - The summaries do **not** show Greenhouse naming headers, footers, text
    boxes or tables. Only a third-party site attributes these to Greenhouse.
  - The specification assigns `documented (Greenhouse)` to
    `contact_in_header_footer` and `table_detected`, and the code keeps that
    assignment.
  - Until the page is checked, treat both as the weakest `documented`
    findings. If the page does not mention them, change their evidence type
    to `heuristic`.

### `sap_sf_parsing` — SAP SuccessFactors: Working with Resume Parsing

- **URL:** https://help.sap.com/docs/SAP_SUCCESSFACTORS_RECRUITING/8477193265ea4172a1dda118505ca631/07b6d03076a149b78f4f7a615e3025fd.html
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:**
  - README background: SuccessFactors uses Textkernel as its parser;
  - parsing is not 100 % accurate.
- **Search summary, unconfirmed:** SuccessFactors uses the third-party
  software Textkernel to parse resume data. The "not 100 % accurate"
  wording appeared in one summary and not in another.

### `ba_lebenslauf` — Bundesagentur für Arbeit: Lebenslauf

- **URL:** https://www.arbeitsagentur.de/bildung/bewerbung/lebenslauf
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:** `page_count_high`, a CV of one to at most two pages.
- **Search summary, unconfirmed:** a tabular CV on one to at most two A4
  pages; a photo is no longer mandatory.

### `hbs_hidden_workers` — Harvard Business School / Accenture: Hidden Workers: Untapped Talent (2021)

- **URL:** https://www.hbs.edu/ris/Publication%20Files/hiddenworkers09032021_Fuller_white_paper_33a2047f-41dd-47b1-9a8d-bd08cf3bfa94.pdf
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:** README background. Employers report that their
  automated recruiting systems filter out qualified candidates who do not
  match rigid criteria.
- **Search summary, unconfirmed:** the report describes employers saying
  that qualified candidates are screened out because they do not match the
  exact criteria of a job description. The percentages from secondary
  coverage are left out, because they could not be checked against the
  PDF.

### `wiles_2025` — Wiles, Munyikwa, Horton: Algorithmic Writing Assistance on Jobseekers' Resumes Increases Hires (Management Science, 2025)

- **URL:** https://pubsonline.informs.org/doi/10.1287/mnsc.2024.04528
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:** `rewriting.md`. Non-generative writing assistance
  (error correction, clarity) increased hires. It supports editing over
  replacing.
- **Search summary, unconfirmed:**
  - The title and authors are as above.
  - It was a field experiment on an online labour market.
  - Jobseekers who received the assistance were hired more often.
  - The assistance was non-generative.
- **Other versions**, also not opened: NBER w30886 and arXiv 2301.08083.

### `xu_2025_selfpref` — Xu, Li, Jiang: AI Self-preferencing in Algorithmic Hiring: Empirical Evidence and Insights

- **URL:** https://arxiv.org/abs/2509.00462
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:** `rewriting.md`. LLMs used as evaluators prefer CVs they
  generated themselves, which is why the skill makes minimal edits instead
  of regenerating the CV.
- **Search summary, unconfirmed:** the abstract reports self-preference
  across several commercial and open models. Candidates who use the same
  LLM as the evaluator are more likely to be shortlisted.

### `figma_export` — Figma Help: Export formats and settings

- **URL:** https://help.figma.com/hc/en-us/articles/13402894554519-Export-formats-and-settings
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Cited for:** `checks.md` background. Design-tool PDF exports store text
  as glyphs rather than editable text.
- **Search summary, unconfirmed:**
  - Figma exports text in PDFs "as glyphs": it cannot be edited, but it can
    still be selected and copied.
  - The option "Outline text" belongs to SVG export.
- **Consequence:** the skill does **not** cite Figma for
  `text_is_outlines`. That finding is `measured` and needs no source.

## The "75 % of CVs are rejected by an ATS" claim

This number is **not** used. The README names it as a myth.

- **URL:** https://theconversation.com/what-everyone-gets-wrong-about-the-modern-job-search-and-what-actually-works-285582
- **Status:** UNVERIFIED (not reachable from the build environment).
- **Search summary, unconfirmed:** the figure goes back to a 2012 sales
  pitch by Preptel, a resume-optimisation company, with no published
  method.

---

## Platform documentation (for building and installing the skill)

These pages were fetched live on 2026-09-29 while building the skill. The
quoted rules were read from the pages.

| Topic | URL | Status | Used for |
|---|---|---|---|
| Agent Skills overview | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview | VERIFIED | Frontmatter rules for `name` (at most 64 characters, lowercase letters, numbers and hyphens, no XML tags, no "anthropic" or "claude") and `description` (non-empty, at most 1024 characters, no XML tags, says what the skill does and when to use it). |
| Skill authoring best practices | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices | VERIFIED | SKILL.md body under 500 lines. |
| Agent Skills specification | https://agentskills.io/specification (read from github.com/agentskills/agentskills) | VERIFIED | `name` matches the folder name, with no leading, trailing or double hyphens. |
| How to create custom skills (claude.ai) | https://support.claude.com/en/articles/12512198-how-to-create-custom-skills | VERIFIED | The ZIP holds the skill folder as its root. |
| Use Skills in Claude | https://support.claude.com/en/articles/12512180-use-skills-in-claude | VERIFIED | Upload procedure; the README links to it. |
| Create a plugin marketplace | https://code.claude.com/docs/en/plugins/create-marketplace | VERIFIED | `.claude-plugin/marketplace.json`: `name`, `owner`, `plugins[]` with `name` and `source`. |
| Plugin marketplace reference | https://code.claude.com/docs/en/plugins/marketplace-reference | VERIFIED | Relative `source` starting with `./`; `strict: false` with `skills` when there is no plugin.json. |
| Code execution tool (API) | https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool | VERIFIED | Pre-installed libraries include pypdf, pdfplumber and pypdfium2. This page documents the **API** tool, not claude.ai. |
| Create and edit files with Claude (claude.ai) | https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude | VERIFIED | Network access depends on the plan and the organisation settings. The page lists no pre-installed packages. |

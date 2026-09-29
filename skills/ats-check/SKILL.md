---
name: ats-check
description: Checks a CV or resume PDF the way an applicant tracking system (ATS) parser reads it. Shows the text a parser actually extracts and gives prioritized findings, each labeled measured, documented or heuristic. Covers text stored as an image or as outlines, mixed-up columns, icon-font garbage, contact details only in the header or in links, tables and file size. Adds concrete before/after rewrites and, if a job ad is given, a relevance check. Use this skill whenever the user uploads a PDF that is or looks like a CV, resume or Lebenslauf. Also use it when the user mentions resume, CV, Lebenslauf, Bewerbung, Bewerbungsunterlagen, ATS, applicant tracking, "check my CV", "prüf meinen Lebenslauf", "is my resume ATS-friendly", "why do my applications get no response", or wants a CV compared with a job posting, even if ATS is never mentioned. Do not use it for writing cover letters or for summarizing PDFs that are not CVs.
---

# ats-check

Measure what text extractors read from a CV PDF, report the problems with
their evidence, and suggest minimal improvements. There is no "ATS score":
there is no universal ATS, and which parser and filters an employer uses
cannot be seen from outside. Report only what the script measured, what a
source documents, or what is clearly marked as a rule of thumb.

## Workflow

Follow these steps in order. Do not ask questions before the first report.

1. **Find the PDF.** Look in `/mnt/user-data/uploads` (and any other upload
   location this environment uses) for a `.pdf`. If there are several, use
   the one that looks like a CV (name contains cv, resume, lebenslauf,
   bewerbung, or the most recent upload). If there is no PDF at all, ask the
   user to upload their CV as a PDF and do nothing else.

2. **Save the job ad, if any.** If the user pasted a job ad as text, write
   it unchanged to a file, e.g. `/tmp/job.txt`. If the job ad is itself an
   uploaded file, pass its path (plain text works; for a PDF job ad, extract
   its text first with the same extractors, e.g. pypdf).

3. **Run the analysis.** The script sits next to this file:

   ```bash
   python3 <this-skill-dir>/scripts/analyze.py "<cv.pdf>" [--job /tmp/job.txt]
   ```

   `<this-skill-dir>` is the directory that contains this SKILL.md. The
   script prints JSON to stdout. It needs no network and installs nothing.
   Do not `pip install` anything; if an extractor is missing, the JSON says
   `unavailable` and the report says so.

4. **Write the report** directly in the chat, following
   `references/report-format.md` exactly. Read that file before writing.
   The JSON field meanings and every check are in `references/checks.md`.

5. **Write the improvements** following `references/rewriting.md`. Read it
   before proposing any rewrite.

6. **With a job ad:** add the relevance section described in
   `references/report-format.md`. The script only lists literal term hits
   (`relevance.terms`). Judge the requirements yourself: for each important
   requirement of the ad, is it *supported* in the CV (with an example,
   number or context), only *named*, or *missing*? Do not compute a keyword
   density or a match percentage.

## Rules

- **Language:** write the report in the user's language (German if the user
  writes German, and so on). The JSON messages are English; translate them.
  Keep finding ids and evidence labels (`measured`, `documented`,
  `heuristic`) unchanged so they stay recognisable.
- **Evidence labels are mandatory** on every finding in the report. For a
  `documented` finding, name the source from `sources` in the JSON. If its
  `source_status` is `UNVERIFIED`, write "(source not verified)" next to it.
- **No invented numbers.** Every number in the report comes from the JSON
  or from the user's CV. Rewrites use placeholders (`[Zahl]`, `[Umfang]`,
  `[Ergebnis]` or `[number]`, `[scope]`, `[result]`) where the CV has no
  number.
- **No score, no pass/fail percentage, no claim about a specific ATS.** Do
  not state how many CVs "ATS reject"; the popular "75 %" figure has no
  published method.
- **Privacy:** do not send the CV anywhere, do not use web search or other
  network tools on it, and do not store it beyond this conversation. Do not
  repeat personal data (address, birth date, phone) in the report beyond
  what a finding needs.
- **If the script fails** (non-zero exit, Python error), say that the
  analysis could not run, quote the error line, and give only what you can
  say without measurement, marked `heuristic`. Never present guesses as
  measurements.
- **If `findings` contains `no_extractor`:** no extractor could run in this
  environment. Report that and list `extractors` with their reasons.
- **If a page has `text_is_image`, `text_is_outlines` or `text_layer_missing`:**
  that is the headline. Content checks cannot run on that page. Do not read
  the CV visually and then critique its wording as if a parser could see it;
  you may mention what you can see, clearly separated.

## After the first report

Answer follow-up questions normally. If the user uploads a revised PDF, run
the script again and report what changed (findings fixed, still open, new).

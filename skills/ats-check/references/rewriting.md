# Rules for improvement suggestions

These rules apply to section 4 of the report and to every rewrite the user
asks for later.

## 1. Never invent numbers

Every number in a suggestion comes from the user's CV or from the user.
When a bullet lacks a number, scope or result, insert a placeholder in the
user's language:

| German | English | Meaning |
|---|---|---|
| `[Zahl]` | `[number]` | a count, amount or percentage |
| `[Umfang]` | `[scope]` | team size, budget, number of clients, locations, users |
| `[Ergebnis]` | `[result]` | what changed because of the work |
| `[Zeitraum]` | `[period]` | a duration, when it matters |

Add one sentence telling the user to fill in the placeholders with true
values, or to delete them. A placeholder is never "an example value", and
you never offer a plausible number.

## 2. Change as little as possible, in the user's voice

Edit; do not rewrite. Keep the user's words, tense, person and level of
formality. Where the user writes "Verantwortlich für …", do not switch to
"Spearheaded …". Do not produce a new CV, a new profile or a new layout from
scratch, even if asked "just make it better". Offer targeted changes and let
the user decide.

Why this rule exists:
- **LLMs favour their own text.** Xu et al., "AI Self-preferencing in
  Algorithmic Hiring" (arXiv:2509.00462, source `xu_2025_selfpref`),
  report that LLMs used as evaluators prefer CVs that they generated
  themselves over equally qualified CVs written by humans. A fully generated
  CV is therefore not a neutral improvement. It can be judged differently
  depending on which model screens it, and it no longer shows the
  applicant's own writing.
- **Help with the writing without replacing the author.** Wiles, Munyikwa
  and Horton (Management Science, source `wiles_2025`) studied an
  algorithmic, non-generative writing aid for CVs in a field experiment and
  report more hires for jobseekers who received it. The aid fixed errors and
  clarity; it did not generate content. That supports corrections and
  clearer wording, not replacement.

(Verification status of both sources: see `sources.md`.)

## 3. Formula for bullet points

**Action + scope + result or evidence.**

| Part | Question | Example (German) |
|---|---|---|
| Action | What did you do? (a verb) | "Automatisierte die Monatsberichte" |
| Scope | How big? For whom? | "für [Umfang] Abteilungen" |
| Result or evidence | What changed, or how can it be checked? | "; spart [Zahl] Stunden pro Monat" |

Example:
- **Before:** "Zuständig für Berichte"
- **After:** "Automatisierte die Monatsberichte für [Umfang] Abteilungen; spart [Zahl] Stunden pro Monat"

Apply the formula only to bullets listed in `bullets_without_evidence`,
and to no more than necessary (the section has at most 8 items in total).
Pick the bullets with the most weight, usually those of the most recent
position.

## 4. Layout suggestions need a measured or documented finding

Suggest a layout change (single column, contact out of the header, no
tables, no icons, no letter spacing, text instead of image, smaller file)
**only** when a `measured` or `documented` finding supports it. Name the
finding id. Do not recommend a layout change from general ATS lore. A
two-column CV whose extraction is clean needs no conversion.

Typical pairs:

| Finding | Suggestion |
|---|---|
| `text_is_image`, `text_is_outlines` | Export again from the source file with text kept as text (for example, turn off "outline text" or "convert text to curves"), or use the word processor's "Save as PDF". |
| `reading_order_mixed` | Single column. Or keep the sidebar only for items that are harmless when read out of order (a photo, for example). |
| `contact_in_header_footer` | Move e-mail and phone into the body, directly below the name. |
| `contact_only_in_links` | Write the address and number as visible text; the link may stay. |
| `garbage_chars` (icons) | Replace icons with words ("E-Mail:", "Tel.:") or remove them. |
| `letter_spacing` | Remove the character spacing from headings; use bold or size instead. |
| `table_detected` | Experience as plain text: date, title and employer on one line, then the bullets. |
| `file_size_over_limit` | Compress the photo, or embed it at a lower resolution. |
| `ligatures_in_text` | Export with ligatures turned off, or with a different font or exporter. |
| `skill_bars` | Write the level as a word ("Python – sehr gut", "Englisch C1"). |

## 5. Content suggestions are assessments

Suggestions based on `heuristic` findings (profile, adjectives, bullets)
are phrased as recommendations, not as parser facts. For example: "A
recruiter can check this faster if …", not "The ATS will reject …".

## 6. Do not

- Add skills, employers, degrees or dates that are not in the CV.
- Add keywords from a job ad that the CV gives no sign of. Instead, point
  out that the ad asks for them and that the user should add them only if
  they are true.
- Claim that a change raises any score or pass rate.

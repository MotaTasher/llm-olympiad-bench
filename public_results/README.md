# Reasoning Space public results

This is the standalone public Reasoning Space site. It contains:

- `index.html`: benchmark, year and stage filters plus one selected leaderboard;
- `competitions.html`: compact buttons for available competition releases;
- `solution.html`: full-width model and official solution reading layout;
- `data.js`: fallback release, team and catalog data;
- `assets/csspace-logo.svg`: local vector CS Space logo used in headers and footers;
- `assets/formula-pattern-{desktop,mobile}.svg`: original vector formula backgrounds;
- `generated/`: ignored public export created from real logs and sidecars;
- `app.js`: release switching, generated-data merge and page rendering.

The public URL contract uses clean, extension-free routes:

- `/` for the leaderboard;
- `/problems` for the published-problem catalog;
- `/problems/<competition-id>/<task-slug>/<model-slug>` for a concrete model
  answer, for example `/problems/math-cup-2026-final/task1/gpt-5.6`.

Old `index.html`, `competitions.html` and query-string solution URLs remain
usable as compatibility entry points. On object storage, `/problems` and every
concrete solution route are extensionless HTML objects that contain the catalog
or solution shell respectively; all page assets use root-relative URLs.

The exporter copies each selected competition's `assets/` directory into
`generated/assets/<competition-id>/` and rewrites `assets/...` references in
published statements and official solutions. It also turns plain HTTP(S)
links, including links accidentally wrapped in inline code, into clickable
Markdown links. The CS Space SVG is used as the favicon on every public page.

It deliberately does not import Flask, modify scoring routes, or write to run
logs and evaluation sidecars.

Generate the current public projection, then open it locally:

```bash
python3 scripts/export_public_results.py
python3 -m http.server 8080 --directory public_results
```

Then visit <http://127.0.0.1:8080>.

The generated view includes all 10 configured model rows for qualifying and
final. A cell prefers a successful attempt with an effective organizer
finalization, then a reviewed attempt, then the newest successful attempt.
Answers remain clickable before finalization and are explicitly marked as not
finalized. Public scores come only from the shared manual final score or the
derived consensus of at least two unanimous extreme checks; individual-review
medians are not published. Math Cup 2026 qualifying
is displayed on the integer `0..4` scale; the final remains on `0..2`. The
three Math Cup 2026 final team rows come from `data.js`
and participate in the same table sorting as model rows rather than appearing
in a separate section.
The fallback team rows include the published member names for both 2026 stages.
Their source scoreboard contains penalties in solved cells; the public matrix
ignores those penalty values and converts only solved status to the final's
`0..2` task scale. Split tasks 6, 7 and 8 combine two equally weighted
subproblems, so one solved half is displayed as 1. Their official
prizes of 150,000 ₽, 100,000 ₽ and 50,000 ₽ are shown in the shared money
column in US dollars using the Central Bank of Russia rate for July 28, 2026
(78.0172 RUB per USD); the original ruble amount and conversion rate remain
available in the cell tooltip.

Each selected answer is copied into a small sanitized JSON document used by the
solution page. It includes the problem statement, unchanged model answer,
official solution, public score, per-attempt metrics, anonymized individual
expert scores and feedback, and an optional organizer finalization comment. It
deliberately excludes reviewer and organizer identities, raw provider/request
data, errors and internal filesystem paths. Run logs and evaluation sidecars
are only read and are never modified.

Each published stage is an independent release with its own URL and table.
Three visible button rows select benchmark, year and stage without a dropdown;
qualifying and final are never rendered together. Only releases present in the
public `releases` and `catalog` lists are shown; competition placeholders alone
do not make an unpublished release visible.
The competition-rules block follows the selected release: qualifying and final
explain their participant format, the corresponding one-attempt model
evaluation and the multi-expert final-verdict process separately. Shared
model-launch rules remain below it.

The solution page renders the exported problem statement, model answer and
official solution as sanitized GitHub-flavored Markdown. The required Marked,
DOMPurify and KaTeX browser assets (including fonts and their licenses) are
versioned under `vendor/`, so rendering does not depend on a third-party CDN.
A safe plain-text fallback remains in place. The renderer also replaces
KaTeX's private-use negation overlay when a browser/font combination exposes it
as a missing-glyph box. The task statement is collapsed by default, followed by
the expert-review cards and then the model solution. Model and official
solutions remain collapsible and open by default, and long prose is centered in
a wider reading column.

Every table column is sortable. The initial order is descending by `points`,
which is the sum of all published absolute task scores, not the count of
perfect answers. Cost/prize, sum, token and accuracy columns precede the task
columns. Task scores fill the complete table cell, aggregate values use a
larger type size, and competition-level costs are displayed to cents. The
participant column wraps full model, team and member names instead of eliding
them. The main-page hero uses the supplied CS Space 2026 formula-pattern SVGs directly
for desktop and mobile layouts; the logo is also served as a local SVG.

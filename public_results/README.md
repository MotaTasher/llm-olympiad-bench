# Reasoning Space public results

This is the standalone public Reasoning Space site. It contains:

- `index.html`: benchmark, year and stage filters plus one selected leaderboard;
- `competitions.html`: compact buttons for available competition releases;
- `solution.html`: full-width single-model solution reading layout;
- `task.html`: statement, official solution and all model answers for one task;
- `model.html`: aggregate model result and all of that model's answers;
- `data.js`: fallback release, team and catalog data;
- `contest-previews.js`: prepared Algo Cup stage with official top-three teams
  and null results for all configured models;
- `model-rosters.js`: versioned model IDs/names scoped to each competition;
- `code/solutions/`: sanitized accepted winner code, compiler and judge metrics;
- `vendor/highlight/`: pinned highlight.js 11.11.1 with its license and dark theme;
- `assets/csspace-logo.svg`: local vector CS Space logo used in headers and footers;
- `assets/formula-pattern-{desktop,mobile}.svg`: original formula artwork;
- `assets/torn-paper-mask.svg`: shared irregular silhouette for both hero layers;
- `assets/blue-paper-texture.svg`: blue pigment with the original paper grain;
- `assets/graphite-texture.svg`: retained original gray texture;
- `generated/`: ignored public export created from real logs and sidecars;
- `app.js`: release switching, generated-data merge and page rendering.
- `metrika.js`: shared Yandex Metrica tag for counter `100459978`.

The public URL contract uses clean, extension-free routes:

- `/` for the leaderboard;
- `/problems` for the published-problem catalog;
- `/problems/<competition-id>` for all statements and official solutions in a stage;
- `/problems/<competition-id>/<task-slug>` for every model answer to one task;
- `/problems/<competition-id>/<model-page-slug>` for every answer from one model;
- `/problems/<competition-id>/<task-slug>/<model-slug>` for a concrete model
  answer, for example `/problems/math-cup-2026-final/task1/gpt-5.6`.

Old `index.html`, `competitions.html`, `problem-set.html`, `model.html`,
`task.html` and query-string solution URLs
remain usable as compatibility entry points. On object storage, `/problems` and
every concrete competition, task, model or solution route are extensionless
HTML objects that contain the matching catalog, problem-set, task, model or
solution shell; all page assets use root-relative URLs.

Every public shell loads the same Yandex Metrica counter. The reverse proxy's
Content Security Policy must allow `https://mc.yandex.ru` in `script-src`,
`connect-src` and `img-src`; without `connect-src`, the tag loads but page-view
requests are blocked by the browser.

The exporter copies each selected competition's `assets/` directory into
`generated/assets/<competition-id>/` and rewrites `assets/...` references in
published statements and official solutions. It also turns plain HTTP(S)
links, including links accidentally wrapped in inline code, into clickable
Markdown links. The CS Space SVG is used as the favicon on every public page.

It deliberately does not import Flask, modify scoring routes, or write to run
logs and evaluation sidecars. Each export also removes obsolete generated
solution JSON files that are no longer referenced by the current projection.

Generate the current public projection, then open it locally:

```bash
python3 scripts/export_public_results.py
python3 scripts/export_contest_preview.py
python3 -m http.server 8080 --directory public_results
```

Then visit <http://127.0.0.1:8080>.

Model cohorts are pinned per competition. Math Cup retains its historical ten
models and exact generated answers; Algo Cup uses nine current flagships as of
2026-11-05, one per provider. Version keys remain distinct while `modelFamily`
keeps provider identity. The baseline table no longer filters models through
one global latest-model name list. Export `model-rosters.js` with the preview
and load it before app.js on every shell; never republish old results under new
model names. See [`MODEL_ROSTERS.md`](../docs/specs/MODEL_ROSTERS.md).

The Algo Cup 2026 qualifying preview uses contest **103053**. Its three teams
all solved four tasks; official ACM penalties **99 / 130 / 141** determine
their order. Models have empty scores, metrics and rank and are labelled
“Не запускалась” on their pages. No model calls or judge submissions have
been made. Original task links are published while complete statements and
submission write access remains unverified (existing report/source access works). The independent preview exporter never
touches the Math Cup generated snapshot. See
[`YANDEX_CONTEST.md`](../docs/specs/YANDEX_CONTEST.md) for provenance and kit
connection instructions. Stage-specific launch rules describe the planned
code format; existing math launch rules remain associated with Math Cup.

Winner result cells and names now open code solutions and team overviews.
All 12 first accepted submissions are published with Yandex verdict, compiler,
maximum execution time, peak memory, submission ID and elapsed contest time.
Code bypasses Markdown/math parsing and uses declared-language syntax
highlighting with original-source copy/download, including C++ and Python.
`scripts/import_contest_winners.py` imports existing submissions read-only;
the source/judge contracts and later explicit admin-submission workflow are in
[`CODE_JUDGING.md`](../docs/specs/CODE_JUDGING.md). No model submissions have
been made. Keep the current layout, typography and hero when updating code UI.

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
official solution, public score, per-attempt metrics and, when supplied, the
single collegially approved finalization comment. It deliberately excludes all
individual expert scores and comments, reviewer/organizer identities, raw
provider/request data, errors and internal filesystem paths. There is no public
`review.experts` list. Run logs and evaluation sidecars are only read and are
never modified.

The task and model overview pages show the selected attempt's cost, token count
and response time inside each answer card. A model page also repeats the
aggregate leaderboard rank, points, cost, tokens and accuracy above its tasks.

Each published stage is an independent release with its own URL and table.
Three visible button rows select benchmark, year and stage without a dropdown;
qualifying and final are never rendered together. Only releases present in the
public `releases` and `catalog` lists are shown; competition placeholders alone
do not make an unpublished release visible.
The competition-rules block follows the selected release: qualifying and final
explain their participant format, the corresponding one-attempt model
evaluation and the multi-expert final-verdict process separately. Shared
model-launch rules remain below it.

The owner-confirmed visual direction keeps the compact Reasoning layout and
the original formula-covered torn-paper hero, now with a dark navy pigment
and white formula writing on the paper. Secondary labels are brighter
and the description uses a solid dark panel.
The main CS Space site is the font/brand reference; its abstract liquid artwork
and large marketing-page gaps must not replace this composition. Details and
reference measurements are in
[`docs/specs/PUBLIC_DESIGN.md`](../docs/specs/PUBLIC_DESIGN.md).

Montserrat and Unbounded load through Google Fonts because the production
proxy permits fonts from `fonts.gstatic.com` but blocks local font files. QA
must verify real downloaded faces under this CSP and compare desktop/mobile
screenshots. A CSS family name alone does not prove that the correct font is
being rendered. Score colors and reading interactions retain their meaning.

Object Storage connection and publication commands are in root
[`AGENTS.md`](../AGENTS.md). Use the existing `yc` session first. Design-only
releases update assets, CSS and all HTML/extensionless shells while preserving
the deployed generated data.

The solution page renders the exported problem statement, model answer and
official solution as sanitized GitHub-flavored Markdown. It shows the shared
finalization-comment block only when that optional comment is non-empty. The required Marked,
DOMPurify and KaTeX browser assets (including fonts and their licenses) are
versioned under `vendor/`, so rendering does not depend on a third-party CDN.
A solution's score badge uses the same full/partial/zero/pending color as its
leaderboard cell. The verdict, score and metrics sit in one colored-outline
panel at the start of the single-cell page. When a shared final comment exists,
it appears in that same panel; without a comment the result panel remains. The
page order is result/comment, statement, model solution, official solution.
Final comments pass through the same sanitized Markdown and KaTeX renderer as
the solution text, including inline and display LaTeX.
A safe plain-text fallback remains in place. The renderer also replaces
KaTeX's private-use negation overlay when a browser/font combination exposes it
as a missing-glyph box. The statement, model answer and official solution are
collapsed by default, and long prose is centered in a wider reading column.
The browser remembers the independent open or closed state of all three
reading sections in local storage and restores it between tasks and later
visits. Reference cards keep a neutral outline; the result panel and model
answer use a solid dark surface with a score-colored outline: muted sage for a
full score, ochre for a partial score, terracotta for zero and graphite while
pending.
An expanded reading card also closes when its empty background is clicked;
clicking rendered text, formulas, links or controls does not close it.

Ranking and aggregate table columns are sortable; task headers open the task
page instead of sorting. The initial order is descending by `points`,
which is the sum of all published absolute task scores, not the count of
perfect answers. Cost/prize, sum, token and accuracy columns precede the task
columns. Task scores fill the complete table cell, aggregate values use a
larger type size, and competition-level costs are displayed to cents. The
participant column wraps full model, team and member names instead of eliding
them. The hero retains the original torn outline and formulas with the blue paper texture.

### Optional official solutions for code stages

Code-stage problem-set/task/individual pages hide their official-solution card
when no reference solution exists, and display it when added later. Math-stage
reference rendering is preserved. Generation works from the complete statement
alone; it never consumes reference solutions. The public model placeholders and
12 imported winner sources remain unchanged; no new runs were performed.

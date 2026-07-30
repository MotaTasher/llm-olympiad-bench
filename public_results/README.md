# Public results prototype

This is a standalone local prototype for the public CS Space Arena. It contains:

- `index.html`: benchmark, year and stage filters plus one selected leaderboard;
- `competitions.html`: compact buttons for available competition releases;
- `solution.html`: full-width model and official solution reading layout;
- `data.js`: fallback release, team and catalog data;
- `generated/`: ignored public export created from real logs and sidecars;
- `app.js`: release switching, generated-data merge and page rendering.

It deliberately does not import Flask, modify scoring routes, or write to run
logs and evaluation sidecars.

Generate the current public projection, then open it locally:

```bash
python3 scripts/export_public_results.py
python3 -m http.server 8080 --directory public_results
```

Then visit <http://127.0.0.1:8080>.

The generated view includes all 16 configured model rows for qualifying and
final. A cell uses the newest successful evaluated attempt when one exists and
otherwise the newest successful attempt. Unreviewed answers remain clickable
without a score. Scores from multiple evaluations are normalized and combined
with the median on the task's current absolute scale. Math Cup 2026 qualifying
is displayed on the integer `0..4` scale; the final remains on `0..2`. The
three Math Cup 2026 final team rows come from `data.js`
and participate in the same table sorting as model rows rather than appearing
in a separate section.
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
official solution, public score and per-attempt metrics. It deliberately excludes
reviewer identities and comments, raw provider/request data, errors and internal
filesystem paths. Run logs and evaluation sidecars are only read and are never
modified.

Each published stage is an independent release with its own URL and table.
Three visible button rows select benchmark, year and stage without a dropdown;
qualifying and final are never rendered together. Only releases present in the
public `releases` and `catalog` lists are shown; competition placeholders alone
do not make an unpublished release visible.

The solution page renders the exported problem statement, model answer and
official solution as sanitized GitHub-flavored Markdown. The required Marked,
DOMPurify and KaTeX browser assets (including fonts and their licenses) are
versioned under `vendor/`, so rendering does not depend on a third-party CDN.
A safe plain-text fallback remains in place. Both solution blocks are
collapsible and open by default.

Every table column is sortable. The initial order is descending by `points`,
which is the sum of all published absolute task scores, not the count of
perfect answers. Cost/prize, sum, token and accuracy columns precede the task
columns. Task scores fill the complete table cell, aggregate values use a
larger type size, and competition-level costs are displayed to cents. The
main-page hero uses optimized WebP derivatives of the supplied CS Space 2026
formula pattern SVGs for desktop and mobile layouts.

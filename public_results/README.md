# Public results prototype

This is a standalone local prototype for the public CS Space Arena. It contains:

- `index.html`: release buttons and sequential stage leaderboards;
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
with the median. The three Math Cup 2026 final team rows come from `data.js`.
Their source scoreboard contains penalties in solved cells; the public matrix
ignores those penalty values and converts only solved status to the same
0–100-per-task scale as model rows. Split tasks 6, 7 and 8 combine two equally
weighted subproblems, so one solved half is displayed as 50.

Each selected answer is copied into a small sanitized JSON document used by the
solution page. It includes the problem statement, unchanged model answer,
official solution, public score and per-attempt metrics. It deliberately excludes
reviewer identities and comments, raw provider/request data, errors and internal
filesystem paths. Run logs and evaluation sidecars are only read and are never
modified.

Each release is selected by a visible button. Its stages are never hidden behind
a dropdown: qualifying and final rounds render one after another on the same
page. Only releases present in the public `releases` and `catalog` lists are
shown; competition placeholders alone do not make an unpublished release
visible.

Every table column is sortable. The initial order is descending by `points`,
which is the sum of all published 0–100 task scores, not the count of perfect
answers. Task scores fill the complete table cell, aggregate values use a larger
type size, and competition-level costs are displayed to cents. The main-page
abstract is the same `abstract-home-2.png` asset used by the original CS Space
site.

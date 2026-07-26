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
with the median. The three team rows still come from the fallback file and
remain explicit placeholders until actual names, members and results are
provided.

Each selected answer is copied into a small sanitized JSON document used by the
solution page. It includes the problem statement, unchanged model answer,
official solution, public score and per-attempt metrics. It deliberately excludes
reviewer identities and comments, raw provider/request data, errors and internal
filesystem paths. Run logs and evaluation sidecars are only read and are never
modified.

Each release is selected by a visible button. Its stages are never hidden behind
a dropdown: qualifying and final rounds render one after another on the same
page. Stages without a published public matrix remain visible with an explicit
data-pending state.

# Public results prototype

This is a standalone local prototype for the public CS Space Arena. It contains:

- `index.html`: release buttons and sequential stage leaderboards;
- `competitions.html`: compact buttons for available competition releases;
- `solution.html`: full-width model and official solution reading layout;
- `data.js`: the only file that currently contains public snapshot data;
- `app.js`: release switching, stacked tables, catalog rendering and detail navigation.

It deliberately does not import Flask, modify scoring routes, or write to run
logs and evaluation sidecars.

Open it locally from the repository root:

```bash
python3 -m http.server 8080 --directory public_results
```

Then visit <http://127.0.0.1:8080>.

The 16 model rows are a static snapshot of the active scoring matrix and the
existing Math Cup 2026 final logs and evaluations. Unreviewed cells remain
visible without a score. The three team rows are explicit placeholders until
actual team names, members and results are provided. Model cells link to the
solution-page prototype; exporting complete immutable answers is intentionally
left for the next public-data contract.

Each release is selected by a visible button. Its stages are never hidden behind
a dropdown: qualifying and final rounds render one after another on the same
page. Stages without a published public matrix remain visible with an explicit
data-pending state.

# Production deployment map

This document describes the deployment roles, known service layout and data
flow. It deliberately does not contain SSH targets, private IP addresses or
credentials. Concrete connection and staging values belong in the gitignored
`config/server.env` file on an operator workstation.

## Services and ownership

| Role | Runtime | Owns | Must never publish |
| --- | --- | --- | --- |
| scoring/admin | authenticated Flask app behind Nginx | reviewer accounts, run logs, scoring sidecars and manual finalizations | auth DB, reviewer identities, individual scores/comments, raw provider data |
| standalone public results | Nginx in front of a Yandex Object Storage bucket | static HTML/CSS/JS, public assets and sanitized solution JSON | scoring/auth source data |
| local repository | development and operational source | code, competition definitions and versioned benchmark data | secret env files and private server configuration |

Public URLs and the Object Storage URI are recorded locally in
`config/server.env`. The scoring domain is reserved for the authenticated admin
application. Its retired `/results` and `/results/` paths return `410 Gone`.

## Scoring-host layout

The checked-in systemd unit files currently assume:

```text
/opt/olympiad-scorer/app/                 repository checkout
/opt/olympiad-scorer/venv/                Python environment
/opt/olympiad-scorer/shared/logs/         immutable model run logs
/opt/olympiad-scorer/app/data/results/    evaluation/finalization sidecars
/opt/olympiad-scorer/app/data/competitions/ competition and problem sources
```

The private auth database is `instance/scorer-auth.sqlite3` relative to the
checkout unless `SCORER_AUTH_DB` overrides it. The public exporter reads the
competition, log and sidecar directories but must never modify them.

The former `public-results-export.timer` compatibility exporter was disabled on
2026-08-06 and its checked-in unit files were removed. It must not be enabled
again: `/results/` is intentionally retired and Object Storage publication is a
separate operation.

## Standalone public site

The standalone domain is backed by the Object Storage bucket named in
`PUBLIC_RESULTS_S3_URI`. It contains:

```text
index.html, app.js, styles.css, data.js
assets/, vendor/
generated/data.js
generated/assets/<competition-id>/...
generated/solutions/<competition-id>/<result-id>.json
problems
problems/<competition-id>
problems/<competition-id>/<task-slug>
problems/<competition-id>/<model-page-slug>
problems/<competition-id>/<task-slug>/<model-slug>
```

`problems` is an extensionless copy of the catalog HTML. Every competition key
is an extensionless copy of `problem-set.html` with all statements and official
solutions for that stage. Every concrete task route is an extensionless copy of
the task shell, every model-page route is an extensionless copy of `model.html`,
and every concrete task/model route is an extensionless copy of the solution
shell. Task slugs use the `taskN` form, while model-page slugs use model names,
so the two-segment objects do not collide. Legacy `.html` objects remain for
compatibility. Upload solution JSON and assets before replacing
`generated/data.js`.

The public projection may contain the effective final score, sanitized solution
metrics and the optional collegially approved finalization comment as
`review.final.feedback`. It must omit reviewer/organizer identities, every
individual expert score or comment, `review.experts`, raw requests/responses,
errors, credentials and internal paths.

## Data flow

```text
model run -> run log on scorer
human review -> sidecar on scorer
finalization -> same sidecar
public exporter -> sanitized local snapshot
S3 publication -> standalone public domain
```

The scorer remains the source of truth. Object Storage is a projection, never a
write-back target. An automatic bridge to Object Storage has not been verified;
S3 publication is therefore an explicit operator action.

## Access boundaries

- `scripts/sync_logs.py` uses SSH/rsync targets from `config/server.env` for
  logs and sidecars; it is unrelated to public S3 publication.
- `yc storage s3 cp` publishes the sanitized static site. Successful bucket
  listing does not prove write access; use a uniquely named test object and
  remove only that object when checking permissions.
- SSH is not required for a manual S3 upload. It is required to change Nginx or
  services on the scorer host.
- Never copy `logs/`, `data/results/`, `instance/` or provider secret files to
  the public bucket.

## Operational verification

After publishing, verify:

1. the public root and `/problems` return `200` and `text/html`;
2. every route referenced by `generated/data.js` returns `200`;
3. every solution JSON either lacks `review` or contains only `review.final`;
   it never contains `review.experts`, evaluator/editor identities or individual
   expert feedback;
4. the scoring root still requires authentication and both `/results` forms
   return `410`;
5. the public `generatedAt` timestamp matches the intended scorer export;
6. an unknown clean route returns `404`.

Do not describe the sites as automatically synced until an S3 bridge has been
installed and verified independently of the retired scoring-host route.

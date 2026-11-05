# Instructions for coding agents

This is the primary instruction file for Codex and other repository agents.

## Mandatory first step

Before changing code or data, read:

1. [`docs/specs/INDEX.md`](docs/specs/INDEX.md)
2. the specifications linked there for the subsystem you will touch
3. the relevant source files and tests/validation commands

Do not start implementation from this file alone. `docs/specs/` is the project map and contract index.

## Project purpose

The project runs several text-only LLM adapters on olympiad problems, stores comparable run logs, provides a Flask UI for manual scoring, and exports scored datasets.

## Non-negotiable contracts

- Model requests are **text-only**. Do not add tools, browsing, code execution, function calling, or provider-side search without an explicit project-wide contract change.
- A model adapter returns `SolveResult`; provider/network errors are captured in `SolveResult.error`, not raised through `runner.py`.
- Run logs are immutable model-output records under `logs/<competition_id>/<problem_id>/<run_id>.json`; new logs use `schema_version: 2`, stable `result_id`, structured telemetry, and atomic incremental writes.
- Human evaluations are stored separately under `data/results/<competition_id>/<problem_id>/<run_id>.json`; new sidecars use `schema_version: 2` and key evaluations by `result_id`.
- Credentials belong only in `models/<provider>/secrets/.env` or private environment variables. Never print, commit, copy, or move secret values.
- Problem sets use `data/competitions/<competition_id>/competition.json` and direct child files `data/competitions/<competition_id>/<problem_id>.json`.
- Task files must not contain `competition_id` or `competition_title`; ownership comes from the parent competition directory.

## Change workflow

1. Read the spec index and identify affected contracts.
2. Inspect the implementation; do not trust documentation over code when they disagree.
3. Make the smallest compatible change.
4. Run the relevant validation commands.
5. Update documentation in the same change.
6. Report exactly what changed, what was verified, and what could not be verified.
7. Commit every completed coherent change and push it to the existing GitHub
   repository (`origin`, currently `MotaTasher/llm-olympiad-bench`). This is an
   explicit owner requirement: local changes or a local commit alone are not
   completion. Include code, affected documentation and authorized versioned
   data; scan staged contents for credentials first. Do not amend/force-push
   shared history or include unrelated work. Report branch and commit SHA.
   If access fails, preserve the local commit and state the exact blocker.
   Public-site changes must also be deployed to the configured public bucket
   with their HTML/extensionless routes and verified on the live site, unless
   the owner explicitly requests local-only work.

## Model versions per competition

Read [`docs/specs/MODEL_ROSTERS.md`](docs/specs/MODEL_ROSTERS.md) before model
updates. A competition pins `metadata.model_roster` to a versioned file under
`config/model_rosters/`; the public Algo Cup snapshot has the same top-level
field. Existing stages use `benchmark-2026-08-01`; Algo Cup uses
`flagships-2026-11-05` (nine models, one per provider). Create a new cohort ID
for future upgrades. Never edit a used roster or relabel old answers/scores as
a newer model. Version identity is `provider:model_id`; `modelFamily` is only
presentation metadata. Do not restore a global latest-model visibility filter.
New competitions must select a cohort before running. Rebuild and publish
`model-rosters.js` with the public projection; preserve historic `generated/`.

## Yandex Contest kit and the prepared Algo Cup stage

The owner supplied `yandex-contest-kit-239.zip` at the repository root. Read
[`docs/specs/YANDEX_CONTEST.md`](docs/specs/YANDEX_CONTEST.md) for the exact
temporary extraction, existing session lookup and verified read-only GETs.
Use contest **103053** for `algo-cup-2026-qualifying`. Admin web session cookies
are unrelated to S3 credentials; never print or copy the private auth file.
The current session reads the contest/problem-set list but individual problem
files return 403. Do not mistake this for verified submission access.

The current authorized scope publishes top-three team results, their selected
accepted code submissions/metrics and empty rows for every configured model.
**Do not run models or submit new code yet.** Read-only winner imports use
`scripts/import_contest_winners.py`. Rebuild the projection and sanitized code
documents with `scripts/export_contest_preview.py`; do not create fake logs,
human evaluations or incomplete canonical task files.

Code-generation infrastructure is ready: `runner.py --solution-format code
--code-language cpp|python` uses only the statement and writes attributed source
artifacts. Official answers/solutions are optional and never model inputs.
Direct defaults are the nine November models; historical cohorts and named
historical batch scripts must keep their original versions. No generation or
submission is authorized merely by changing/preparing calls. `--only-missing`
distinguishes math, C++ and Python. See `docs/LOCAL_SETUP.md` for later commands.

Code sources belong in `data/code_solutions/`; Yandex judgments belong in
`data/judge_results/`; submission outbox markers belong in `data/judge_jobs/`.
Read [`docs/specs/CODE_JUDGING.md`](docs/specs/CODE_JUDGING.md) before touching
these contracts. `scripts/judge_code.py submit` is a dry run by default.
`--execute` is a separate external action; the present no-submissions request
still applies. Future authorized submissions use the logged-in admin account,
with explicit local attribution to the model/result_id, never impersonation.

## Connecting to the public site and Object Storage

Use the existing **Yandex Cloud CLI (`yc`) session first**. Public-site files
live in Object Storage; uploading them does not require SSH, AWS CLI, a new
service account or another static access key. This workflow was verified on
2026-11-05, including a temporary upload, HTTPS origin read and deletion.

Run from the repository root. On the operator's Mac, `yc` is installed at
`$HOME/yandex-cloud/bin/yc`; add that directory to `PATH` if necessary. Inspect
profile **names** with `yc config profile list`. Do not print the full CLI
configuration: it may contain authentication tokens.

Read the destination from private configuration, not from remembered IPs:

```bash
public_results_uri="$(.venv/bin/python - <<'PY'
import os
from urllib.parse import urlsplit
from dotenv import dotenv_values

value = os.environ.get("PUBLIC_RESULTS_S3_URI") or dotenv_values("config/server.env").get("PUBLIC_RESULTS_S3_URI")
assert value, "Set PUBLIC_RESULTS_S3_URI in private config/server.env"
parsed = urlsplit(value)
assert parsed.scheme == "s3" and parsed.netloc and parsed.path in ("", "/"), "Expected a bucket-root s3:// URI"
assert not parsed.query and not parsed.fragment and "@" not in parsed.netloc
print("s3://" + parsed.netloc + "/")
PY
)"
public_results_bucket="${public_results_uri#s3://}"
public_results_bucket="${public_results_bucket%/}"

yc storage bucket get --name "$public_results_bucket"
yc storage s3api list-objects-v2 --bucket "$public_results_bucket" --max-keys 10
yc storage bucket get-https --name "$public_results_bucket"
```

The correct listing command is `yc storage s3api list-objects-v2`;
`yc storage s3 ls` does not exist. To read a known object or publish an explicitly
requested change:

```bash
yc storage s3 cp "${public_results_uri}index.html" /tmp/reasoning-current-index.html
# After preparing and validating the requested replacement:
yc storage s3 cp public_results/styles.css "${public_results_uri}styles.css" --content-type text/css
```

Read access alone does not prove write access. When a write preflight is needed,
upload one uniquely named, harmless test object, read it back, then delete only
that same object and verify `404`. Do not overwrite an existing object as a
permissions test. Never upload the repository root, secrets, logs, score
sidecars or the auth database. Upload new assets before the HTML that uses them;
update the exact extensionless route objects as well as `.html` shells. A
design-only publication must preserve the deployed `generated/` snapshot.

If `yc` authentication has actually expired, reauthenticate the existing
profile. Use the AWS `yc-storage` profile only when it is already configured
or the operator specifically requests AWS setup; never ask for secret keys in
chat. Its endpoint is `https://storage.yandexcloud.net`, region `ru-central1`.

TLS on the public reverse proxy and TLS on the bucket are separate. Inspect the
certificate ID returned by `get-https` with
`yc certificate-manager certificate get --id <certificate-id>`; do not export
certificate contents/private keys. Follow the HTTPS procedure in
[`OPERATIONS.md`](docs/specs/OPERATIONS.md). An expired public certificate does
not prevent authenticated S3 work. SSH is needed only for server operations;
use independently verified host keys and the current private connection
inventory, never disable host-key verification or assume the bucket hostname
is the scorer host. Do not reopen intentionally disabled scoring routes.

### Remote TLS maintenance without an old SSH key

The public proxy was successfully repaired on 2026-11-05 through the existing
cloud identity's **OS Login**, not a legacy private key. Its Ubuntu 24.04 image
already includes the OS Login agent. Private `config/server.env` now records
`PUBLIC_RESULTS_VM_ID`, `PUBLIC_RESULTS_VM_FOLDER_ID`,
`PUBLIC_RESULTS_OSLOGIN_ORGANIZATION_ID`, `PUBLIC_RESULTS_SSH_USER`,
`PUBLIC_RESULTS_SSH_HOST_FINGERPRINT`, `PUBLIC_RESULTS_PROXY_CONTAINER`,
`PUBLIC_RESULTS_CERTBOT_WEBROOT`, `PUBLIC_RESULTS_RENEW_COMMAND` and
`PUBLIC_RESULTS_RENEW_TIMER`. Read these named values with `dotenv_values`;
never dump all configuration or ask for a secret key in chat.

If SSH maintenance is required and legacy keys are unavailable:

1. Verify the VM image supports OS Login and record the original
   `enable-oslogin` metadata value. Use the existing cloud identity and roles;
   do not change organization settings or grant new IAM permissions.
2. If needed, temporarily enable only that metadata key with
   `yc compute instance add-metadata <vm-id> --metadata enable-oslogin=true`.
   Check that every other metadata field and existing SSH key is preserved.
3. Create a mode-700 temporary directory and use
   `yc compute ssh certificate export --organization-id <organization-id> --login <user> --directory <directory>`.
   This creates a short-lived SSH identity; it does not export the TLS private
   key. Use strict host-key verification against the independently verified
   fingerprint in the private inventory.
4. Nginx runs in the recorded **Docker container**, not `nginx.service` on the
   host. Run the installed renewal command with `sudo`, and test with
   `sudo <renew-command> --dry-run --run-deploy-hooks`. The wrapper uses the
   existing webroot, excludes legacy directory hooks that stop the container,
   checks Nginx configuration and reloads only after a successful renewal.
5. Verify the recorded systemd timer is enabled/active and check public HTTPS
   using normal certificate and hostname validation, never `curl -k` as proof.
6. Restore the original OS Login metadata value. If the key was absent, remove
   only it with `yc compute instance remove-metadata <vm-id> --keys enable-oslogin`;
   never use `--all`. Delete the temporary SSH identity and certificate.

## Public-site design source

Before a visual change, read [`PUBLIC_DESIGN.md`](docs/specs/PUBLIC_DESIGN.md).
Use the **current production CS Space design**, checked against the other
buckets and live pages, for spacing, typography, colors, radii and interaction
states. Preserve the owner's corrected direction: the compact Reasoning
layout and formula-covered torn-paper hero, recolored blue. Do not replace it
with the main site's abstract artwork, staggered uppercase headings or large
marketing-page gaps. The public site is the typography/brand reference and
production LMS is the shared-component cross-check. Development and seasonal sites are not default
replacements for the production design.

The blue paper must stay dark enough for white text. Its formula writing must
be white, not a faint gray layer. Use a solid dark description panel and
readable secondary labels; prioritize text
contrast over decorative brightness and check it on the rendered background.

For bucket-built sites, download `index.html` first and follow its actual CSS
links. Buckets contain old hashed builds: the newest-looking filename or an
arbitrary `assets/index-*.css` is not a reliable source. Inspect desktop and
mobile computed styles, then verify the changed Reasoning pages at the same
viewport sizes and compare the screenshots visually. Verify actual downloaded
fonts under the production CSP: the proxy currently allows fonts from
`fonts.gstatic.com` but blocks local fonts. A computed family name or an
installed fallback is not proof of correct font loading. Preserve
benchmark-specific scoring colors and data behavior.

## Documentation update matrix

| Changed area | Documentation that must be reviewed |
| --- | --- |
| repository layout or a new subsystem | `docs/specs/PROJECT_MAP.md`, `docs/specs/INDEX.md` |
| problem, competition, log, or score JSON | `docs/specs/DATA_CONTRACTS.md`, `docs/ADDING_PROBLEMS.md` |
| `runner.py` or CLI flags | `README.md`, `docs/specs/ARCHITECTURE.md`, `docs/LOCAL_SETUP.md` |
| model adapter, aliases, env loading, text-only policy | `docs/specs/MODEL_ADAPTERS.md`, provider README |
| Flask routes, templates, score persistence | `docs/specs/SCORING_WEB.md`, `docs/LOCAL_SETUP.md` |
| server sync or export scripts | `SERVER.md`, `docs/specs/OPERATIONS.md` |
| dependencies or setup commands | `requirements.txt`, `README.md`, `docs/LOCAL_SETUP.md` |
| public-site layout, styling or brand assets | `docs/specs/PUBLIC_DESIGN.md`, `public_results/README.md`, `docs/specs/OPERATIONS.md` |
| recurring failure mode | `docs/specs/TROUBLESHOOTING.md` |

A code change is incomplete when its affected documentation is stale.

## Validation

Run from the repository root:

```bash
python -m compileall -q runner.py models scripts scoring
python scripts/validate_problem_data.py data/competitions --all --strict
python scripts/export_scoring.py --all --output /tmp/olympiad-scorer-check.csv
```

For web changes, also run the Flask test-client smoke check described in `docs/LOCAL_SETUP.md`.

Provider API smoke tests are optional when credentials are unavailable. In that case, verify import/compile behavior and state that external calls were not tested.

## Fast fault localization

Use [`docs/specs/TROUBLESHOOTING.md`](docs/specs/TROUBLESHOOTING.md). Start with the persisted artifact:

- no log file: `runner.py`, env loading, adapter creation
- log exists with `error`: provider adapter or credentials/runtime configuration
- log is valid but absent from UI: `scoring/app.py`, working directory/path, malformed metadata
- score not saved: `/score` route, sidecar path, write permissions
- export misses rows: sidecar/run IDs or `scripts/export_scoring.py`
- sync fails: `scripts/sync_logs.py`, `config/server.env`, SSH/rsync

## Repository hygiene

Logs and scoring sidecars are versioned project data. Before committing new files
under `logs/` or `data/results/`, scan for accidental credentials. Do not modify
existing generated logs, scoring sidecars, notebooks, or sample datasets unless
the task requires it. Never add `__pycache__`, `.DS_Store`, `__MACOSX`, virtual
environments, private server config, or real secret files to an archive or
commit.

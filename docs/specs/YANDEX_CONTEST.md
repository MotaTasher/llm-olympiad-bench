# Yandex Contest: prepared code-solution stage

## Current scope (2026-11-05)

Contest **103053**, **CS Space. Algo Cup (Отборочный тур, 2026)**, ran on
November 4, 2026 with a three-hour virtual duration and four tasks (A–D).
The [official standings](https://contest.yandex.ru/contest/103053/standings/)
are the source for the three published teams, member names, accepted-task
flags and ACM penalties **99 / 130 / 141**. Preserve the official totals;
rounded per-task display times do not necessarily sum to the official penalty.

The public stage is `algo-cup-2026-qualifying`. It publishes the winners'
12 original first-accepted code submissions, compiler, verdict, execution
time and memory. See [`CODE_JUDGING.md`](CODE_JUDGING.md) for source/judgment
schemas, import commands and the future admin submission interface.
It shows all configured model
columns with `null` scores, metrics and solution references, `runStatus:
not_started`, and no rank. These are placeholders, not zero scores or attempts
awaiting review. There are no new run logs or scoring sidecars.

`data/public_results/algo-cup-2026-qualifying.json` is a curated public
standings snapshot, **not** a canonical problem set. It contains the top
three teams, selected code-artifact references and task metadata. Complete statements, samples and limits have
not been imported: the current session can read contest metadata and the
problem-set list, but individual problem settings and files return **403**.
The site links to the original conditions rather than publishing incomplete
statements. Do not create dummy canonical task files.

Rebuild the public projection after model configuration or snapshot changes:

```bash
.venv/bin/python scripts/export_contest_preview.py
.venv/bin/python -m unittest discover -s tests -p 'test_contest_preview.py'
```

This command is entirely local. It writes `public_results/contest-previews.js`
and allowlisted documents under `public_results/code/solutions/`;
it does not run models, submit solutions, alter the Math Cup export or contact
Yandex. All public shells load this file before `app.js`. The public table
uses solved count descending and penalty ascending for ACM ties. Unknown
costs, prizes and tokens stay empty.

No Dev Reasoning host/bucket was found in the current DNS, cloud buckets,
proxy configuration or private project configuration. The owner explicitly
authorized publishing this stage on the main Reasoning site in that case.
Keep the existing layout, fonts, white formulas and blue torn-paper background.

## Exact kit connection procedure

The supplied archive is **`yandex-contest-kit-239.zip` in the repository root**.
It contains `contest_kit/` and `legacy/contest_cli.py`. This kit targets the
**unofficial admin web API** at `https://admin.contest.yandex.ru`; its session
cookie authentication is separate from Yandex Cloud/S3 credentials and the
public Contest OAuth API.

Extract it into a private temporary working directory; do not run `install.sh`
for read-only inspection (it also changes Claude client configuration):

```bash
contest_kit_tmp="$(mktemp -d /tmp/reasoning-contest-kit.XXXXXX)"
.venv/bin/python - "$contest_kit_tmp" <<'PY'
import sys, zipfile
from pathlib import Path, PurePosixPath

destination = Path(sys.argv[1])
with zipfile.ZipFile('yandex-contest-kit-239.zip') as archive:
    for name in archive.namelist():
        path = PurePosixPath(name)
        assert not path.is_absolute() and '..' not in path.parts
    archive.extractall(destination)
PY
export PYTHONPATH="$contest_kit_tmp/yandex-contest-kit-239${PYTHONPATH:+:$PYTHONPATH}"
```

Use the existing repository virtual environment (`requests` is required).
`auth.resolve()` checks private `CONTEST_KIT_COOKIE` / `CONTEST_KIT_CSRF`, then
`~/.config/contest-kit/auth.json`, then the kit's browser-cookie fallback.
The existing auth file worked on 2026-11-05. Never print its contents or copy
it to the repo, staging directory, public bucket or an archive. Do not dump
request headers, credential objects or complete admin responses.

Minimal verified read-only access, printing only public task aliases:

```bash
.venv/bin/python - <<'PY'
from contest_kit import auth
from contest_kit.http import Client

client = Client(auth.resolve())
contest = client.json('GET', '/api/admin/contest/103053',
                      referer='/contests/103053/settings')
print(contest['id'], contest['name'])
problem_set = client.json('GET', '/api/admin/contests/103053/problemset',
                          params={'fields': 'problems,id'},
                          referer='/contests/103053/problems')
for problem in problem_set['problems']:
    print(problem['title'], problem['name'])
PY
```

Submission list/details/sourceCode access works despite the problem-file 403.
Use `scripts/import_contest_winners.py` for the authorized read-only import.
The API may return more fields than requested. Persist only explicitly
allowlisted public metadata, never a raw admin response. The problem-set
endpoint includes statement sections but may omit samples/limits. A successful
contest GET does not prove permission to edit tasks or submit code. Individual
problem IDs contain slashes; use the kit's `problem_id_encoded()` for URL paths
and `encode_file_path()` for file paths. If auth expires, use the kit's browser
login command after reading its setup docs; never request cookies in chat.

## Next implementation boundary

The owner explicitly requested **no runs or submissions yet**. Do not execute
the kit's upload, submit, clone or contest-standard-settings commands while
preparing this stage. Existing math prompts, adapters, logs and human-score
contracts remain unchanged.

Code artifact and judgment contracts plus the explicit submit/refresh CLI are
implemented in [`CODE_JUDGING.md`](CODE_JUDGING.md). The actual submission
write path is mock-tested, not exercised remotely. Before enabling model code
runs, agree a code-only prompt/request budget and import complete statements,
samples and limits. Model requests remain text-only; execution belongs to the
external judge. No model generation, polling worker or automatic publication
of model judge scores is enabled by this release.

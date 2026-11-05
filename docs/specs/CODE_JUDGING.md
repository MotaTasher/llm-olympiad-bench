# Code sources and Yandex judgments

## Scope and boundaries

The public Algo Cup stage supports code viewing for the three winning teams.
Their **12 first accepted submissions inside the original three-hour contest
window** were imported read-only from contest **103053**. Each source remains
byte-for-byte equivalent to the UTF-8 encoding of the API's `sourceCode`
string, including whitespace; we do not rewrite or execute participant code.
All imported winners used **C++23 (GCC 14.1)**, verdict `OK`.

No new model calls, submissions or rejudging were performed. Model rows still
have `null` scores/metrics and `runStatus: not_started`. The existing math
prompts, logs, human evaluation files and Flask scoring flow are unchanged.

`judging/` owns the new external-judge boundary. Model generation stays
text-only. A generated source artifact references its immutable original
`result_id`, `run_id` and model key; external execution never goes through a
provider adapter or changes a model-output log.

## Source artifact (schema_version 1)

Path: `data/code_solutions/<competition_id>/<problem_id>/<solution_id>.json`.

```json
{
  "schema_version": 1,
  "id": "code_<24 hex characters>",
  "format": "code",
  "competition_id": "algo-cup-2026-qualifying",
  "problem_id": "task_01",
  "author": {"type": "model", "id": "openai-gpt-5.6-sol", "name": "GPT-5.6 Sol"},
  "source": {
    "language": "cpp",
    "filename": "solution.cpp",
    "code": "<exact source text>",
    "sha256": "<SHA-256 of UTF-8 source bytes>",
    "encoding": "utf-8"
  },
  "origin": {"kind": "model_generation"},
  "generation": {"result_id": "res_...", "run_id": "...", "model_key": "openai:gpt-5.6-sol"}
}
```

`author.type` is `team` or `model`. Imported teams have `generation: null` and
an origin containing `kind: yandex_contest`, original contest/submission IDs
and `selection: first_accepted_in_contest`. The stable source ID hashes
competition, problem, author ID, language and source SHA-256. Rewriting an
artifact with different contents is rejected. It is separate from a judge
submission: the same source can have an independently recorded judgment.

Default languages/compilers are **`cpp` → `gcc14_cpp23`** and
**`python` → `python3_13`**. Explicit alternatives are C++20 (`gcc_cpp20`) and
PyPy (`pypy3_7_1_0`). The actual compiler must also be enabled in the target
contest. Never infer the language from model name. Inputs are UTF-8, nonempty,
at most 262144 bytes. Preparation consumes an explicit source file; it does
not extract arbitrary Markdown fences or execute code.

## Judge record (schema_version 1)

Path:
`data/judge_results/<competition_id>/<problem_id>/<solution_id>/<submission_id>.json`.

Fields: `solution_id`, `competition_id`, `problem_id`, `judge: yandex_contest`,
`contest_id`, `problem_alias`, `submission_id`, `compiler_id`, `compiler_name`,
`status`, `verdict`, `score`, `metrics`, `submitted_at`, `time_from_start_ms`,
`ignored_in_monitor`, and administrative `source_url`.

- `metrics.time_ms`: maximum execution time in **milliseconds** reported by
  `usedTimeMillis`; refresh without a list summary falls back to the maximum
  test `runningTime`. It is **not generation latency** or total contest time.
- `metrics.memory_bytes`: peak memory in **bytes**, `usedMemoryBytes`, with
  fallback to the maximum test `memoryUsed`. The UI converts bytes to MiB.
- Missing metrics are `null`; a reported zero remains zero.
- `submitted_at`: ISO timestamp in UTC; `time_from_start_ms`: elapsed time from
  this participant's virtual start. The UI displays submission dates in Moscow
  time and elapsed time separately.
- `status` is lowercase provider state. Only `finished` has an ACM score:
  `OK` → 1, other finished verdicts → 0; unfinished → `null`.
- The record is a refreshable judge observation. It never overwrites the
  immutable source or original generation log. A new submission gets another
  record; human evaluations remain under their existing separate contract.

Import/report conversion uses an allowlist. **Never persist raw admin
responses**, IP addresses, worker hosts, compiler logs, private user identities,
hidden test names/contents, cookies, CSRF tokens or signed download/upload URLs.
Per-test details are used only in memory to calculate aggregate metrics.

## Read-only import and public projection

Use the exact connection procedure in [`YANDEX_CONTEST.md`](YANDEX_CONTEST.md).
The existing session can read submission lists, report details and `sourceCode`
even though individual **problem files/settings** return 403.

```bash
python scripts/import_contest_winners.py --kit-dir /private/path/yandex-contest-kit-239
python scripts/export_contest_preview.py
```

The import filters by the three known participant IDs, excludes ignored,
failed and out-of-contest submissions, chooses the earliest accepted source per
task, and checks the detailed report's contest, author, problem and verdict.
List pagination uses page indexes of at most 100 entries, not record offsets;
the server's `total` does not reflect participant filters.

The public export writes `public_results/code/solutions/<solution_id>.json`
and updates team solution references in `contest-previews.js`. It validates
source hashes and team/task/contest bindings and exports only accepted,
non-ignored selections. Its allowlisted documents contain source, author,
task metadata and public judge metrics. They do not contain model requests,
expert evaluations, generation internals or private admin metadata. Math Cup's
existing `generated/` snapshot is not rewritten.

Team names, result cells, task pages and team overview pages open the same
solution reader as math answers. Code bypasses Markdown and KaTeX: raw text is
inserted with `textContent`, then locally vendored highlight.js highlights the
declared language. C++ and Python are supported, unknown display languages
fall back to readable escaped text. Copy and download use the original source,
not highlighted HTML. Long lines scroll inside the code block on mobile.
Judge execution time and memory remain separate from model cost/tokens/latency.

## Future administrative submissions

The current owner instruction is **no new submissions or model runs yet**.
The following interface is implemented and mock-tested for later authorized
use; the real write path has **not** been exercised on the contest.

1. Generate code in the existing text-only model flow under a separately
   agreed code prompt and record its immutable result. No code prompt or
   `runner.py` behavior has been changed in this task.
2. Prepare a source artifact locally:

   ```bash
   python scripts/judge_code.py prepare --source /path/solution.cpp --language cpp \
     --competition algo-cup-2026-qualifying --task task_01 \
     --author-id openai-gpt-5.6-sol --author-name 'GPT-5.6 Sol' \
     --model-key openai:gpt-5.6-sol --result-id res_REAL --run-id REAL_RUN
   ```

3. Review the **offline dry run**, which needs no kit/session and writes no
   job marker:

   ```bash
   python scripts/judge_code.py submit --solution /path/code_ID.json \
     --contest 103053 --problem-id 'group/date/problem-id' --alias A
   ```

4. Only after authorization, add `--execute --kit-dir /private/path/to/kit`.
   Preflight verifies contest compiler and exact problem ID/alias. The kit
   obtains an upload policy, a **separate HTTP session without admin cookies**
   uploads source, then the admin API receives `problemId`, `compilerId`,
   `fileName`, `s3Id`. No `participantId` or impersonation field is sent:
   **all new submissions belong to the authenticated admin**. Local
   `solution_id`/generation references distinguish models and agents.
5. Refresh a known submission with a read-only call:

   ```bash
   python scripts/judge_code.py refresh --solution /path/code_ID.json \
     --contest 103053 --submission ACTUAL_ID --kit-dir /private/path/to/kit
   ```

Submission outbox markers are written **before any upload/POST** to
`data/judge_jobs/<competition>/<problem>/<solution>.json` using exclusive file
creation. They store the plan, source hash, state and returned submission ID.
An uncertain timeout becomes `outcome_unknown` without persisting an exception
that could contain a signed URL. A second invocation cannot silently resubmit
that source. Inspect the admin submissions and reconcile the ID first; never
delete a marker merely to retry. This is a local outbox, not a distributed
lock: use one submitting operator/checkout, synchronize versioned state before
future runs, and coordinate other agents. No polling loop, remote worker or
automatic model-score publication is enabled yet.

## Browser validation

`scripts/check_public_code.cjs` is the reusable Chrome/playwright-core smoke
check. Set `PLAYWRIGHT_MODULE` to the installed `playwright-core` module path
if it is not on Node's module search path; optionally set `CHROME_EXECUTABLE`.
Start the local static server on port 8765, then run
`node scripts/check_public_code.cjs`. To verify production, pass the HTTPS
site origin as its first argument. Synthetic Python/XSS-shaped source exists
only in an intercepted browser response and is never published. Screenshots
and exact-source download checks go into a printed temporary directory.

## Validation

```bash
python -m unittest discover -s tests -p 'test_code_judging.py'
python -m unittest discover -s tests -p 'test_contest_preview.py'
python -m unittest discover -s tests -p 'test_*public_results*.py'
python -m compileall -q runner.py models scripts scoring judging
```

Tests cover exact source hashes, language/compiler defaults, dry-run isolation,
admin submit payload/preflight with mocked HTTP, uncertain-outcome protection,
pagination, private-field exclusion, source selection and all 12 public
documents. Browser QA covers C++/Python highlighting, raw copy/download,
desktop/mobile overflow, team/task navigation and existing math rendering.

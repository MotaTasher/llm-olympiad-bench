# Data contracts

## Competition manifest

Canonical path:

```text
data/competitions/<competition_id>/competition.json
```

Canonical object:

```json
{
  "schema_version": 1,
  "id": "school_2026",
  "title": "Школьная олимпиада 2026",
  "description": null,
  "date": null,
  "source": null,
  "metadata": {}
}
```

Required fields:

- `schema_version`: integer;
- `id`: stable non-empty string matching the competition directory name;
- `title`: human-readable non-empty string.

Optional fields may be omitted or set to `null` where appropriate. Unknown additional fields are allowed. `metadata` is the place for arbitrary extra structured data.

## Problem file

Canonical path:

```text
data/competitions/<competition_id>/<problem_id>.json
```

Canonical object:

```json
{
  "schema_version": 1,
  "id": "task_01",
  "number": 1,
  "title": "Название задачи",
  "statement": "Полное условие...",
  "answer": null,
  "solution": null,
  "tags": [],
  "metadata": {}
}
```

Required fields:

- `schema_version`: integer;
- `id`: stable non-empty string matching the filename stem;
- `statement`: complete non-empty problem statement.

Optional known fields:

- `number`: integer, string, or `null`;
- `title`: non-empty string when present;
- `answer`: string or `null`;
- `solution`: string or `null`;
- `tags`: list of strings;
- `metadata`: object.

Problem files must not contain `competition_id` or `competition_title`; ownership is determined by the parent directory. Unknown additional fields are allowed and must be preserved by migrations and import workflows.

`competition.json` is not a problem. `assets/`, hidden files, temporary files, directories and unknown non-JSON files are ignored by normal problem discovery.

## Ordering

Problem listing order is stable:

1. by `number` when present;
2. then by `id`.

Displayed competition titles come from `competition.json.title`. Displayed problem titles come from `title`; if it is missing, the safe fallback is `Задача <number>` or the problem `id`.

## Run log

Canonical path:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

New shape written by `runner.py` uses `schema_version: 2`:

```json
{
  "schema_version": 2,
  "run_id": "2026_06_28_12_00_00_first_pass",
  "timestamp": "2026-06-28T12:00:00Z",
  "started_at": "2026-06-28T12:00:00Z",
  "completed_at": "2026-06-28T12:03:10Z",
  "duration_ms": 190000,
  "status": "completed",
  "git_hash": "abc1234",
  "git": {
    "hash": "abc1234",
    "full_hash": "abc1234...",
    "branch": "main",
    "dirty": false
  },
  "runtime": {
    "command": ["runner.py", "--problem", "data/competitions/school_2026/task_01.json", "--models", "gpt"],
    "cli": {"models": "gpt", "allow_env_model_overrides": false},
    "requested_models": ["gpt"],
    "python": {"version": "3.11.9"},
    "platform": {"system": "Darwin"},
    "packages": {"openai": "2.0.0"},
    "environment": {"OPENAI_MAX_COMPLETION_TOKENS": "4096"}
  },
  "requested_models": ["gpt"],
  "competition_id": "school_2026",
  "competition_title": "Школьная олимпиада 2026",
  "competition": {},
  "problem_id": "task_01",
  "problem_number": 1,
  "problem_title": "Название задачи",
  "problem_file": "data/competitions/school_2026/task_01.json",
  "problem_text": "Полное условие...",
  "problem": {},
  "problem_hash": "sha256...",
  "problem_text_hash": "sha256...",
  "system_prompt": {
    "version": "2026-06-29",
    "sha256": "sha256...",
    "text": "Полный system prompt..."
  },
  "runtime_settings": {
    "text_only": true,
    "sequential": true,
    "reasoning_budget_tokens": 8000,
    "max_final_tokens": 8000
  },
  "results": [
    {
      "result_id": "res_0123456789abcdef01234567",
      "result_index": 0,
      "provider": "openai",
      "alias": "gpt",
      "adapter_class": "models.gpt.gpt.GPTModel",
      "requested_model_id": "gpt-5.5",
      "resolved_model_id": "gpt-5.5-20260601",
      "model": "provider-model-id",
      "attempt": 1,
      "started_at": "2026-06-28T12:00:01Z",
      "completed_at": "2026-06-28T12:03:10Z",
      "status": "success",
      "request": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-5.5",
        "messages": [
          {"role": "system", "content": "Полный system prompt..."},
          {"role": "user", "content": "Полное условие..."}
        ],
        "stream": false
      },
      "answer": "Решение модели",
      "prompt_tokens": 100,
      "completion_tokens": 500,
      "cost_usd": 0.001,
      "latency_ms": 1200,
      "usage": {
        "input_tokens": 100,
        "output_tokens": 500,
        "total_tokens": 600,
        "reasoning_tokens": null,
        "cached_input_tokens": null,
        "cache_creation_input_tokens": null,
        "raw": {},
        "source": "provider_response"
      },
      "timing": {
        "wall_ms": 1200,
        "monotonic_ms": 1200,
        "time_to_first_token_ms": null,
        "reasoning_ms": null,
        "retry_durations_ms": [],
        "attempts_total_ms": 1200,
        "source": "runner"
      },
      "cost": {
        "currency": "USD",
        "input": 0.00025,
        "output": 0.00075,
        "cached_input": null,
        "reasoning": null,
        "total": 0.001,
        "pricing_source": "models/gpt/gpt.py",
        "pricing_version": "2026-06-29",
        "estimated": true,
        "exchange_rate": null
      },
      "finish_reason": "stop",
      "provider_request_id": "req_...",
      "response_id": "chatcmpl_...",
      "provider_timestamp": 1782427699,
      "raw_response": {},
      "error": null,
      "error_info": null,
      "score": null,
      "scored_by": null,
      "scored_at": null,
      "score_comment": null
    }
  ]
}
```

Run status is `running`, `completed`, `partial` or `failed`. Result status is `running`, `success` or `error`. The runner creates the run-log before the first provider call, appends a `running` result before each model call, and atomically rewrites the JSON through a temporary file plus `os.replace` after each result. `runtime_settings.reasoning_budget_tokens` and `runtime_settings.max_final_tokens` are request-scoped limits when supplied by a programmatic caller; they may be `null` for ordinary CLI defaults.

`competition_id`, `competition_title`, `problem_id` and `problem_title` for new logs are derived from the canonical competition and problem files unless explicitly overridden by CLI flags. Old logs without `schema_version` remain readable through `models.telemetry.normalize_run_log()` and are not migrated on disk.

`score*` fields remain in new run entries for backward compatibility. The authoritative current evaluations are sidecars.

When runner receives a unified output-token ceiling, the value is recorded as
`runtime.cli.max_tokens` and `runtime_settings.max_tokens`. Adapter request
snapshots also include the provider-specific request key used for that ceiling,
for example `max_completion_tokens`, `max_tokens` or `maxTokens`.
When runner is invoked with `--pipeline draft-final`, `runtime_settings.pipeline`
records the pipeline mode plus draft/final token caps. The corresponding result
remains a single scorable row whose `answer` is the finalizer output. Its
`request.pipeline` identifies the mode, and `raw_response.pipeline_steps`
contains the redacted draft and final step logs. The finalizer input is only the
draft answer text, not the original problem statement as a separate field.

Do not mutate `results[]` order after a score sidecar exists.

Requests, raw responses, errors and tracebacks are recursively redacted before persistence. API keys, Authorization headers, cookies, client secrets, credentials and token values that are credentials must not be stored. Token-count fields such as `prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens`, `max_tokens` and `time_to_first_token_ms` are not secrets.

## Scoring sidecar

Canonical path:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

New sidecar shape:

```json
{
  "schema_version": 2,
  "competition_id": "school_2026",
  "problem_id": "task_01",
  "run_id": "2026_06_28_12_00_00_first_pass",
  "updated_at": "2026-06-28T12:10:00Z",
  "evaluation_pool": {
    "res_0123456789abcdef01234567": [
      {
        "evaluation_id": "ev_0123456789abcdef0123456789abcdef",
        "result_id": "res_0123456789abcdef01234567",
        "result_index": 0,
        "model_key": "openai:gpt-5.5",
        "model": "provider-model-id",
        "evaluator": "reviewer",
        "score": 8,
        "max_score": 10,
        "score_category": "partial",
        "feedback": "Комментарий",
        "created_at": "2026-06-28T12:10:00Z",
        "updated_at": "2026-06-28T12:10:00Z"
      }
    ]
  },
  "evaluations": {
    "res_0123456789abcdef01234567": {
      "evaluation_id": "ev_0123456789abcdef0123456789abcdef",
      "result_id": "res_0123456789abcdef01234567",
      "result_index": 0,
      "model_key": "openai:gpt-5.5",
      "model": "provider-model-id",
      "evaluator": "reviewer",
      "score": 8,
      "max_score": 10,
      "score_category": "partial",
      "feedback": "Комментарий",
      "created_at": "2026-06-28T12:10:00Z",
      "updated_at": "2026-06-28T12:10:00Z"
    }
  }
}
```

`evaluation_pool` is authoritative and stores all manual checks for a result. A
single model answer can have multiple checks from one or more reviewers.
`evaluations` is a compatibility snapshot of the latest check for each
`result_id`; it must not be treated as the full history.

The evaluation key for new writes is `result_id`. Readers use this precedence:

1. `evaluation_pool` keyed by `result_id`;
2. old sidecar `evaluations` keyed by `result_id`;
3. old sidecar `evaluations` keyed by string result index, for example `"0"`;
4. legacy `score`, `scored_by`, `scored_at` and `score_comment` inside the run-log.

Manual scoring must not be written back into run logs. Server-side score validation uses `problem.metadata.max_score`, then `competition.metadata.max_score`, then fallback `10`.
For new web-scoring writes, `evaluator` is the authenticated
`current_user.username` from the scoring site session. Older sidecars with any
string `evaluator` remain valid and readable.

## Validation

Validate one competition:

```bash
python scripts/validate_problem_data.py data/competitions/<competition_id> --strict
```

Validate all competitions:

```bash
python scripts/validate_problem_data.py data/competitions --all --strict
```

`--strict` is accepted for command compatibility. The current validator always checks the canonical direct-child layout.

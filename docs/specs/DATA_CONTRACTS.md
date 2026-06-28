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

Shape written by `runner.py`:

```json
{
  "run_id": "2026_06_28_12_00_00_first_pass",
  "timestamp": "2026-06-28T12:00:00Z",
  "git_hash": "abc1234",
  "competition_id": "school_2026",
  "competition_title": "Школьная олимпиада 2026",
  "problem_id": "task_01",
  "problem_title": "Название задачи",
  "problem_file": "data/competitions/school_2026/task_01.json",
  "problem_text": "Полное условие...",
  "problem": {},
  "results": [
    {
      "model": "provider-model-id",
      "answer": "Решение модели",
      "prompt_tokens": 100,
      "completion_tokens": 500,
      "cost_usd": 0.001,
      "latency_ms": 1200,
      "raw_response": {},
      "error": null,
      "score": null,
      "scored_by": null,
      "scored_at": null,
      "score_comment": null
    }
  ]
}
```

`competition_id`, `competition_title`, `problem_id` and `problem_title` for new logs are derived from the canonical competition and problem files unless explicitly overridden by CLI flags. Old logs remain readable and are not migrated.

`score*` fields remain in new run entries for backward compatibility. The authoritative current evaluations are sidecars.

Do not mutate `results[]` order after a score sidecar exists.

## Scoring sidecar

Canonical path:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Shape:

```json
{
  "competition_id": "school_2026",
  "problem_id": "task_01",
  "run_id": "2026_06_28_12_00_00_first_pass",
  "updated_at": "2026-06-28T12:10:00Z",
  "evaluations": {
    "0": {
      "model": "provider-model-id",
      "evaluator": "reviewer",
      "score": 8,
      "feedback": "Комментарий",
      "updated_at": "2026-06-28T12:10:00Z"
    }
  }
}
```

The evaluation key is the string form of the index in run-log `results[]`.

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

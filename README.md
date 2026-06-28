# Olympiad Scorer

Проект сравнивает ответы разных LLM на олимпиадные задачи.

Что делает:

- берет задачу из JSON или Markdown;
- запускает выбранные модели через общий `runner.py`;
- сохраняет ответы, токены, стоимость, задержку и ошибки в `logs/<competition_id>/<problem_id>/<run_id>.json`;
- дает простой веб-интерфейс для ручной оценки ответов.

Агентная архитектура, контракты адаптеров и формат логов описаны в [AGENTS.md](AGENTS.md).

Работа с сервером, push локальных решений и pull оценок описаны в [SERVER.md](SERVER.md).

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Можно также запускать из текущего Python-окружения, если зависимости уже установлены:

```bash
pip install -r requirements.txt
```

## Конфигурация

В проекте есть жесткое разделение:

- `models/<provider>/secrets/.env` — только ключи, токены и идентификаторы доступа;
- `config/models.env` — единый публичный конфиг для выбора моделей и runtime-настроек;
- `models/<provider>/versions.py` — список доступных версий и default-модель.

Не клади `*_MODEL`, temperature, token limits, scope, SSL-настройки или курс валют в secret-файлы. Secret-файлы должны оставаться credentials-only.

## 1. Как получить ключи

Инструкции по каждому провайдеру лежат рядом с адаптером:

- [GPT / OpenAI](models/gpt/README.md)
- [Claude / Anthropic](models/claude/README.md)
- [DeepSeek](models/deepseek/README.md)
- [GigaChat / Сбер](models/gigachat/README.md)
- [YandexGPT / Alice](models/yandexgpt/README.md)

Кратко:

- OpenAI: создать API key в [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
- Anthropic: создать API key в [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
- DeepSeek: создать API key в [platform.deepseek.com](https://platform.deepseek.com).
- GigaChat: получить `Client ID` и `Client Secret` в Sber Studio.
- YandexGPT/Alice: создать сервисный аккаунт, folder и API-ключ в Yandex Cloud.

## 2. Как положить ключи

Секреты всегда лежат в папке конкретного провайдера:

```text
models/gpt/secrets/.env
models/claude/secrets/.env
models/deepseek/secrets/.env
models/gigachat/secrets/.env
models/yandexgpt/secrets/.env
```

Создать структуру можно так:

```bash
mkdir -p models/gpt/secrets \
  models/claude/secrets \
  models/deepseek/secrets \
  models/gigachat/secrets \
  models/yandexgpt/secrets
```

Папки `models/*/secrets/` gitignored. В них должны быть только ключи, токены и идентификаторы доступа. Не клади туда выбор моделей, temperature, token limits, reasoning settings, server remote или другие runtime-настройки.

### GPT

`models/gpt/secrets/.env`:

```env
OPENAI_API_KEY=sk-...
```

### Claude

`models/claude/secrets/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

### DeepSeek

`models/deepseek/secrets/.env`:

```env
DEEPSEEK_API_KEY=...
```

### GigaChat

`models/gigachat/secrets/.env`:

```env
GIGACHAT_CLIENT_ID=...
GIGACHAT_CLIENT_SECRET=...
```

Старый формат тоже поддерживается:

```env
GIGACHAT_CREDENTIALS=...
```

Если заданы обе формы, `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET` имеют приоритет.

### YandexGPT / Alice

`models/yandexgpt/secrets/.env`:

```env
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
```

Или:

```env
YANDEX_IAM_TOKEN=...
YANDEX_FOLDER_ID=...
```

Для YandexGPT обязателен `YANDEX_FOLDER_ID` и один способ авторизации: `YANDEX_API_KEY` или `YANDEX_IAM_TOKEN`.

## 3. Где выбирать модели

Default-версии лежат в `versions.py` внутри папки провайдера:

```text
models/gpt/versions.py
models/claude/versions.py
models/deepseek/versions.py
models/gigachat/versions.py
models/yandexgpt/versions.py
```

Проект берет:

```python
DEFAULT = VERSIONS[0]
```

Чтобы сменить default надолго, измени порядок `VERSIONS` в нужном `versions.py`.

Чтобы временно выбрать модель для запуска, используй единый конфиг:

```text
config/models.env
```

Пример:

```env
OPENAI_MODEL=gpt-5.4
ANTHROPIC_MODEL=claude-sonnet-4-5
GIGACHAT_MODEL=GigaChat-2-Pro
YANDEX_MODEL=aliceai-llm/latest
DEEPSEEK_MODEL=deepseek-v4-flash
```

В этот же файл кладутся non-secret runtime-настройки:

```env
OPENAI_REASONING_EFFORT=high
OPENAI_MAX_COMPLETION_TOKENS=12000

ANTHROPIC_MAX_TOKENS=12000
# ANTHROPIC_THINKING_BUDGET_TOKENS=8000

GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL=false
GIGACHAT_TEMPERATURE=0.1
GIGACHAT_TOP_P=0.9
GIGACHAT_MAX_TOKENS=8192
GIGACHAT_REPETITION_PENALTY=1.05

YANDEX_TEMPERATURE=0.1
YANDEX_MAX_TOKENS=8000
YANDEX_REASONING_MODE=ENABLED_HIDDEN

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=8192

RUB_PER_USD=90
```

`runner.load_env()` загружает `.env`, затем `models/*/secrets/.env`, затем `config/models.env`. Старые `*_MODEL` из `.env`, shell env и secrets игнорируются, чтобы Jupyter/kernel не подхватывал случайно устаревшие модели.

Если нужно явно разрешить shell env override:

```bash
OPENAI_MODEL=gpt-5.4 python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models gpt \
  --allow-env-model-overrides
```

## Проверить секреты

Команда не печатает значения ключей.

```bash
python scripts/check_secrets.py --models gpt,claude,gigachat,yandexgpt,deepseek
```

Пример вывода:

```text
gpt: ok
gigachat: ok
yandexgpt: missing required: YANDEX_FOLDER_ID
```

## Запуск моделей

Каноническая структура задач:

```text
data/competitions/
  <competition_id>/
    competition.json
    problems/
      <problem_id>.json
```

Пример задачи лежит в `data/competitions/local_examples/problems/example.json`.

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models gpt \
  --run-id test_gpt
```

Несколько моделей:

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models gpt,gigachat,yandexgpt,deepseek \
  --run-id local_test
```

Запуск внутри соревнования:

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models gpt,claude,deepseek \
  --run-id first_pass
```

Если задача лежит в `data/competitions/<competition_id>/problems/`, runner автоматически читает `data/competitions/<competition_id>/competition.json`. Флаги `--competition` и `--competition-title` нужны только для override.

Алиас `alice` использует YandexGPT-адаптер:

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models alice \
  --run-id test_alice
```

Если не указать `--run-id`, он будет создан по timestamp. Результат пишется в:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

Формат автоматического `run_id`:

```text
YYYY_MM_DD_HH_MM_SS_<название>
```

Если передать `--run-id`, значение используется как название после timestamp:

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
  --models claude \
  --run-id smoke_claude
# logs/local_examples/example/2026_06_28_14_30_05_smoke_claude.json
```

Если `--run-id` не передан, название берется из `title` задачи, затем из `id`, затем из имени файла.

JSON-логи игнорируются git.

## Соревнования и задачи

Соревнования и задачи хранятся в `data/competitions/`:

```text
data/competitions/
  local_examples/
    competition.json
    problems/
      example.json
      tug_tug_500.json
```

`competition.json`:

```json
{
  "id": "local_examples",
  "title": "Локальные примеры",
  "description": "Примеры задач для локальной проверки runner и scoring UI."
}
```

Каждая задача в `problems/` использует обычный problem JSON с `id`, `title`, `source`, `text`, `expected_answer`.

Новые логи лежат так:

```text
logs/
  <competition_id>/
    <problem_id>/
      <run_id>.json
```

В JSON-лог добавляются поля:

```json
{
  "competition_id": "school_2026",
  "competition_title": "Школьная олимпиада 2026",
  "problem_id": "task1",
  "problem_title": "Название задачи"
}
```

`competition_id` можно передать через `--competition`. Если он не передан, runner берет `competition.id` из `data/competitions/<competition_id>/competition.json`, затем `competition_id` из JSON задачи, затем `default`.

`problem_id` берется из поля `id` JSON-задачи или из имени файла.

Старая папка `data/problems/` остается для обратной совместимости с простыми одиночными задачами. Старые логи из `logs/*.json` остаются видны в UI как соревнование `legacy`.

## Tools и thinking limits

В этом проекте tools намеренно выключены для честного text-only сравнения решений. Они не настраиваются через `.env` или `config/models.env`.

Адаптеры не передают tools/functions/search/code execution:

- OpenAI GPT: нет `tools`;
- Claude: нет `tools`;
- DeepSeek: нет `tools`;
- GigaChat: нет `tools`, `functions`, `function_call`;
- YandexGPT/Alice: используется basic completion endpoint без tools.

В коде есть дополнительный предохранитель `ensure_text_only_request()` в `models/common.py`: если в будущей правке в payload появятся `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, запрос будет остановлен ошибкой до отправки провайдеру.

Если когда-нибудь нужно включить tools, это уже изменение контракта проекта: нужно обновить `AGENTS.md`, адаптеры в `models/`, scoring/log формат при необходимости и этот README. Для текущего проекта правильная настройка tools — не включать их.

Лимит “сколько модель может думать” у провайдеров устроен по-разному:

- `OPENAI_REASONING_EFFORT` задает effort для reasoning-моделей OpenAI, а `OPENAI_MAX_COMPLETION_TOKENS` ограничивает generated tokens.
- `ANTHROPIC_THINKING_BUDGET_TOKENS` включает Claude extended thinking и задает максимум thinking tokens; `ANTHROPIC_MAX_TOKENS` должен быть больше этого значения.
- `DEEPSEEK_MAX_TOKENS` ограничивает output у DeepSeek; для reasoning-моделей DeepSeek этот лимит включает reasoning content.
- `GIGACHAT_MAX_TOKENS` ограничивает output GigaChat.
- `YANDEX_MAX_TOKENS` ограничивает output YandexGPT, а `YANDEX_REASONING_MODE` включает или отключает reasoning mode, если выбранная модель его поддерживает.

Ни один из этих API не дает надежного hard-minimum “думай не меньше N токенов”. Для этого используется высокий effort, достаточный max-token budget и системный промпт с требованием полной проверки решения.

## Формат задачи

JSON-файл должен содержать поле `text`:

```json
{
  "id": "task1",
  "title": "Название задачи",
  "source": "Олимпиада X",
  "text": "Полный текст условия...",
  "expected_answer": null
}
```

Markdown-файл тоже поддерживается: тогда весь файл считается текстом задачи.

## Веб-скоринг

После запуска моделей можно открыть интерфейс ручной оценки:

```bash
python scoring/app.py
```

Открой:

```text
http://127.0.0.1:8000
```

Интерфейс показывает структуру:

```text
соревнования -> задачи -> прогоны -> ответы моделей
```

Ответы скрыты за раскрытием. Оценка, reviewer и комментарий сохраняются отдельным sidecar-файлом в `data/results/`.

## Результаты скоринга и датасет

Ответы моделей хранятся в JSON-логах:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

Оценки хранятся отдельно:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Формат scoring sidecar:

```json
{
  "competition_id": "school_2026",
  "problem_id": "task1",
  "run_id": "2026_06_28_14_30_00_first_pass",
  "updated_at": "2026-06-28T14:40:00Z",
  "evaluations": {
    "0": {
      "model": "gpt-5.5",
      "evaluator": "reviewer",
      "score": 8,
      "feedback": "Комментарий",
      "updated_at": "2026-06-28T14:40:00Z"
    }
  }
}
```

Ключ `"0"` — индекс ответа в `results[]` исходного run-лога.

Посмотреть оценки можно через сайт:

```bash
python scoring/app.py
```

Или собрать датасет из логов:

```bash
python scripts/export_scoring.py
```

По умолчанию экспортируются только оцененные ответы в:

```text
data/results/scoring_dataset.csv
```

JSONL:

```bash
python scripts/export_scoring.py --format jsonl
```

Включить неоцененные ответы тоже:

```bash
python scripts/export_scoring.py --all
```

Указать свой путь:

```bash
python scripts/export_scoring.py \
  --format csv \
  --output data/results/my_dataset.csv
```

## Синхронизация с сервером

Локально запускай модели и пушь получившиеся логи на сервер:

```bash
python scripts/sync_logs.py push
```

Настрой private remote в gitignored-файле:

```bash
cp config/server.env.example config/server.env
```

В `config/server.env`:

```env
SCORER_REMOTE_LOGS=user@host:/absolute/path/to/shared/logs/
# SCORER_SSH_PORT=22
```

Переопределить remote можно также через env или аргумент:

```bash
SCORER_REMOTE_LOGS=user@host:/absolute/path/to/shared/logs/ \
python scripts/sync_logs.py push

python scripts/sync_logs.py pull --remote user@host:/absolute/path/to/shared/logs/
```

`push` использует `rsync --ignore-existing`, чтобы не перезаписать уже оцененный лог на сервере. После вычитки на сайте забери оценки обратно:

```bash
python scripts/sync_logs.py pull
```

Проверить команду без выполнения:

```bash
python scripts/sync_logs.py push --dry-run
python scripts/sync_logs.py pull --dry-run
```

## Ноутбуки

Для GPT есть тестовый ноутбук:

```bash
jupyter notebook notebooks/test_gpt_runner.ipynb
```

Для полного примера с олимпиадной задачей про монеты Туг-туг:

```bash
jupyter notebook notebooks/run_tug_tug_problem.ipynb
```

Ноутбуки должны использовать тот же контракт: credentials в `models/*/secrets/.env`, выбор моделей и runtime-настройки в `config/models.env`.

## GitHub Actions

Workflow `.github/workflows/run-benchmark.yml` запускается вручную:

```text
Actions -> Run benchmark -> Run workflow
```

Repository Secrets должны содержать только credentials:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
GIGACHAT_CLIENT_ID
GIGACHAT_CLIENT_SECRET
GIGACHAT_CREDENTIALS
YANDEX_API_KEY
YANDEX_IAM_TOKEN
YANDEX_FOLDER_ID
```

Repository Variables или committed config должны использоваться для non-secret настроек:

```text
OPENAI_MODEL
ANTHROPIC_MODEL
DEEPSEEK_MODEL
GIGACHAT_MODEL
YANDEX_MODEL
GIGACHAT_SCOPE
RUB_PER_USD
```

Логи workflow сохраняются как artifact `benchmark-logs`.

## Полезные команды

```bash
python -m compileall runner.py models scripts scoring
python scripts/check_secrets.py --models gpt,claude,gigachat,yandexgpt,deepseek
python runner.py --problem data/competitions/local_examples/problems/example.json --models gpt,gigachat --run-id smoke
python scoring/app.py
python scripts/sync_logs.py push --dry-run
```

# Olympiad Scorer

Проект для сравнения ответов разных LLM на олимпиадные задачи.

Что делает:

- берет задачу из JSON или Markdown;
- запускает выбранные модели через общий `runner.py`;
- сохраняет ответы, токены, стоимость, задержку и ошибки в `logs/<run_id>.json`;
- дает простой веб-интерфейс для ручной оценки ответов.

Агентная архитектура, контракты адаптеров и формат логов описаны в [AGENTS.md](AGENTS.md).

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

## Секреты

Секреты хранятся рядом с кодом конкретной модели и не попадают в git. В этих файлах должны быть только ключи, токены и идентификаторы доступа.

```text
models/gpt/secrets/.env
models/claude/secrets/.env
models/deepseek/secrets/.env
models/gigachat/secrets/.env
models/yandexgpt/secrets/.env
```

Папки `models/*/secrets/` уже добавлены в `.gitignore`.

### GPT

`models/gpt/secrets/.env`:

```env
OPENAI_API_KEY=...
```

### Claude

`models/claude/secrets/.env`:

```env
ANTHROPIC_API_KEY=...
```

### GigaChat

`models/gigachat/secrets/.env`:

```env
GIGACHAT_CREDENTIALS=...
GIGACHAT_CLIENT_ID=...
GIGACHAT_CLIENT_SECRET=...
```

Достаточно либо `GIGACHAT_CREDENTIALS`, либо пары `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET`.

### DeepSeek

`models/deepseek/secrets/.env`:

```env
DEEPSEEK_API_KEY=...
```

### YandexGPT

`models/yandexgpt/secrets/.env`:

```env
YANDEX_API_KEY=...
YANDEX_API_KEY_ID=...
YANDEX_FOLDER_ID=...
```

Для YandexGPT обязательны `YANDEX_FOLDER_ID` и один из ключей: `YANDEX_API_KEY` или `YANDEX_IAM_TOKEN`.

## Выбор моделей

Список доступных версий лежит в `versions.py` внутри папки провайдера:

```text
models/gpt/versions.py
models/claude/versions.py
models/deepseek/versions.py
models/gigachat/versions.py
models/yandexgpt/versions.py
```

По умолчанию берётся `DEFAULT = VERSIONS[0]`. Для разового override можно задать `*_MODEL` в публичном конфиге:

```text
config/models.env
```

Пример:

```env
# OPENAI_MODEL=gpt-5.4
# ANTHROPIC_MODEL=claude-sonnet-4-5
# GIGACHAT_MODEL=GigaChat-2-Pro
# YANDEX_MODEL=yandexgpt
# DEEPSEEK_MODEL=deepseek-v4-flash

GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL=false
YANDEX_TEMPERATURE=0.3
YANDEX_MAX_TOKENS=4000
RUB_PER_USD=90
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.3
```

Как это работает:

- `--models gpt,gigachat` выбирает провайдеры/адаптеры для запуска;
- `models/<provider>/versions.py` выбирает default-версию внутри провайдера;
- `config/models.env` может временно переопределить версию;
- `models/*/secrets/.env` содержит только ключи;
- старые `*_MODEL` из shell env, `.env` и secrets игнорируются, чтобы Jupyter/kernel не подхватывал старые модели.

Если нужно явно разрешить shell env override:

```bash
OPENAI_MODEL=gpt-5.4 python runner.py --problem data/problems/example.json --models gpt --allow-env-model-overrides
```

## Проверить секреты

Команда не печатает значения ключей.

```bash
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt,deepseek
```

Пример вывода:

```text
gpt: ok
gigachat: ok
yandexgpt: missing required: YANDEX_FOLDER_ID
```

## Запуск моделей

Пример задачи лежит в `data/problems/example.json`.

```bash
python runner.py --problem data/problems/example.json --models gpt --run-id test_gpt
```

Несколько моделей:

```bash
python runner.py --problem data/problems/example.json --models gpt,gigachat,yandexgpt,deepseek --run-id local_test
```

Если не указать `--run-id`, он будет создан по timestamp.

Результат пишется в:

```text
logs/<run_id>.json
```

JSON-логи игнорируются git.

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

Интерфейс показывает список прогонов из `logs/`, условие задачи, ответы моделей и форму оценки 0-10.

## Ноутбуки

Для GPT есть тестовый ноутбук:

```bash
jupyter notebook notebooks/test_gpt_runner.ipynb
```

Он проверяет секреты, запускает `runner.py`, читает лог и показывает прямой вызов `GPTModel.solve()`.

Для полного примера с олимпиадной задачей про монеты Туг-туг:

```bash
jupyter notebook notebooks/run_tug_tug_problem.ipynb
```

Ноутбук создает файл задачи, запускает выбранные модели и показывает ответы из лога.

## GitHub Actions

Workflow `.github/workflows/run-benchmark.yml` запускается вручную:

```text
Actions -> Run benchmark -> Run workflow
```

Repository Secrets:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
GIGACHAT_CREDENTIALS
GIGACHAT_CLIENT_ID
GIGACHAT_CLIENT_SECRET
YANDEX_API_KEY
YANDEX_IAM_TOKEN
YANDEX_FOLDER_ID
```

Repository Variables:

```text
GIGACHAT_SCOPE=GIGACHAT_API_PERS
RUB_PER_USD=90
```

Логи workflow сохраняются как artifact `benchmark-logs`.

## Полезные команды

```bash
python -m compileall runner.py models scripts scoring
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt,deepseek
python runner.py --problem data/problems/example.json --models gpt,gigachat --run-id smoke
python scoring/app.py
```

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

### YandexGPT

`models/yandexgpt/secrets/.env`:

```env
YANDEX_API_KEY=...
YANDEX_API_KEY_ID=...
YANDEX_FOLDER_ID=...
```

Для YandexGPT обязательны `YANDEX_FOLDER_ID` и один из ключей: `YANDEX_API_KEY` или `YANDEX_IAM_TOKEN`.

## Выбор моделей

Конкретные версии моделей и не-секретные runtime-настройки лежат в публичном конфиге:

```text
config/models.env
```

Пример:

```env
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-opus-4-5
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL=false
YANDEX_MODEL=yandexgpt-pro
YANDEX_TEMPERATURE=0.3
YANDEX_MAX_TOKENS=4000
RUB_PER_USD=90
```

Как это работает:

- `--models gpt,gigachat` выбирает провайдеры/адаптеры для запуска;
- `config/models.env` выбирает конкретные версии внутри провайдеров;
- `models/*/secrets/.env` содержит только ключи.

## Проверить секреты

Команда не печатает значения ключей.

```bash
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt
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
python runner.py --problem data/problems/example.json --models gpt,gigachat,yandexgpt --run-id local_test
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
GIGACHAT_CREDENTIALS
GIGACHAT_CLIENT_ID
GIGACHAT_CLIENT_SECRET
YANDEX_API_KEY
YANDEX_IAM_TOKEN
YANDEX_FOLDER_ID
```

Repository Variables:

```text
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-opus-4-5
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_SCOPE=GIGACHAT_API_PERS
YANDEX_MODEL=yandexgpt-pro
RUB_PER_USD=90
```

Логи workflow сохраняются как artifact `benchmark-logs`.

## Полезные команды

```bash
python -m compileall runner.py models scripts scoring
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt
python runner.py --problem data/problems/example.json --models gpt,gigachat --run-id smoke
python scoring/app.py
```

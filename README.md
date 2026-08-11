# Olympiad Scorer

`Olympiad Scorer` запускает несколько LLM на олимпиадных задачах, сохраняет ответы и метрики в JSON, а затем позволяет вручную оценивать решения через локальный Flask-сайт.

## Быстрый старт: открыть сайт локально

Нужны Python 3.11+ и терминал. Доступ к серверу не требуется.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scoring/app.py
```

Откройте в браузере:

```text
http://127.0.0.1:8000
```

Сайт показывает соревнования и задачи из `data/competitions/` даже до первого запуска модели. Ответы и прогресс проверки подтягиваются из `logs/` и `data/results/`. Главная страница — витрина соревнований с кликабельными карточками: на них остаются название, дата, описание, количество задач и прогресс проверки.
Scoring-сайт закрыт авторизацией; перед использованием создайте reviewer через
`flask --app scoring.app user create <username>`. Подробности:
[scoring/README.md](scoring/README.md).

Полная инструкция, включая Windows и проверку без браузера: [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

## Быстрый старт: запустить модель

1. Создайте секрет конкретного провайдера, например:

```text
models/gpt/secrets/.env
```

```env
OPENAI_API_KEY=...
```

2. Проверьте наличие секретов без вывода их значений:

```bash
python scripts/check_secrets.py --models gpt
```

3. Запустите задачу:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt \
  --run-id local_smoke
```

Результат появится в:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

Несколько моделей:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt,claude,deepseek,gemini,gigachat,grok,glm,yandexgpt \
  --run-id comparison
```

Все активные модели, которые показаны колонками на сайте:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models all \
  --max-tokens 4096 \
  --run-id comparison_all
```

Если `--models` не указан, runner берет значение из `RUNNER_MODELS` в
`config/models.env`. По умолчанию там стоит `RUNNER_MODELS=all`, то есть
запускаются все активные версии из `models/*/versions.py`.
Флаг `--max-tokens` задаёт единый потолок output/completion-токенов для всех
выбранных адаптеров. Без флага официальный benchmark использует общий бюджет
`256000`. Это общий бюджет запуска, а не обещание, что каждый провайдер
израсходует его целиком. Отдельный CLI-флаг намеренно переопределяет
benchmark-бюджет для экспериментального запуска.

Для OpenAI, Gemini, Grok и GLM `--max-tokens` является суммарным бюджетом.
Если он больше лимита одного запроса, адаптер продолжает незавершённое
reasoning-состояние до первого непустого visible output или исчерпания бюджета:
OpenAI/Grok через `previous_response_id`, Gemini через
`previous_interaction_id`, GLM через preserved `reasoning_content`.
Остальные провайдеры получают значение как один provider-specific ceiling.

Runner пишет `schema_version: 2` run-log со статусом `running` до первого API-вызова и атомарно обновляет JSON после каждой модели. Ошибки API не должны останавливать весь запуск: они записываются в `error` и `error_info` соответствующего результата.
Во время запуска runner печатает live-progress по моделям: `START`, затем
`DONE` или `ERROR` с длительностью, токенами и оценкой стоимости.

## Добавить задачи из PDF или TXT

Используйте готовый промпт из [docs/ADDING_PROBLEMS.md](docs/ADDING_PROBLEMS.md). Его нужно отправить агенту вместе с PDF/TXT-файлом. Агент должен создать:

```text
data/competitions/<competition_id>/competition.json
data/competitions/<competition_id>/<problem_id>.json
```

После импорта:

```bash
python scripts/validate_problem_data.py data/competitions/<competition_id> --strict
```

## Как устроен проект

```text
runner.py                 единый CLI для запуска моделей
models/                   адаптеры провайдеров и общий контракт SolveResult
config/models.env         публичные runtime-настройки без секретов
data/competitions/        условия соревнований и задач
data/results/             отдельные JSON с ручными оценками
logs/                     ответы моделей и метрики прогонов
scoring/                  Flask-интерфейс ручной оценки и каталог logs/results
scripts/                  валидация, экспорт и синхронизация
notebooks/                вспомогательные эксперименты
```

Поток данных:

```text
problem JSON/Markdown
        ↓
     runner.py
        ↓
model adapters → logs/.../run.json (schema_version 2)
                        ↓
                  scoring/app.py
                        ↓
              data/results/.../run.json
                        ↓
             scripts/export_scoring.py
```

## Документация

| Задача | Документ |
| --- | --- |
| локальный запуск сайта и CLI | [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) |
| импорт задач из PDF/TXT | [docs/ADDING_PROBLEMS.md](docs/ADDING_PROBLEMS.md) |
| просмотр решения как построения в GeoGebra | [docs/GEOGEBRA_VIEWER.md](docs/GEOGEBRA_VIEWER.md) |
| серверная синхронизация | [SERVER.md](SERVER.md) |
| production-серверы, каталоги и публичный S3 | [docs/specs/DEPLOYMENT.md](docs/specs/DEPLOYMENT.md) |
| авторизация scoring-сайта | [scoring/README.md](scoring/README.md) |
| инструкции для Codex/Claude/агентов | [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), [CODEX.md](CODEX.md) |
| архитектура и контракты | [docs/specs/INDEX.md](docs/specs/INDEX.md) |
| настройка конкретного провайдера | `models/<provider>/README.md` |

## Конфигурация

Секреты и обычные настройки разделены.

**Секреты**:

```text
models/gpt/secrets/.env
models/claude/secrets/.env
models/deepseek/secrets/.env
models/gemini/secrets/.env
models/gigachat/secrets/.env
models/grok/secrets/.env
models/glm/secrets/.env
models/yandexgpt/secrets/.env
```

**Публичные runtime-настройки**:

```text
config/models.env
```

Там же лежит публичный набор моделей для runner:

```env
RUNNER_MODELS=all
```

`all` разворачивается в те же активные модели, что используются как колонки
scoring UI. Точечный запуск конкретной версии можно задать через
`provider:model_id`, например
`openai:gpt-5.6-sol,google:gemini-3.1-pro-preview,anthropic:claude-opus-5`.

**Версии моделей по умолчанию**:

```text
models/<provider>/versions.py
```

Эти файлы также задают активные колонки в scoring UI. Сейчас в активном
бенчмарке 9 provider groups и 10 active model columns: `claude-fable-5`,
`claude-opus-5`, `deepseek-v4-pro`, `gemini-3.1-pro-preview`,
`GigaChat-3-Ultra`, `grok-4.5`, `glm-5.2`, `gpt-5.6-sol`,
`aliceai-llm`, `kimi-k3`. Исторические логи моделей вне `VERSIONS` не создают
отдельные колонки на сайте.

Canonical provider IDs for new adapters are `google`, `xai` and `zai`.
Accepted aliases: `gemini`/`google`, `grok`/`xai`, `glm`/`zai`/`zhipu`.
Gemini uses the official `google-genai` SDK. Grok uses xAI's hosted
OpenAI-compatible API at `https://api.x.ai/v1`. GLM uses Z.AI's
OpenAI-compatible API at `https://api.z.ai/api/paas/v4/`.

Gemini 3.1 Pro, Grok 4.3 and GLM 5.2 are the active flagships for their
providers. Their former Flash/Build comparison IDs remain explicitly callable
legacy versions but no longer create scoring or public-results columns.

`runner.load_env()` загружает корневой `.env` для обратной совместимости, затем provider secrets, затем `config/models.env`. Не храните выбор модели, temperature или лимиты токенов в secret-файлах.

Матрицы scoring UI используют короткие подписи моделей и tooltip/title/aria-label
с полным model ID. При 10 колонках таблицы нормально прокручиваются
горизонтально; столбец задач остаётся sticky, а страница отвечает за
вертикальный scroll.

## Формат новой задачи

```json
{
  "schema_version": 1,
  "id": "task_01",
  "number": 1,
  "title": "Название задачи",
  "statement": "Полное условие с формулами в LaTeX.",
  "answer": null,
  "solution": null,
  "tags": [],
  "metadata": {}
}
```

Задача лежит непосредственно в папке соревнования, а имя файла совпадает с `id`: `data/competitions/<competition_id>/task_01.json`.

## Посмотреть решение как построение

Геометрическое решение можно смотреть чертежом, а не текстом: сцена из шагов
проигрывается в GeoGebra, шаг за шагом.

```bash
python scripts/geogebra_view.py scripts/geogebra_viewer/examples/euler_line.json
```

Пока сервер работает, файл сцены можно править — страница обновится сама.
Формат сцены и грабли: [docs/GEOGEBRA_VIEWER.md](docs/GEOGEBRA_VIEWER.md).

## Ручная оценка и экспорт

Оценки сохраняются отдельно от ответов моделей и для новых записей связываются с ответом по `result_id`:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

У одного ответа может быть по одной изменяемой проверке от каждого проверяющего.
Сайт хранит их как пул текущих проверок, а имя проверяющего берётся из активной
login-сессии (`current_user.username`). Повторное сохранение обновляет прежнюю
проверку. Общий итог организаторов хранится отдельно; две совпавшие крайние
оценки финализируются автоматически. Главная
страница группирует соревнования по годам, а внутри года показывает их от более
ранних к более поздним; соревнования без определяемого года скрыты на главной,
но доступны по прямому URL. Дата на карточке выводится по-русски без года.
Прогресс серый без запусков, красный для непроверенных запусков и зелёный для
проверенной части. Страница задачи показывает проверку в одну колонку: условие,
закрытый эталон, ответ модели, затем форма, текущая проверка, метрики и сырой JSON. На
страницах соревнования и задачи есть CSV-экспорт:
все проверки, проверки текущего пользователя и обратный импорт CSV.

Экспорт только оценённых ответов:

```bash
python scripts/export_scoring.py
```

Экспорт всех ответов:

```bash
python scripts/export_scoring.py --all
```

Экспорт сохраняет старые столбцы и добавляет `schema_version`, `result_id`, provider/model IDs, status, usage/timing/cost, max score, score category и prompt/problem hashes.

## Важные ограничения

- Модели работают в режиме text-only: без tools, поиска, function calling и исполнения кода. Provider-side Google Search, X search, code execution, managed agents and remote MCP are not enabled.
- Локальный Flask-сервер запускается с debug-режимом и предназначен только для разработки на `127.0.0.1`; серверный сайт должен работать за HTTPS reverse proxy.
- Реальные API-ключи, `config/server.env`, кэши Python и системные файлы не должны попадать в Git или архивы.
- Auth DB (`instance/scorer-auth.sqlite3` или `SCORER_AUTH_DB`) содержит password hashes и не должна попадать в Git.
- Изменение форматов problem/log/score требует одновременного обновления runner, scoring, export и спецификаций.

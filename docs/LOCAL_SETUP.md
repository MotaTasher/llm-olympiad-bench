# Локальный запуск

Эта инструкция позволяет запустить scoring-сайт и CLI без доступа к удалённому серверу.

## Требования

- Python 3.11 или новее;
- `pip`;
- интернет нужен только для установки зависимостей и вызова внешних моделей;
- для просмотра уже существующих логов API-ключи не нужны.

Проверка:

```bash
python --version
python -m pip --version
```

Команды runner и скриптов выполняются из корня проекта — папки, где лежат
`runner.py` и `requirements.txt`. Scoring-сайт сам находит `logs/` и
`data/results/` относительно расположения `scoring/app.py`.
На сервере эти пути можно переопределить переменными `SCORER_LOGS_DIR`,
`SCORER_RESULTS_DIR` и `SCORER_COMPETITIONS_DIR`.
Scoring-сайт закрыт авторизацией. Локальная база пользователей по умолчанию:
`instance/scorer-auth.sqlite3`; путь можно переопределить через
`SCORER_AUTH_DB`.

## 1. Создать окружение

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Если PowerShell запрещает активацию скрипта, можно не активировать окружение и запускать команды через `.venv\Scripts\python.exe`.

## 2. Создать пользователя scoring-сайта

Публичной регистрации нет. Создайте reviewer-аккаунт из терминала:

```bash
flask --app scoring.app user create reviewer-01
```

Команда сгенерирует длинный пароль, сохранит только password hash и покажет
plaintext-пароль один раз. Сразу сохраните его в менеджере паролей:

```text
User created: reviewer-01
Password: <generated password>
Save this password now. It will not be shown again.
```

Если пароль утрачен:

```bash
flask --app scoring.app user reset-password reviewer-01
```

Отключить или включить пользователя:

```bash
flask --app scoring.app user disable reviewer-01
flask --app scoring.app user enable reviewer-01
flask --app scoring.app user list
```

Для локальной разработки `SCORER_SECRET_KEY` необязателен: приложение создаст
временный ключ на процесс и предупредит об этом. На сервере ключ нужно задать
явно:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. Запустить сайт

```bash
python scoring/app.py
```

Открыть:

```text
http://127.0.0.1:8000
```

Остановка: `Ctrl+C` в терминале.

Сайт читает canonical задачи и соревнования:

```text
data/competitions/
logs/**/*.json
```

и сохраняет оценки в:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Задача появляется в интерфейсе даже без run-лога. Логи и sidecar-оценки объединяются для матрицы моделей и страницы проверки.
На главной странице соревнования сгруппированы по годам, извлеченным из `date`,
ID или названия; внутри года соревнования идут от более ранних к более поздним.
Страница проверки задачи идет в одну колонку: условие,
закрытый эталон, ответ модели, затем форма оценки, история проверок, метрики и
сырой JSON. Новая оценка получает `evaluator`, равный username текущего
вошедшего пользователя; браузер не отправляет имя проверяющего.

На главной и на странице соревнования есть общий компактный калькулятор
стоимости: два синхронных ползунка/числовых поля для reasoning budget и лимита
ответа, плюс галочка учёта уже решённых задач. Значения сохраняются в браузере
и сразу пересчитывают стоимость без кнопки и без HTTP-запроса. Расчёт
использует локальные price tables, грубую оценку токенов и курс USD/RUB из ЦБ.
Для моделей с настроенной reasoning-стоимостью токены reasoning budget
считаются по output-ставке провайдера, а для total-priced RUB моделей — по
общей ставке за токены. Модели без reasoning-тарифа не получают эту надбавку.
API-вызовы не выполняются, фоновые задания не создаются, run-log не
записываются. По умолчанию расчёт использует все активные модели из
`models/*/versions.py`, как при `runner.py --models all`.

Рядом с калькулятором интерфейс показывает фактически потраченные деньги из уже
существующих логов: сумму последних попыток, которые попадают в текущую матрицу
проверки, и сумму всех результатов в логах соревнования. На главной странице
эти три числа также суммируются по всем соревнованиям в верхней панели. На
карточке соревнования эти числа остаются видимыми сразу; подробная таблица на
странице соревнования раскрывается по клику. В ней стоимость по моделям
показана с уже потраченным по логам в отдельных USD/RUB колонках, ценой за 1M
input/output/reasoning токенов, оценкой USD/RUB и итоговой строкой суммы.

## 4. Если сайт пустой

Создайте тестовый run. Для реального адаптера нужен его API-ключ:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt \
  --run-id local_smoke
```

Даже если ключ отсутствует или API вернул ошибку, runner должен создать schema v2 лог с заполненными `error` и `error_info`; такой run также виден в интерфейсе. Лог создаётся со статусом `running` до первого API-вызова и обновляется после каждой модели.
В терминале runner показывает live-progress по моделям: строку `START` перед
ожиданием API и строку `DONE` или `ERROR` после ответа.

После запуска обновите страницу.

Если `--models` не указан, runner берет `RUNNER_MODELS` из
`config/models.env`. В committed-конфиге стоит `RUNNER_MODELS=all`, поэтому
запуск без `--models` обращается ко всем активным моделям сайта. Для дешевого
smoke-теста явно указывайте одну модель, как в примере выше.

## 5. Настроить ключи моделей

Создайте только нужный secret-файл.

### OpenAI

```text
models/gpt/secrets/.env
```

```env
OPENAI_API_KEY=...
```

### Anthropic

```text
models/claude/secrets/.env
```

```env
ANTHROPIC_API_KEY=...
```

### DeepSeek

```text
models/deepseek/secrets/.env
```

```env
DEEPSEEK_API_KEY=...
```

### GigaChat

```text
models/gigachat/secrets/.env
```

```env
GIGACHAT_CLIENT_ID=...
GIGACHAT_CLIENT_SECRET=...
```

### YandexGPT

```text
models/yandexgpt/secrets/.env
```

```env
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
```

Проверка без печати значений:

```bash
python scripts/check_secrets.py --models gpt,claude,deepseek,gigachat,yandexgpt
```

## 6. Выбрать модели и лимиты

Версии по умолчанию находятся в:

```text
models/<provider>/versions.py
```

`VERSIONS` в этих файлах задает активный набор для runner defaults и колонок
scoring UI. По умолчанию там оставлены paid и budget/free-tier модели каждого
провайдера.

Обычные runtime-настройки находятся в:

```text
config/models.env
```

Там же задается набор моделей runner по умолчанию:

```env
RUNNER_MODELS=all
```

`all` разворачивается в активные `VERSIONS` из `models/*/versions.py`, то есть
в те же пять моделей, которые показаны колонками scoring UI. Исторические логи
с удаленными слабым моделями не добавляют отдельные колонки на сайте. Можно
запускать конкретную версию через `provider:model_id`, например:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models openai:gpt-5.5,anthropic:claude-opus-4-8 \
  --max-tokens 4096 \
  --run-id strong_pair
```

Единый лимит output/completion-токенов можно задать CLI-флагом
`--max-tokens` или переменной `RUNNER_MAX_TOKENS` в `config/models.env`.
В committed-конфиге стоит `RUNNER_MAX_TOKENS=8000`. CLI-флаг имеет приоритет
над `RUNNER_MAX_TOKENS`, а они вместе имеют приоритет над provider-specific
переменными (`ANTHROPIC_MAX_TOKENS`,
`OPENAI_MAX_COMPLETION_TOKENS`, `DEEPSEEK_MAX_TOKENS`, `GIGACHAT_MAX_TOKENS`,
`YANDEX_MAX_TOKENS`).

Не помещайте runtime-настройки в `models/*/secrets/.env`.

## 7. Проверить сайт без браузера

```bash
python - <<'PY'
from pathlib import Path
import re
import tempfile
from scoring.app import app
from scoring.auth import create_user

tmp = tempfile.TemporaryDirectory()
app.config.update(AUTH_DB=Path(tmp.name) / "auth.sqlite3", TESTING=True, WTF_CSRF_TIME_LIMIT=None)
_, password = create_user(app.config["AUTH_DB"], "smoke-user")
client = app.test_client()
login = client.get("/login").get_data(as_text=True)
csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login).group(1)
assert client.get("/").status_code == 302
assert client.post("/login", data={"username": "smoke-user", "password": password, "csrf_token": csrf}).status_code == 302
response = client.get("/")
assert response.status_code == 200, response.status_code
print("scoring UI smoke test: ok")
PY
```

## 8. Проверить проект

```bash
python -m compileall -q runner.py models scripts scoring
python scripts/validate_problem_data.py data/competitions --all --strict
python scripts/export_scoring.py --all --output /tmp/olympiad-scorer-check.csv
```

На Windows вместо `/tmp/olympiad-scorer-check.csv` укажите, например, `data/results/local-check.csv`, а затем удалите файл.

## Типичные проблемы

### `ModuleNotFoundError: flask`

Окружение не активировано или зависимости не установлены:

```bash
pip install -r requirements.txt
```

### Сайт открывается, но соревнований нет

В `logs/` нет корректных JSON run-логов. Запустите модель или перенесите логи с другой машины.

### Порт 8000 занят

Завершите старый процесс. macOS/Linux:

```bash
lsof -i :8000
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8000
```

### Оценка не сохраняется

Проверьте, что вы вошли в scoring-сайт активным пользователем, CSRF token не
устарел, есть права на запись в `data/results/`, а исходный run-log валиден.

Расширенная карта диагностики: [specs/TROUBLESHOOTING.md](specs/TROUBLESHOOTING.md).

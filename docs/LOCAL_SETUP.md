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

Все команды ниже выполняются из корня проекта — папки, где лежат `runner.py` и `requirements.txt`.

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

## 2. Запустить сайт

```bash
python scoring/app.py
```

Открыть:

```text
http://127.0.0.1:8000
```

Остановка: `Ctrl+C` в терминале.

Сайт читает:

```text
logs/**/*.json
```

и сохраняет оценки в:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Сайт не читает условия напрямую из `data/competitions/`: задача появляется в интерфейсе после появления run-лога.

## 3. Если сайт пустой

Создайте тестовый run. Для реального адаптера нужен его API-ключ:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt \
  --run-id local_smoke
```

Даже если ключ отсутствует или API вернул ошибку, runner должен создать лог с заполненным полем `error`; такой run также виден в интерфейсе.

После запуска обновите страницу.

## 4. Настроить ключи моделей

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

## 5. Выбрать модели и лимиты

Версии по умолчанию находятся в:

```text
models/<provider>/versions.py
```

Обычные runtime-настройки находятся в:

```text
config/models.env
```

Не помещайте runtime-настройки в `models/*/secrets/.env`.

## 6. Проверить сайт без браузера

```bash
python - <<'PY'
from scoring.app import app

client = app.test_client()
response = client.get("/")
assert response.status_code == 200, response.status_code
print("scoring UI smoke test: ok")
PY
```

## 7. Проверить проект

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

### Запуск из другой папки не видит логи

Текущая реализация использует относительные пути `logs/` и `data/results/`. Перейдите в корень проекта перед запуском.

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

Проверьте права на запись в `data/results/` и валидность исходного run-лога.

Расширенная карта диагностики: [specs/TROUBLESHOOTING.md](specs/TROUBLESHOOTING.md).

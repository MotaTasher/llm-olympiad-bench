# Server Workflow

Инструкция для обмена логами со scoring-сервером. Доступ к серверу не нужен для локального запуска сайта; см. [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

## Кто может пушить

Адрес сервера сам по себе не дает доступ. Пушить может только тот, у кого есть SSH-доступ к серверу и права писать в remote-папку логов.

В публичном репозитории не должно быть твоего IP, домена, username или server path. Эти значения хранятся локально в gitignored-файле:

```text
config/server.env
```

## Локальная настройка сервера

Создай файл:

```bash
mkdir -p config
cp config/server.env.example config/server.env
```

Заполни:

```env
SCORER_REMOTE_LOGS=user@host:/absolute/path/to/shared/logs/
SCORER_REMOTE_RESULTS=user@host:/absolute/path/to/data/results/
# SCORER_SSH_PORT=22
```

Пример формата:

```env
SCORER_REMOTE_LOGS=deploy@example.com:/srv/my-scorer/shared/logs/
SCORER_REMOTE_RESULTS=deploy@example.com:/srv/my-scorer/data/results/
SCORER_SSH_PORT=22
```

`config/server.env` добавлен в `.gitignore`.

## Схема

Локально запускаются модели и создаются JSON-логи:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

На сервере scoring-сайт читает ответы из remote-папки, указанной в `SCORER_REMOTE_LOGS`, и пишет оценки в `SCORER_REMOTE_RESULTS`.

## Push: отправить решения на сервер

После локального запуска моделей:

```bash
python scripts/sync_logs.py push
```

Команда отправляет содержимое локальной папки `logs/` на сервер. Если задан `SCORER_REMOTE_RESULTS`, sidecar-файлы из `data/results/` тоже синхронизируются с `--ignore-existing`.

Внутри используется:

```bash
rsync -avz --ignore-existing logs/ "$SCORER_REMOTE_LOGS"
```

`--ignore-existing` нужен специально: если на сервере уже поставили оценки, локальный старый лог не перетрет серверную версию.

Проверить команду без выполнения:

```bash
python scripts/sync_logs.py push --dry-run
```

## Server-side retry for Math Cup 2026 final

На сервере можно пересчитать только пары `задача × модель`, где нет успешного
непустого ответа. Скрипт по умолчанию делает dry-run и показывает список пар и
оценку максимальной стоимости:

```bash
cd /opt/olympiad-scorer/app
.venv/bin/python scripts/run_missing_math_cup_2026_final.py
```

Запуск API-вызовов требует явного `--yes`. Чтобы процесс жил после разрыва SSH:

```bash
cd /opt/olympiad-scorer/app
mkdir -p run-output/missing-2026-final-320k
nohup .venv/bin/python scripts/run_missing_math_cup_2026_final.py \
  --max-tokens 320000 \
  --workers 23 \
  --yes \
  > run-output/missing-2026-final-320k/launcher.log 2>&1 &
```

Каждая пара запускается отдельным процессом `runner.py` и пишет отдельный
schema-v2 run-log прямо в `/opt/olympiad-scorer/shared/logs`. Логи stdout/stderr
лежат в `run-output/missing-2026-final-320k/`.

## Pull: забрать оценки с сервера

После вычитки на сайте:

```bash
python scripts/sync_logs.py pull
```

Команда скачивает серверные JSON обратно в локальные папки `logs/` и `data/results/`.

Оценки подтягиваются из sidecar-файлов:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Проверить команду без выполнения:

```bash
python scripts/sync_logs.py pull --dry-run
```

## Где лежит scoring

Оценки не лежат в базе. Они записываются отдельными JSON sidecar-файлами:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Внутри:

```text
evaluations.<result_index>.score
evaluations.<result_index>.evaluator
evaluations.<result_index>.feedback
evaluations.<result_index>.updated_at
```

Ответы моделей остаются в `logs/<competition_id>/<problem_id>/<run_id>.json`. Экспорт датасета объединяет `logs/` и `data/results/`.

## Собрать датасет

Сначала подтяни оценки с сервера:

```bash
python scripts/sync_logs.py pull
```

Потом экспортируй CSV:

```bash
python scripts/export_scoring.py
```

Файл появится здесь:

```text
data/results/scoring_dataset.csv
```

JSONL:

```bash
python scripts/export_scoring.py --format jsonl
```

По умолчанию экспортируются только оцененные ответы. Чтобы включить все ответы:

```bash
python scripts/export_scoring.py --all
```

## Полный рабочий цикл

1. Запустить модели локально:

```bash
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt,claude,deepseek \
  --run-id first_pass
```

2. Отправить решения на сервер:

```bash
python scripts/sync_logs.py push
```

3. Открыть scoring-сайт и поставить оценки.

4. Забрать оценки обратно:

```bash
python scripts/sync_logs.py pull
```

## Переопределить сервер

Разово через аргумент:

```bash
python scripts/sync_logs.py push \
  --remote user@host:/absolute/path/to/shared/logs/

python scripts/sync_logs.py pull \
  --remote user@host:/absolute/path/to/shared/logs/
```

Через env:

```bash
export SCORER_REMOTE_LOGS=user@host:/absolute/path/to/shared/logs/
python scripts/sync_logs.py push
python scripts/sync_logs.py pull
```

Если SSH не на стандартном порту:

```bash
python scripts/sync_logs.py push --ssh-port 2222
python scripts/sync_logs.py pull --ssh-port 2222
```

Или через env/config:

```env
SCORER_SSH_PORT=2222
```

## Проверки

Посмотреть, что будет отправлено:

```bash
find logs -maxdepth 4 -type f | sort
```

Проверить, что remote настроен:

```bash
python scripts/sync_logs.py push --dry-run
python scripts/sync_logs.py pull --dry-run
```

Проверить SSH:

```bash
ssh user@host 'hostname && ls -la /absolute/path/to/shared/logs'
```

## Важно

- Модельные API-ключи не нужны серверу, если модели запускаются локально.
- На сервер отправляются только JSON-логи с ответами и scoring-полями.
- Не коммить `config/server.env`.
- Не редактируй один и тот же лог одновременно локально и на сервере.
- Если сомневаешься, сначала сделай `pull`, потом запускай новые модели и делай `push`.

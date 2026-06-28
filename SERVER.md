# Server Workflow

Инструкция для обмена логами со scoring-сервером.

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
# SCORER_SSH_PORT=22
```

Пример формата:

```env
SCORER_REMOTE_LOGS=deploy@example.com:/srv/my-scorer/shared/logs/
SCORER_SSH_PORT=22
```

`config/server.env` добавлен в `.gitignore`.

## Схема

Локально запускаются модели и создаются JSON-логи:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

На сервере scoring-сайт читает те же логи из remote-папки, указанной в `SCORER_REMOTE_LOGS`.

## Push: отправить решения на сервер

После локального запуска моделей:

```bash
python scripts/sync_logs.py push
```

Команда отправляет содержимое локальной папки `logs/` на сервер.

Внутри используется:

```bash
rsync -avz --ignore-existing logs/ "$SCORER_REMOTE_LOGS"
```

`--ignore-existing` нужен специально: если на сервере уже поставили оценки, локальный старый лог не перетрет серверную версию.

Проверить команду без выполнения:

```bash
python scripts/sync_logs.py push --dry-run
```

## Pull: забрать оценки с сервера

После вычитки на сайте:

```bash
python scripts/sync_logs.py pull
```

Команда скачивает серверные JSON обратно в локальную папку `logs/`.

Вместе с логами подтягиваются scoring-поля:

```text
score
scored_by
scored_at
score_comment
```

Проверить команду без выполнения:

```bash
python scripts/sync_logs.py pull --dry-run
```

## Полный рабочий цикл

1. Запустить модели локально:

```bash
python runner.py \
  --problem data/competitions/local_examples/problems/example.json \
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

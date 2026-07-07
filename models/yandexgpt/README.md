# YandexGPT / Alice

Алиас `alice` в `runner.py` использует адаптер `AliceModel`, который ходит в YandexGPT API. Публичного API голосовой Alice для произвольного скоринга задач здесь не используется.

Адаптер работает через basic completion endpoint в text-only режиме: без tools, function calling, поиска, кода и внешних цепочек.
Единый лимит output-токенов задаётся через `runner.py --max-tokens`; `YANDEX_MAX_TOKENS` остаётся fallback-настройкой.

## 1. Как получить ключ

1. Открой [console.yandex.cloud](https://console.yandex.cloud) и войди через Яндекс ID.
2. Создай платежный аккаунт, если его еще нет.
3. Создай или выбери folder и скопируй его `Folder ID`.
4. Создай сервисный аккаунт.
5. Выдай сервисному аккаунту роль `ai.languageModels.user`.
6. Создай API-ключ сервисного аккаунта и скопируй его.

Для короткого ручного теста можно использовать IAM-токен:

```bash
yc iam create-token
```

IAM-токен живет ограниченное время, поэтому для обычных запусков удобнее API-ключ.

## 2. Как положить ключ

Создай файл:

```text
models/yandexgpt/secrets/.env
```

Если папки еще нет:

```bash
mkdir -p models/yandexgpt/secrets
```

Вариант с API-ключом:

```env
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
```

Вариант с IAM-токеном:

```env
YANDEX_IAM_TOKEN=...
YANDEX_FOLDER_ID=...
```

`YANDEX_FOLDER_ID` обязателен. Для авторизации нужен один из вариантов: `YANDEX_API_KEY` или `YANDEX_IAM_TOKEN`.

Файл `models/yandexgpt/secrets/.env` должен содержать только credentials и идентификаторы доступа: ключ, IAM-токен, folder id. Не клади туда `YANDEX_MODEL`, temperature, token limits, reasoning mode или курс валют.

## 3. Где выбирать модель

Default-модель выбирается в:

```text
models/yandexgpt/versions.py
```

Проект берет:

```python
DEFAULT = VERSIONS[0]
```

Если нужно временно выбрать другую модель для запуска, задай override в едином публичном конфиге:

```text
config/models.env
```

Пример:

```env
YANDEX_MODEL=yandexgpt-5.1
```

Runtime-настройки YandexGPT тоже должны жить в `config/models.env`:

```env
YANDEX_TEMPERATURE=0.1
YANDEX_MAX_TOKENS=8000
YANDEX_REASONING_MODE=ENABLED_HIDDEN
YANDEX_TIMEOUT=120
RUB_PER_USD=90
```

`YANDEX_REASONING_MODE` поддерживает значения `ENABLED_HIDDEN` и `DISABLED`. Если выбранная модель не поддерживает hidden reasoning, адаптер повторит запрос без `reasoningOptions` и запишет это в `raw_response`. Когда API возвращает `completionTokensDetails.reasoningTokens`, адаптер сохраняет это число в `usage.reasoning_tokens`; `cost.reasoning` является поддолей total-priced стоимости, а не дополнительной надбавкой.

`runner.load_env()` специально игнорирует старые `YANDEX_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

## Проверка

```bash
python scripts/check_secrets.py --models yandexgpt
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models yandexgpt \
  --run-id smoke_yandexgpt
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models alice \
  --run-id smoke_alice
```

## Tools и runtime

Адаптер использует Yandex Foundation Models completion endpoint. Инструменты на этом уровне API не передаются. Это важно для честного сравнения олимпиадных решений: модель должна отвечать только текстом, без внешних инструментов.

Tools не включаются через конфиг. Если в payload случайно появится `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, общий guard в `models/common.py` остановит запрос.

Настраивать можно только text-only runtime:

```env
YANDEX_TEMPERATURE=0.1
YANDEX_MAX_TOKENS=8000
YANDEX_REASONING_MODE=ENABLED_HIDDEN
YANDEX_TIMEOUT=120
RUB_PER_USD=90
```

Если API вернул usage/status, но не вернул видимый текстовый ответ,
адаптер записывает `SolveResult.error`, а не успешное пустое решение.

## Полезные ссылки

- [Yandex Cloud Console](https://console.yandex.cloud)
- [YandexGPT quickstart](https://yandex.cloud/en/docs/foundation-models/quickstart/yandexgpt)
- [API key management](https://yandex.cloud/en/docs/iam/operations/api-key/create)
- [Foundation Models pricing](https://yandex.cloud/ru/prices#foundation-models)

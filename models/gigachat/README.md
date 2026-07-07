# GigaChat (Сбер)

Этот адаптер запускает GigaChat через общий `runner.py` в text-only режиме: без `tools`, `functions`, `function_call` и внешних цепочек.
Единый лимит output-токенов задаётся через `runner.py --max-tokens`; `GIGACHAT_MAX_TOKENS` остаётся fallback-настройкой.

## 1. Как получить ключи

1. Открой страницу GigaChat API в Sber Studio: [developers.sber.ru/studio/workspaces/my-space/get/gigachat-api](https://developers.sber.ru/studio/workspaces/my-space/get/gigachat-api).
2. Войди через СберID.
3. Подключи GigaChat API и создай проект, если он еще не создан.
4. В проекте открой настройки авторизационных данных.
5. Получи и скопируй `Client ID` и `Client Secret`.

GigaChat может требовать сертификаты НУЦ Минцифры для HTTPS. Для локальной разработки в проекте есть настройка `GIGACHAT_VERIFY_SSL=false`, но это runtime-настройка и она должна лежать в `config/models.env`, а не в secrets.

## 2. Как положить ключи

Создай файл:

```text
models/gigachat/secrets/.env
```

Если папки еще нет:

```bash
mkdir -p models/gigachat/secrets
```

Рекомендуемый формат:

```env
GIGACHAT_CLIENT_ID=...
GIGACHAT_CLIENT_SECRET=...
```

Адаптер сам соберет строку `client_id:client_secret`, закодирует ее в base64 и передаст в OAuth.

Для обратной совместимости поддерживается старый единый credential:

```env
GIGACHAT_CREDENTIALS=...
```

Если заданы обе формы, `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET` имеют приоритет.

Файл `models/gigachat/secrets/.env` должен содержать только credentials. Не клади туда `GIGACHAT_MODEL`, `GIGACHAT_SCOPE`, `GIGACHAT_VERIFY_SSL`, temperature, token limits или другие runtime-настройки.

## 3. Где выбирать модель

Default-модель выбирается в:

```text
models/gigachat/versions.py
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
GIGACHAT_MODEL=GigaChat-2-Max
```

Runtime-настройки GigaChat тоже должны жить в `config/models.env`:

```env
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL=false
GIGACHAT_TEMPERATURE=0.1
GIGACHAT_TOP_P=0.9
GIGACHAT_MAX_TOKENS=8192
GIGACHAT_REPETITION_PENALTY=1.05
```

`GIGACHAT_SCOPE` обычно:

- `GIGACHAT_API_PERS` для физлиц;
- `GIGACHAT_API_CORP` для юрлиц/ИП.

`runner.load_env()` специально игнорирует старые `GIGACHAT_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

## Проверка

```bash
python scripts/check_secrets.py --models gigachat
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gigachat \
  --run-id smoke_gigachat
```

## Tools и runtime

Адаптер не передает `tools`, `functions` или `function_call`. Это важно для честного сравнения олимпиадных решений: модель должна отвечать только текстом, без внешних инструментов.

Tools не включаются через конфиг. Если в payload случайно появится `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, общий guard в `models/common.py` остановит запрос.

Настраивать можно только text-only runtime:

```env
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL=false
GIGACHAT_TEMPERATURE=0.1
GIGACHAT_TOP_P=0.9
GIGACHAT_MAX_TOKENS=8192
GIGACHAT_REPETITION_PENALTY=1.05
```

Если API вернул usage и finish reason, но не вернул видимый текстовый ответ,
адаптер записывает `SolveResult.error`, а не успешное пустое решение.

## Полезные ссылки

- [GigaChat API quickstart](https://developers.sber.ru/docs/ru/gigachat/individuals-quickstart)
- [GigaChat API reference](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/gigachat-api)
- [Сертификаты для GigaChat](https://developers.sber.ru/docs/ru/gigachat/certificates)
- [Тарифы GigaChat](https://developers.sber.ru/docs/ru/gigachat/api/tariffs)

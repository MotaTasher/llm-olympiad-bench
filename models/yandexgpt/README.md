# YandexGPT (Яндекс)

> **Про Alice:** голосовой ассистент Alice недоступен через публичный API для кастомных запросов.
> Для скоринга задач используем **YandexGPT API** — это основная текстовая модель Яндекса,
> которая лежит в основе Alice.

## Получение доступа

### Шаг 1 — Аккаунт Yandex Cloud

1. Зайди на [console.yandex.cloud](https://console.yandex.cloud)
2. Войди через Яндекс ID или зарегистрируйся
3. Создай **платёжный аккаунт** (Billing → Создать аккаунт) — нужна карта, есть бесплатный грант на старт
4. Создай **папку** (folder): главная страница консоли → Создать папку → запомни `Folder ID`

### Шаг 2 — API-ключ сервисного аккаунта (рекомендуется для автоматизации)

1. Консоль → **IAM** → **Сервисные аккаунты** → **Создать**
2. Дай имя, добавь роль `ai.languageModels.user`
3. Открой созданный аккаунт → вкладка **API-ключи** → **Создать API-ключ**
4. Скопируй ключ (начинается с `AQVN...`)

### Альтернатива: IAM-токен (для быстрого теста)

```bash
yc iam create-token
# Токен живёт 12 часов, не подходит для постоянного использования
```

**В `.env`:**
```
YANDEX_API_KEY=AQVN...
YANDEX_FOLDER_ID=b1g...
YANDEX_MODEL=yandexgpt-pro
```

## Актуальные модели

| Модель (`modelUri`) | Описание | Цена |
|---------------------|----------|------|
| `yandexgpt-pro` | Продвинутая | 0.80₽ / 1K токенов |
| `yandexgpt-lite` | Быстрая и дешёвая | 0.20₽ / 1K токенов |
| `yandexgpt-pro-32k` | Большой контекст | 1.20₽ / 1K токенов |

Цены актуальны на 2026-06 — сверяй на [yandex.cloud/ru/prices](https://yandex.cloud/ru/prices#foundation-models)

`modelUri` передаётся как `gpt://<folder_id>/<model_name>`, например:
```
gpt://b1g.../yandexgpt-pro
```

## Как работает API (text-only, без инструментов)

Endpoint: `POST https://llm.api.cloud.yandex.net/foundationModels/v1/completion`

YandexGPT базовый completion API **изначально без инструментов** — поиск, код, функции не предусмотрены на этом уровне.

```python
import requests, os, time

YANDEX_API_KEY = os.environ["YANDEX_API_KEY"]
YANDEX_FOLDER_ID = os.environ["YANDEX_FOLDER_ID"]
YANDEX_MODEL = os.environ.get("YANDEX_MODEL", "yandexgpt-pro")

headers = {
    "Authorization": f"Api-Key {YANDEX_API_KEY}",
    "Content-Type": "application/json",
    "x-folder-id": YANDEX_FOLDER_ID,
}

payload = {
    "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{YANDEX_MODEL}",
    "completionOptions": {
        "stream": False,
        "temperature": 0.3,
        "maxTokens": 4000,
    },
    "messages": [
        {"role": "system", "text": "Ты решаешь олимпиадные задачи. Думай пошагово и дай финальный ответ."},
        {"role": "user", "text": problem_text},
    ],
}

start = time.time()
response = requests.post(
    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
    headers=headers,
    json=payload,
    timeout=120,
)
response.raise_for_status()
latency_ms = int((time.time() - start) * 1000)

data = response.json()["result"]
answer = data["alternatives"][0]["message"]["text"]
prompt_tokens = int(data["usage"]["inputTextTokens"])
completion_tokens = int(data["usage"]["completionTokens"])
```

## Подсчёт стоимости

YandexGPT считает в **рублях** за 1000 токенов. В `SolveResult.cost_usd` конвертируй по курсу или храни `cost_rub`:

```python
PRICE_PER_1K_TOKENS_RUB = 0.80  # yandexgpt-pro, вход+выход одинаково
total_tokens = prompt_tokens + completion_tokens
cost_rub = (total_tokens / 1000) * PRICE_PER_1K_TOKENS_RUB
```

## Будущее: включить инструменты

YandexGPT через базовый API не поддерживает function calling. Для инструментов нужно использовать **Yandex AI Studio** (UI) или **YandexGPT через LangChain/GigaChain** с кастомными цепочками.

## Полезные ссылки

- [Быстрый старт YandexGPT](https://yandex.cloud/en/docs/foundation-models/quickstart/yandexgpt)
- [Справка API completion](https://yandex.cloud/en/docs/foundation-models/text-generation/api-ref/TextGeneration/completion)
- [Управление IAM-ключами](https://yandex.cloud/en/docs/iam/operations/api-key/create)
- [AI Studio (тест в браузере)](https://console.yandex.cloud/link/foundation-models)
- [Цены Foundation Models](https://yandex.cloud/ru/prices#foundation-models)
- [Квоты и лимиты](https://yandex.cloud/en/docs/foundation-models/concepts/limits)

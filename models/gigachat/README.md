# GigaChat (Сбер)

## Получение доступа

### Шаг 1 — Регистрация в Sber Studio

1. Зайди на [developers.sber.ru/studio](https://developers.sber.ru/studio/workspaces/my-space/get/gigachat-api)
2. Войди через **СберID** (нужен аккаунт Сбербанк Онлайн) или зарегистрируйся
3. На странице GigaChat API нажми **Подключить**
4. Создай проект (или используй дефолтный workspace)

### Шаг 2 — Получить credentials

1. В личном кабинете студии → **GigaChat API** → твой проект
2. Вкладка **Настройки** → раздел **Авторизационные данные**
3. Нажми **Получить Client Secret** — скопируй `Client ID` и `Client Secret`
4. Credentials = `Base64(Client_ID:Client_Secret)` — либо вычисляй сам, либо библиотека сделает автоматически

> ⚠️ **Важно:** GigaChat требует сертификаты НУЦ Минцифры для HTTPS.
> Инструкция: [developers.sber.ru/docs/ru/gigachat/certificates](https://developers.sber.ru/docs/ru/gigachat/certificates)
> Без них запросы падают с SSL-ошибкой. Для разработки можно отключить проверку (`verify=False`), но не в проде.

**В `.env`:**
```
GIGACHAT_CREDENTIALS=Base64(client_id:client_secret)
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_SCOPE=GIGACHAT_API_PERS
```

`GIGACHAT_SCOPE`:
- `GIGACHAT_API_PERS` — для физлиц
- `GIGACHAT_API_CORP` — для юрлиц/ИП (другой договор)

## Актуальные модели

| Модель | Описание |
|--------|----------|
| `GigaChat` | Базовая |
| `GigaChat-Pro` | Продвинутая, лучше для задач |
| `GigaChat-Max` | Максимальная |
| `GigaChat-2-Max` | Последняя флагманская (2026) |

Цены: [developers.sber.ru/docs/ru/gigachat/api/tariffs](https://developers.sber.ru/docs/ru/gigachat/api/tariffs)

## Как работает API

GigaChat совместим с OpenAI Chat Completions — можно использовать официальный SDK `gigachat`:

```python
from gigachat import GigaChat as GigaChatClient
import os, time

# SDK автоматически получает и обновляет OAuth-токен
client = GigaChatClient(
    credentials=os.environ["GIGACHAT_CREDENTIALS"],
    scope=os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
    model=os.environ.get("GIGACHAT_MODEL", "GigaChat-Pro"),
    verify_ssl_certs=False,  # только для разработки без сертификатов Минцифры
)

start = time.time()
response = client.chat(
    {
        "messages": [
            {"role": "system", "content": "Ты решаешь олимпиадные задачи. Думай пошагово и дай финальный ответ."},
            {"role": "user", "content": problem_text}
        ]
        # НЕ передаём function_call / tools → чистый текстовый ответ
    }
)
latency_ms = int((time.time() - start) * 1000)

answer = response.choices[0].message.content
prompt_tokens = response.usage.prompt_tokens
completion_tokens = response.usage.completion_tokens
```

### Альтернатива: через OpenAI-совместимый endpoint

```python
import openai, os

client = openai.OpenAI(
    api_key="<oauth_token>",   # получить отдельно через /oauth
    base_url="https://gigachat.devices.sberbank.ru/api/v1",
)
# Далее как обычный OpenAI клиент
```

## Подсчёт стоимости

GigaChat считает в **рублях**, токены — собственные. Цену за токен смотри в тарифах. В `SolveResult.cost_usd` переводи по текущему курсу или храни отдельное поле `cost_rub`.

## Будущее: включить инструменты

GigaChat поддерживает function calling (одна функция за запрос):
```python
"functions": [{"name": "...", "description": "...", "parameters": {...}}],
"function_call": "auto"
```

Документация: [developers.sber.ru/docs/ru/gigachat/guides/functions/overview](https://developers.sber.ru/docs/ru/gigachat/guides/functions/overview)

## Полезные ссылки

- [Быстрый старт (физлица)](https://developers.sber.ru/docs/ru/gigachat/individuals-quickstart)
- [Справка API](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/gigachat-api)
- [SDK gigachat (PyPI)](https://github.com/ai-forever/gigachat)
- [Песочница промптов](https://developers.sber.ru/docs/ru/gigachat/prompts-hub/playground)
- [Тарифы](https://developers.sber.ru/docs/ru/gigachat/api/tariffs)
- [Поддержка](https://t.me/SD_SmartApp_Supprot_Bot)

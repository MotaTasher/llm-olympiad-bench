# GPT (OpenAI)

## Получение API-ключа

1. Зайди на [platform.openai.com](https://platform.openai.com) → войди или зарегистрируйся
2. Левое меню → **API keys** (или напрямую: [platform.openai.com/api-keys](https://platform.openai.com/api-keys))
3. Нажми **+ Create new secret key** → дай имя → **Create secret key**
4. Скопируй ключ сразу — потом не покажет
5. Пополни баланс: [platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing) → **Add to credit balance**

**В `.env`:**
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

## Актуальные модели для задачи

| Модель | Описание | Цена (вход/выход) |
|--------|----------|-------------------|
| `gpt-4o` | Основная, быстрая | $2.50 / $10.00 за 1M токенов |
| `gpt-4o-mini` | Дешевле, чуть слабее | $0.15 / $0.60 |
| `o3` | Reasoning, думает дольше | $2.00 / $8.00 |
| `o4-mini` | Reasoning, дешевле | $1.10 / $4.40 |

Цены актуальны на 2026-06 — сверяй на [openai.com/api/pricing](https://openai.com/api/pricing)

## Как работает API (text-only, без инструментов)

Endpoint: `POST https://api.openai.com/v1/chat/completions`

Инструменты (`tools`) — **opt-in**: просто не передаём поле — и модель работает без них.

```python
import openai, os, time

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

start = time.time()
response = client.chat.completions.create(
    model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
    messages=[
        {"role": "system", "content": "Ты решаешь олимпиадные задачи. Думай пошагово и дай финальный ответ."},
        {"role": "user", "content": problem_text}
    ],
    # НЕ передаём tools= → никакого веба, кода, поиска
)
latency_ms = int((time.time() - start) * 1000)

answer = response.choices[0].message.content
prompt_tokens = response.usage.prompt_tokens
completion_tokens = response.usage.completion_tokens
```

## Подсчёт стоимости

Цены хранить константами в `gpt.py`:
```python
# Цены за 1 токен в USD (обновить при смене модели)
PRICE_INPUT_PER_TOKEN = 2.50 / 1_000_000   # gpt-4o
PRICE_OUTPUT_PER_TOKEN = 10.00 / 1_000_000

cost_usd = (prompt_tokens * PRICE_INPUT_PER_TOKEN +
            completion_tokens * PRICE_OUTPUT_PER_TOKEN)
```

## Будущее: включить инструменты

Когда нужно будет добавить веб-поиск или код — передать в запрос:
```python
tools=[{"type": "web_search_preview"}]
# или
tools=[{"type": "code_interpreter"}]
```

Документация: [platform.openai.com/docs/guides/tools](https://platform.openai.com/docs/guides/tools)

## Полезные ссылки

- [Документация Chat Completions](https://platform.openai.com/docs/api-reference/chat)
- [Список моделей и цены](https://openai.com/api/pricing)
- [Playground для теста](https://platform.openai.com/playground)
- [Лимиты и квоты](https://platform.openai.com/settings/organization/limits)

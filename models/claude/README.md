# Claude (Anthropic)

## Получение API-ключа

1. Зайди на [console.anthropic.com](https://console.anthropic.com) → войди или зарегистрируйся
2. Левое меню → **Settings** → **API Keys** (или: [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys))
3. Нажми **Create Key** → дай имя → **Create Key**
4. Скопируй сразу — потом не покажет
5. Пополни баланс: **Settings** → **Billing** → **Add credits**

**В `.env`:**
```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-5
```

## Актуальные модели для задачи

| Модель | Описание | Цена (вход/выход) |
|--------|----------|-------------------|
| `claude-opus-4-5` | Самая мощная | $15 / $75 за 1M токенов |
| `claude-sonnet-4-5` | Баланс цена/качество | $3 / $15 |
| `claude-haiku-4-5` | Быстрая и дешёвая | $0.80 / $4 |

Цены актуальны на 2026-06 — сверяй на [anthropic.com/pricing](https://www.anthropic.com/pricing)

## Как работает API (text-only, без инструментов)

Endpoint: `POST https://api.anthropic.com/v1/messages`

Инструменты — **opt-in**: без поля `tools` в запросе — никакого веба, кода, поиска.

```python
import anthropic, os, time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

start = time.time()
response = client.messages.create(
    model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5"),
    max_tokens=4096,
    system="Ты решаешь олимпиадные задачи. Думай пошагово и дай финальный ответ.",
    messages=[
        {"role": "user", "content": problem_text}
    ],
    # НЕ передаём tools= → чистый текстовый ответ
)
latency_ms = int((time.time() - start) * 1000)

answer = response.content[0].text
prompt_tokens = response.usage.input_tokens
completion_tokens = response.usage.output_tokens
```

## Подсчёт стоимости

```python
PRICE_INPUT_PER_TOKEN = 15.00 / 1_000_000   # claude-opus-4-5
PRICE_OUTPUT_PER_TOKEN = 75.00 / 1_000_000

cost_usd = (prompt_tokens * PRICE_INPUT_PER_TOKEN +
            completion_tokens * PRICE_OUTPUT_PER_TOKEN)
```

## Extended Thinking (опционально)

Для сложных задач можно включить расширенное обдумывание — модель тратит больше токенов на внутренние рассуждения:

```python
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=16000,
    thinking={"type": "enabled", "budget_tokens": 10000},
    messages=[{"role": "user", "content": problem_text}]
)
# Думающие токены тоже биллятся, учитывать в cost_usd
```

## Будущее: включить инструменты

```python
tools=[{"type": "web_search_20260209"}]
# или custom tools через стандартный tool_use
```

Документация: [platform.claude.com/docs/en/agents-and-tools/tool-use/overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

## Полезные ссылки

- [Документация Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Список моделей](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Workbench (тест в браузере)](https://console.anthropic.com/workbench)
- [Цены](https://www.anthropic.com/pricing)
- [Лимиты](https://platform.claude.com/docs/en/api/rate-limits)

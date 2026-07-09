# Claude (Anthropic)

Этот адаптер запускает Claude через общий `runner.py` в text-only режиме: без `tools`, web search, computer use и внешних цепочек.
Единый лимит output-токенов задаётся через `runner.py --max-tokens`; `ANTHROPIC_MAX_TOKENS` остаётся fallback-настройкой.
Адаптер сам режет общий лимит на provider-совместимые запросы: до `128000`
output-токенов за запрос для `claude-opus-4-8` и до `64000` для
`claude-haiku-4-5-20251001`.

## 1. Как получить ключ

1. Открой [console.anthropic.com](https://console.anthropic.com) и войди в аккаунт.
2. Перейди в **Settings** -> **API Keys** или открой [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
3. Нажми **Create Key**.
4. Скопируй ключ сразу после создания.
5. Проверь billing и лимиты аккаунта, иначе запросы к API могут не пройти.

## 2. Как положить ключ

Создай файл:

```text
models/claude/secrets/.env
```

Если папки еще нет:

```bash
mkdir -p models/claude/secrets
```

Положи туда только credential:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

Файл лежит в gitignored-папке `models/claude/secrets/` и не должен попадать в репозиторий.

## 3. Где выбирать модель

Не клади `ANTHROPIC_MODEL` в `models/claude/secrets/.env`, корневой `.env` или shell env для обычных запусков. Secret-файл нужен только для ключей.

Default-модель выбирается в:

```text
models/claude/versions.py
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
ANTHROPIC_MODEL=claude-opus-4-8
ANTHROPIC_MAX_TOKENS=12000
# ANTHROPIC_THINKING_BUDGET_TOKENS=8000
```

Runtime-настройки, которые не являются секретами, тоже должны жить в `config/models.env`. Например:

```env
ANTHROPIC_MAX_TOKENS=4096
```

`ANTHROPIC_THINKING_BUDGET_TOKENS` включает extended thinking и задает максимум thinking tokens там, где конкретная версия Claude поддерживает ручной thinking budget. `ANTHROPIC_MAX_TOKENS` должен быть больше thinking budget. API не гарантирует минимум thinking tokens. Extended/adaptive thinking тарифицируется как output tokens; если Anthropic возвращает `output_tokens_details.reasoning_tokens`, адаптер сохраняет это в `usage.reasoning_tokens`, а `cost.reasoning` показывает поддолю output-стоимости. Локальная таблица цен в `models/pricing.py` должна соответствовать официальной Anthropic pricing table.
Для `claude-opus-4-8` ручной `thinking: {type: "enabled", budget_tokens: ...}` не поддерживается; при заданном `ANTHROPIC_THINKING_BUDGET_TOKENS` адаптер включает `thinking: {type: "adaptive"}` и `output_config: {effort: ...}`. Effort задается через `ANTHROPIC_EFFORT` (`max` по умолчанию в проекте для максимального Claude-режима). Для моделей с manual thinking budget адаптер режет `ANTHROPIC_THINKING_BUDGET_TOKENS` так, чтобы в каждом запросе осталось не меньше `ANTHROPIC_FINAL_TOKEN_RESERVE` токенов под видимый ответ. Если Anthropic возвращает `output_tokens_details.thinking_tokens`, адаптер также нормализует это значение в `usage.reasoning_tokens`.

Anthropic Python SDK требует streaming для запросов с `max_tokens > 21333`,
потому что такие запросы могут идти дольше non-streaming timeout. Адаптер
переключается на Messages streaming автоматически выше этого порога и затем
собирает финальный текст из итогового message. Стоимость API от streaming не
меняется: тарификация остается по input/output токенам.

Если общий `--max-tokens` больше лимита одного Claude-запроса и Claude вернул
только thinking/redacted thinking без видимого текста, адаптер продолжает
Messages-диалог следующим запросом. Для продолжения он передает предыдущие
assistant `content` blocks неизмененными и добавляет короткое user-сообщение
`Continue.`. Это официальный формат Anthropic для сохранения подписанных
thinking-блоков; адаптер не пересказывает reasoning в обычный prompt и не
подключает инструменты.

`runner.load_env()` специально игнорирует старые `ANTHROPIC_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

## Проверка

```bash
python scripts/check_secrets.py --models claude
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models claude \
  --run-id smoke_claude
```

## Tools и runtime

Адаптер использует Anthropic Messages API и не передает `tools`, web search или computer use. Это важно для честного сравнения олимпиадных решений: модель должна отвечать только текстом, без внешних инструментов.

Tools не включаются через конфиг. Если в payload случайно появится `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, общий guard в `models/common.py` остановит запрос.

Настраивать можно только text-only runtime:

```env
ANTHROPIC_MAX_TOKENS=12000
ANTHROPIC_THINKING_BUDGET_TOKENS=60000
ANTHROPIC_FINAL_TOKEN_RESERVE=4096
ANTHROPIC_EFFORT=max
```

Если API вернул usage и stop reason, но не вернул видимый текстовый ответ,
адаптер записывает `SolveResult.error`, а не успешное пустое решение.

## Полезные ссылки

- [Anthropic API keys](https://console.anthropic.com/settings/keys)
- [Anthropic docs](https://docs.anthropic.com)
- [Anthropic pricing](https://www.anthropic.com/pricing)

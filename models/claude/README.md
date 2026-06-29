# Claude (Anthropic)

Этот адаптер запускает Claude через общий `runner.py` в text-only режиме: без `tools`, web search, computer use и внешних цепочек.
Единый лимит output-токенов задаётся через `runner.py --max-tokens`; `ANTHROPIC_MAX_TOKENS` остаётся fallback-настройкой.

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

`ANTHROPIC_THINKING_BUDGET_TOKENS` включает extended thinking и задает максимум thinking tokens. `ANTHROPIC_MAX_TOKENS` должен быть больше thinking budget. API не гарантирует минимум thinking tokens.

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
# ANTHROPIC_THINKING_BUDGET_TOKENS=8000
```

## Полезные ссылки

- [Anthropic API keys](https://console.anthropic.com/settings/keys)
- [Anthropic docs](https://docs.anthropic.com)
- [Anthropic pricing](https://www.anthropic.com/pricing)

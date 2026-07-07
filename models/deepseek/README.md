# DeepSeek

Этот адаптер запускает DeepSeek через OpenAI-compatible Chat Completions API в text-only режиме: без `tools`, function calling, поиска и внешних цепочек.
Единый лимит completion-токенов задаётся через `runner.py --max-tokens`; `DEEPSEEK_MAX_TOKENS` остаётся fallback-настройкой.

## 1. Как получить ключ

1. Открой [platform.deepseek.com](https://platform.deepseek.com) и войди в аккаунт.
2. Перейди в раздел API keys.
3. Создай новый API key.
4. Скопируй ключ сразу после создания.
5. Проверь баланс, лимиты и доступность нужных моделей в аккаунте.

## 2. Как положить ключ

Создай файл:

```text
models/deepseek/secrets/.env
```

Если папки еще нет:

```bash
mkdir -p models/deepseek/secrets
```

Положи туда только credential:

```env
DEEPSEEK_API_KEY=...
```

Файл лежит в gitignored-папке `models/deepseek/secrets/` и не должен попадать в репозиторий.

## 3. Где выбирать модель

Не клади `DEEPSEEK_MODEL` в `models/deepseek/secrets/.env`, корневой `.env` или shell env для обычных запусков. Secret-файл нужен только для ключей.

Default-модель выбирается в:

```text
models/deepseek/versions.py
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
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_MAX_TOKENS=8192
```

Runtime-настройки, которые не являются секретами, тоже должны жить в `config/models.env`:

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=8192
```

`DEEPSEEK_MAX_TOKENS` ограничивает output. Для reasoning-моделей DeepSeek этот лимит включает reasoning content там, где провайдер считает его частью output. API не гарантирует минимум thinking tokens. В калькуляторе стоимости reasoning для DeepSeek V4 считается по обычной output-ставке модели.

`runner.load_env()` специально игнорирует старые `DEEPSEEK_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

## Проверка

```bash
python scripts/check_secrets.py --models deepseek
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models deepseek \
  --run-id smoke_deepseek
```

Список моделей, доступных конкретному ключу, можно проверить через API:

```bash
curl https://api.deepseek.com/models \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

## Tools и runtime

Адаптер использует OpenAI-compatible Chat Completions API и не передает `tools` или function calling. Это важно для честного сравнения олимпиадных решений: модель должна отвечать только текстом, без внешних инструментов.

Tools не включаются через конфиг. Если в payload случайно появится `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, общий guard в `models/common.py` остановит запрос.

Настраивать можно только text-only runtime:

```env
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=8192
```

Если API вернул usage и finish reason, но не вернул видимый текстовый ответ,
адаптер записывает `SolveResult.error`, а не успешное пустое решение.

## Полезные ссылки

- [DeepSeek platform](https://platform.deepseek.com)
- [DeepSeek API docs](https://api-docs.deepseek.com)

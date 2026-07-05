# GPT (OpenAI)

Этот адаптер запускает OpenAI-модели через Responses API в text-only режиме:
без `tools`, поиска, code interpreter и function calling.
Единый лимит output-токенов задаётся через `runner.py --max-tokens`;
`OPENAI_MAX_COMPLETION_TOKENS` остаётся fallback-настройкой.

## 1. Как получить ключ

1. Открой [platform.openai.com](https://platform.openai.com) и войди в аккаунт.
2. Перейди в раздел API keys: [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
3. Нажми **Create new secret key**.
4. Скопируй ключ сразу после создания. Позже платформа не покажет его полностью.
5. Проверь billing и лимиты проекта в настройках платформы, иначе API-запросы могут отклоняться.

## 2. Как положить ключ

Создай файл:

```text
models/gpt/secrets/.env
```

Если папки еще нет:

```bash
mkdir -p models/gpt/secrets
```

Положи туда только credential:

```env
OPENAI_API_KEY=sk-...
```

Файл лежит в gitignored-папке `models/gpt/secrets/` и не должен попадать в репозиторий.

## 3. Где выбирать модель

Не клади `OPENAI_MODEL` в `models/gpt/secrets/.env`, корневой `.env` или shell env для обычных запусков. Secret-файл нужен только для ключей.

Default-модель выбирается в:

```text
models/gpt/versions.py
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
OPENAI_MODEL=gpt-5.5
OPENAI_REASONING_EFFORT=high
OPENAI_MAX_COMPLETION_TOKENS=12000
OPENAI_TIMEOUT_SECONDS=7200
```

`runner.load_env()` специально игнорирует старые `OPENAI_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

`OPENAI_REASONING_EFFORT` побуждает reasoning-модель думать больше или меньше.
`OPENAI_MAX_COMPLETION_TOKENS` задает общий hard cap на generated tokens, если
`runner.py --max-tokens` не передан. API не гарантирует минимум thinking tokens.
Если Responses API возвращает `output_tokens_details.reasoning_tokens`, адаптер
сохраняет это число в `usage.reasoning_tokens`; `cost.reasoning` является
поддолей уже учтенной output-стоимости, а не дополнительной надбавкой.
`OPENAI_TIMEOUT_SECONDS` задает HTTP timeout одного Responses API request;
по умолчанию адаптер ждёт 7200 секунд, потому что 128K output/reasoning-запросы
могут занимать заметно больше стандартных 10 минут SDK.

## Проверка

```bash
python scripts/check_secrets.py --models gpt
python runner.py \
  --problem data/competitions/local_examples/example.json \
  --models gpt \
  --run-id smoke_gpt
```

## Tools и runtime

Адаптер использует Responses API и не передает `tools`, web search,
code interpreter или function calling. Это важно для честного сравнения
олимпиадных решений: модель должна отвечать только текстом, без внешних
инструментов.

Для reasoning-моделей `max_output_tokens` включает both reasoning tokens and
visible output tokens. Если общий бюджет больше лимита одного OpenAI-запроса,
адаптер режет его по `OPENAI_MAX_OUTPUT_TOKENS_BY_MODEL` и делает следующий
Responses API request только когда предыдущий не вернул непустой visible
output. Следующий request связывается с предыдущим через `previous_response_id`,
поэтому модель может использовать сохраненное reasoning state. Как только
появляется непустой ответ, цепочка останавливается.

Tools не включаются через конфиг. Если в payload случайно появится `tools`, `tool_choice`, `functions`, `function_call` или `web_search_options`, общий guard в `models/common.py` остановит запрос.

Настраивать можно только text-only runtime:

```env
OPENAI_REASONING_EFFORT=high
OPENAI_MAX_COMPLETION_TOKENS=12000
OPENAI_TIMEOUT_SECONDS=7200
OPENAI_MAX_RETRIES=0
```

## Полезные ссылки

- [OpenAI API keys](https://platform.openai.com/api-keys)
- [OpenAI API docs](https://platform.openai.com/docs)
- [OpenAI pricing](https://openai.com/api/pricing)

# GPT (OpenAI)

Этот адаптер запускает OpenAI-модели через общий `runner.py` в text-only режиме: без `tools`, поиска, code interpreter и function calling.

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
OPENAI_MODEL=gpt-5.4
OPENAI_REASONING_EFFORT=high
OPENAI_MAX_COMPLETION_TOKENS=12000
```

`runner.load_env()` специально игнорирует старые `OPENAI_MODEL` из `.env`, shell env и `models/*/secrets/.env`, чтобы выбор модели был централизован. Shell override разрешается только при запуске с флагом `--allow-env-model-overrides`.

`OPENAI_REASONING_EFFORT` побуждает reasoning-модель думать больше или меньше. `OPENAI_MAX_COMPLETION_TOKENS` задает hard cap на generated tokens. API не гарантирует минимум thinking tokens.

## Проверка

```bash
python scripts/check_secrets.py --models gpt
python runner.py --problem data/problems/example.json --models gpt --run-id smoke_gpt
```

## Text-Only Policy

Адаптер использует Chat Completions и не передает `tools`. Это важно для честного сравнения олимпиадных решений: модель должна отвечать только текстом, без внешних инструментов.

## Полезные ссылки

- [OpenAI API keys](https://platform.openai.com/api-keys)
- [OpenAI API docs](https://platform.openai.com/docs)
- [OpenAI pricing](https://openai.com/api/pricing)

# Olympiad Scorer

Система для сравнения решений LLM на олимпиадных задачах. Запускает несколько нейронок на одну задачу, логирует метрики, предоставляет веб-интерфейс для ручного скоринга.

---

## Быстрый запуск

### Локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполни .env ключами
python runner.py --problem data/problems/example.json --models gpt,claude,gigachat,yandexgpt
python scoring/app.py
```

### Локальный тест GPT, GigaChat и YandexGPT

Секреты можно хранить рядом с кодом конкретной модели. Эти папки игнорируются git:

```text
models/gpt/secrets/.env
models/gigachat/secrets/.env
models/yandexgpt/secrets/.env
```

GPT:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
```

GigaChat:

```env
GIGACHAT_CREDENTIALS=...
GIGACHAT_CLIENT_ID=...
GIGACHAT_CLIENT_SECRET=...
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_SCOPE=GIGACHAT_API_PERS
```

YandexGPT:

```env
YANDEX_API_KEY=...
YANDEX_API_KEY_ID=...
YANDEX_FOLDER_ID=...
YANDEX_MODEL=yandexgpt-pro
```

Проверить наличие секретов без вывода значений:

```bash
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt
```

Запустить тест:

```bash
python runner.py --problem data/problems/example.json --models gpt,gigachat,yandexgpt --run-id local_test
```

Тестовый ноутбук для GPT:

```bash
jupyter notebook notebooks/test_gpt_runner.ipynb
```

### Через GitHub Actions

Workflow `.github/workflows/run-benchmark.yml` запускается вручную через **Actions → Run benchmark → Run workflow**.
В репозиторий нужно положить только Secrets:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GIGACHAT_CREDENTIALS
# или вместо GIGACHAT_CREDENTIALS:
GIGACHAT_CLIENT_ID
GIGACHAT_CLIENT_SECRET
YANDEX_API_KEY
YANDEX_FOLDER_ID
```

Опциональные настройки моделей можно положить в **Variables**:

```text
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-opus-4-5
GIGACHAT_MODEL=GigaChat-Pro
YANDEX_MODEL=yandexgpt-pro
RUB_PER_USD=90
```

Логи прогона Actions сохраняет как artifact `benchmark-logs`.

---

## Архитектура

```
olympiad-scorer/
├── README.md
├── .env.example
├── requirements.txt
│
├── models/                    # Адаптеры под каждую LLM
│   ├── __init__.py
│   ├── base.py                # Абстрактный BaseModel + датакласс SolveResult
│   ├── gpt.py                 # OpenAI GPT (gpt-4o и др.)
│   ├── claude.py              # Anthropic Claude
│   ├── gigachat.py            # Сбер GigaChat
│   └── alice.py               # Яндекс YandexGPT / Alice
│
├── runner.py                  # Единый скрипт запуска
│
├── logs/                      # JSON-логи прогонов (gitignored кроме .gitkeep)
│   └── .gitkeep
│
├── scoring/                   # Веб-интерфейс для ручного скоринга
│   ├── app.py
│   └── templates/
│       ├── index.html
│       └── review.html
│
└── data/
    ├── problems/              # Задачи (JSON или Markdown)
    └── results/               # Итоговые CSV с оценками
```

---

## Интерфейсы (что должен реализовать агент)

### `models/base.py`

```python
from dataclasses import dataclass
from typing import Optional
import abc

@dataclass
class SolveResult:
    model: str                    # идентификатор модели, напр. "gpt-4o"
    answer: str                   # текст ответа
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float               # стоимость запроса в долларах
    latency_ms: int               # время ответа в мс
    raw_response: dict            # полный ответ от API (для дебага)
    error: Optional[str] = None   # если запрос упал

class BaseModel(abc.ABC):
    """Каждый адаптер наследует этот класс и реализует solve()."""
    
    @property
    @abc.abstractmethod
    def model_id(self) -> str:
        """Уникальный идентификатор модели, напр. 'gpt-4o'."""
        ...

    @abc.abstractmethod
    def solve(self, problem: str) -> SolveResult:
        """
        Принимает текст задачи, возвращает SolveResult.
        Не должен бросать исключения — ошибки пишем в SolveResult.error.
        """
        ...
```

### `models/*.py` — каждый адаптер

Каждый файл реализует `BaseModel`. Ключи API берёт из переменных окружения (см. `.env.example`). Обязательно считает `cost_usd` по актуальным ценам (константы в начале файла).

### `runner.py`

CLI-скрипт. Принимает аргументы:

```
python runner.py \
  --problem data/problems/task1.json \
  --models gpt,claude,gigachat,alice \
  --run-id my_run_01          # опционально, иначе генерируется timestamp
```

Логика:
1. Загружает задачу из файла (поле `text` в JSON, или весь файл если `.md`)
2. Для каждой модели из `--models` — импортирует адаптер, вызывает `solve()`
3. Пишет лог в `logs/<run-id>.json` (структура ниже)
4. Выводит краткую таблицу в stdout: модель | токены | цена | статус

### Формат лога `logs/<run-id>.json`

```json
{
  "run_id": "20260602_153000",
  "problem_file": "data/problems/task1.json",
  "problem_text": "Условие задачи...",
  "timestamp": "2026-06-02T15:30:00Z",
  "results": [
    {
      "model": "gpt-4o",
      "answer": "Решение...",
      "prompt_tokens": 312,
      "completion_tokens": 850,
      "cost_usd": 0.0045,
      "latency_ms": 2340,
      "error": null,
      "score": null,          // заполняется через веб-интерфейс
      "scored_by": null,      // email/имя судьи
      "scored_at": null,
      "score_comment": null,
      "raw_response": {}
    }
  ]
}
```

### `scoring/app.py`

Flask или FastAPI веб-сервер. Функции:

- `GET /` — список всех прогонов из `logs/`
- `GET /run/<run-id>` — страница ревью: задача + все ответы + форма оценки
- `POST /score` — принимает `{run_id, model, score, scored_by, comment}`, пишет в лог

Интерфейс `review.html`:
- Слева: условие задачи
- Справа: ответы каждой модели (скрыто до клика, чтобы избежать bias)
- Под каждым ответом: слайдер 0–10 + поле комментария + кнопка "Сохранить"
- Метрики (токены, цена, время) показываются **после** оценки

---

## Задачи в `data/problems/`

Формат JSON:

```json
{
  "id": "task1",
  "title": "Название задачи",
  "source": "Олимпиада X, 2025",
  "text": "Полный текст условия...",
  "expected_answer": null     // опционально, для автоскоринга позже
}
```

---

## API — режим "только рассуждение, без инструментов"

Цель: модель получает задачу, думает своими силами и выдаёт текстовый ответ. Никакого кода, гугления, калькуляторов.

### GPT (OpenAI)
**✅ Полностью управляется через API.**
- Инструменты (web_search, code_interpreter) подключаются явно через поле `tools`. Если не передавать — модель их не имеет.
- Для Chat Completions (`/v1/chat/completions`) по умолчанию никаких инструментов нет.
- Для Responses API (`/v1/responses`) web_search тоже opt-in.
- Reasoning-модели (o3, o4-mini) думают внутри `reasoning_tokens`, результат — чистый текст.
- **Вывод:** просто не передавать `tools` в запросе. Достаточно.

### Claude (Anthropic)
**✅ Полностью управляется через API.**
- Web search, code execution — всё opt-in через поле `tools`.
- Без `tools` в запросе — модель работает только с текстом.
- Extended thinking (`"thinking": {"type": "enabled"}`) — внутренний процесс, не даёт инструментов.
- **Вывод:** просто не передавать `tools`. Достаточно.

### GigaChat (Сбер)
**✅ Управляется через API, но с нюансами.**
- API совместим с OpenAI Chat Completions — инструменты передаются в `tools` и opt-in.
- Ограничение: только один вызов функции за запрос (не цепочка).
- Собственный sandbox для выполнения кода — встроен в чат-интерфейс, не в API.
- **Вывод:** не передавать `tools` — модель отвечает текстом. Sandbox через API не активируется.

### YandexGPT / Alice (Яндекс)
**✅ Управляется через API.**
- Базовый API (`/foundationModels/v1/completion`) — чистый text-in / text-out, инструментов нет вообще.
- В Yandex AI Studio есть поиск и инструменты — но это UI, не API.
- Alice (голосовой ассистент) через API не доступна напрямую; для скоринга используем YandexGPT API.
- **Вывод:** базовый completion API изначально без инструментов. Ничего отключать не нужно.

### Итог для адаптеров

| Модель     | Инструменты по умолчанию | Что делать в адаптере                  |
|------------|--------------------------|----------------------------------------|
| GPT        | Нет                      | Не передавать `tools`                  |
| Claude     | Нет                      | Не передавать `tools`                  |
| GigaChat   | Нет                      | Не передавать `tools`                  |
| YandexGPT  | Нет (нет в API)          | Ничего, базовый completion endpoint    |

**Все четыре модели через API работают в режиме "только текст" по умолчанию — инструменты нужно подключать явно.**

---

## `.env.example`

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GIGACHAT_API_KEY=...
GIGACHAT_CLIENT_ID=...
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
```

---

## `requirements.txt` (минимум)

```
openai>=1.0
anthropic>=0.25
requests
flask          # или fastapi + uvicorn
python-dotenv
tabulate       # для таблицы в stdout
```

---

## Что делать агенту

1. **Реализовать адаптеры** — `models/gpt.py`, `models/claude.py`, `models/gigachat.py`, `models/alice.py`
   - Каждый наследует `BaseModel`, реализует `solve()`, считает `cost_usd`
   - Ошибки (таймаут, 429, etc.) ловим и пишем в `SolveResult.error`, не бросаем

2. **Реализовать `runner.py`** — CLI с argparse, загрузка задачи, параллельный (или sequential) вызов моделей, запись лога

3. **Реализовать `scoring/`** — простой веб-сервер, чтение логов, форма скоринга, запись оценки обратно в JSON

4. **Не трогать** формат `SolveResult` и формат лога без обновления этого README — от них зависит совместимость runner ↔ scoring

---

## Приоритеты реализации

1. `models/base.py` + `models/gpt.py` (эталонный адаптер)
2. `runner.py` (можно с одной моделью)
3. Остальные адаптеры (`claude`, `gigachat`, `alice`)
4. `scoring/app.py` + `review.html`

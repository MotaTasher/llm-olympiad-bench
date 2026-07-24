window.RESULTS_DATA = {
  releases: [
    {
      id: "math-cup-2026",
      series: "Math Cup",
      year: "2026",
      shortTitle: "2026",
      title: "Math Cup 2026",
      description: "Отборочный тур и финал идут последовательно — один выпуск, одна страница и две независимые таблицы.",
      competitionIds: ["math-cup-2026-qualifying", "math-cup-2026-final"]
    },
    {
      id: "math-cup-2025-spring",
      series: "Math Cup",
      year: "2025",
      shortTitle: "2025 · Весна",
      title: "Math Cup 2025",
      description: "Весенний выпуск Math Cup 2025 и результаты его финального этапа.",
      competitionIds: ["math-cup-2025-spring-final"]
    },
    {
      id: "math-cup-2025-winter",
      series: "Math Cup",
      year: "2025",
      shortTitle: "2025 · Зима",
      title: "Math Cup 2025",
      description: "Зимний отбор и финал Math Cup 2025 собраны на одной странице в хронологическом порядке.",
      competitionIds: ["math-cup-2025-winter-qualifying", "math-cup-2025-winter-final"]
    },
    {
      id: "vsosh-ai-2026",
      series: "ВсОШ по ИИ",
      year: "2026",
      shortTitle: "Финал · 2026",
      title: "ВсОШ по ИИ 2026",
      description: "Заключительный этап профиля «Искусственный интеллект».",
      competitionIds: ["vsosh-ai-2026-round-1"]
    }
  ],
  series: [
    { id: "all", label: "Все соревнования" },
    { id: "math-cup", label: "Math Cup" },
    { id: "algo-cup", label: "Algo Cup" },
    { id: "vsosh-ai", label: "ВсОШ по ИИ" }
  ],
  competitions: [
    {
      id: "math-cup-2026-final",
      series: "math-cup",
      seriesLabel: "Math Cup",
      editionLabel: "2026 · Финал",
      title: "Math Cup 2026",
      stage: "Финал",
      date: "17 мая 2026",
      description: "Сравниваем, как языковые модели решают задачи финала — без инструментов, поиска и доступа к коду.",
      taskCount: 9,
      tasks: [
        { id: "task_01", short: "01", title: "Задача 1" },
        { id: "task_02", short: "02", title: "Задача 2" },
        { id: "task_03", short: "03", title: "Задача 3" },
        { id: "task_04", short: "04", title: "Задача 4" },
        { id: "task_05", short: "05", title: "Задача 5" },
        { id: "task_06", short: "06", title: "Задача 6" },
        { id: "task_07", short: "07", title: "Задача 7" },
        { id: "task_08", short: "08", title: "Строки" },
        { id: "task_09", short: "09", title: "Задача 9" }
      ],
      participants: [
        {
          id: "gpt-5-5",
          type: "model",
          rank: 1,
          name: "GPT-5.5",
          provider: "OpenAI",
          scores: [100, 100, 100, 100, 100, null, 90, 100, 100],
          solved: 7,
          accuracy: 98.8,
          cost: 2.189,
          tokens: 154477
        },
        {
          id: "gpt-5-4-mini",
          type: "model",
          rank: 2,
          name: "GPT-5.4 mini",
          provider: "OpenAI",
          scores: [100, 100, 100, 100, null, 0, 0, 50, 0],
          solved: 4,
          accuracy: 56.2,
          cost: 4.788,
          tokens: 614816
        },
        {
          id: "claude-opus-4-8",
          type: "model",
          rank: 3,
          name: "Claude Opus 4.8",
          provider: "Anthropic",
          scores: [100, 100, 90, 100, 0, 50, 0, 0, 0],
          solved: 3,
          accuracy: 48.9,
          cost: 2.842,
          tokens: 40885
        },
        {
          id: "deepseek-v4-pro",
          type: "model",
          rank: 4,
          name: "DeepSeek V4 Pro",
          provider: "DeepSeek",
          scores: [100, 100, 100, 0, 0, 50, 0, 50, 0],
          solved: 3,
          accuracy: 44.4,
          cost: 0.518,
          tokens: 596888
        },
        {
          id: "deepseek-v4-flash",
          type: "model",
          rank: 5,
          name: "DeepSeek V4 Flash",
          provider: "DeepSeek",
          scores: [0, 90, 100, 0, 0, 40, 0, 0, 90],
          solved: 1,
          accuracy: 35.6,
          cost: 0.152,
          tokens: 545733
        },
        {
          id: "claude-haiku-4-5",
          type: "model",
          rank: 6,
          name: "Claude Haiku 4.5",
          provider: "Anthropic",
          scores: [100, 0, 100, 0, 0, 0, 0, 0, 0],
          solved: 2,
          accuracy: 22.2,
          cost: 0.057,
          tokens: 17134
        },
        {
          id: "gigachat-2-max",
          type: "model",
          rank: 7,
          name: "GigaChat 2 Max",
          provider: "Сбер",
          scores: [100, 0, 0, 0, 0, 0, 0, 0, 0],
          solved: 1,
          accuracy: 11.1,
          cost: 0.068,
          tokens: 9385
        },
        {
          id: "gigachat-2",
          type: "model",
          rank: 8,
          name: "GigaChat 2",
          provider: "Сбер",
          scores: [0, 0, 0, 0, 0, 0, 0, 0, 0],
          solved: 0,
          accuracy: 0,
          cost: 0.008,
          tokens: 10620
        },
        {
          id: "yandexgpt-5-1",
          type: "model",
          rank: 9,
          name: "YandexGPT 5.1",
          provider: "Яндекс",
          scores: [0, 0, 0, 0, 0, 0, 0, 0, 0],
          solved: 0,
          accuracy: 0,
          cost: 0.09,
          tokens: 10081
        },
        {
          id: "yandexgpt-5-lite",
          type: "model",
          rank: 10,
          name: "YandexGPT 5 Lite",
          provider: "Яндекс",
          scores: [0, 0, 0, 0, 0, 0, 0, 0, 0],
          solved: 0,
          accuracy: 0,
          cost: 0.028,
          tokens: 12521
        },
        {
          id: "gemini-3-1-pro-preview",
          type: "model",
          rank: 11,
          name: "Gemini 3.1 Pro",
          provider: "Google",
          scores: [100, null, null, null, null, null, null, null, null],
          solved: 1,
          accuracy: null,
          cost: 0,
          tokens: 222442
        },
        {
          id: "gemini-3-5-flash",
          type: "model",
          rank: 12,
          name: "Gemini 3.5 Flash",
          provider: "Google",
          scores: [null, null, null, null, null, null, null, null, null],
          solved: 0,
          accuracy: null,
          cost: 0,
          tokens: 247997
        },
        {
          id: "grok-4-3",
          type: "model",
          rank: 13,
          name: "Grok 4.3",
          provider: "xAI",
          scores: [null, null, null, null, null, null, null, null, null],
          solved: 0,
          accuracy: null,
          cost: 1.012,
          tokens: 407073
        },
        {
          id: "grok-build-0-1",
          type: "model",
          rank: 14,
          name: "Grok Build 0.1",
          provider: "xAI",
          scores: [null, null, null, null, null, null, null, null, null],
          solved: 0,
          accuracy: null,
          cost: 1.92,
          tokens: 961972
        },
        {
          id: "glm-5-2",
          type: "model",
          rank: 15,
          name: "GLM 5.2",
          provider: "Z.ai",
          scores: [null, null, null, null, null, null, null, null, null],
          solved: 0,
          accuracy: null,
          cost: 0.494,
          tokens: 113080
        },
        {
          id: "glm-4-7-flash",
          type: "model",
          rank: 16,
          name: "GLM 4.7 Flash",
          provider: "Z.ai",
          scores: [null, null, null, null, null, null, null, null, null],
          solved: 0,
          accuracy: null,
          cost: 0,
          tokens: 110108
        },
        {
          id: "team-gold",
          type: "team",
          medal: "🥇",
          rank: 1,
          name: "Команда будет добавлена",
          members: "Участники будут добавлены после получения результатов",
          scores: [null, null, null, null, null, null, null, null, null]
        },
        {
          id: "team-silver",
          type: "team",
          medal: "🥈",
          rank: 2,
          name: "Команда будет добавлена",
          members: "Участники будут добавлены после получения результатов",
          scores: [null, null, null, null, null, null, null, null, null]
        },
        {
          id: "team-bronze",
          type: "team",
          medal: "🥉",
          rank: 3,
          name: "Команда будет добавлена",
          members: "Участники будут добавлены после получения результатов",
          scores: [null, null, null, null, null, null, null, null, null]
        }
      ]
    },
    {
      id: "math-cup-2026-qualifying",
      series: "math-cup",
      seriesLabel: "Math Cup",
      editionLabel: "2026 · Отбор",
      title: "Math Cup 2026",
      stage: "Отборочный тур",
      date: "10 мая 2026",
      description: "Отборочный тур Math Cup 2026. Набор задач уже есть в проекте; публичная матрица готовится.",
      taskCount: 8,
      tasks: [],
      participants: []
    },
    {
      id: "math-cup-2025-spring-final",
      series: "math-cup",
      seriesLabel: "Math Cup",
      editionLabel: "2025 · Весна",
      title: "Math Cup 2025",
      stage: "Весенний финал",
      date: "27 апреля 2025",
      description: "Финальный этап весеннего турнира.",
      taskCount: 9,
      tasks: [],
      participants: []
    },
    {
      id: "math-cup-2025-winter-qualifying",
      series: "math-cup",
      seriesLabel: "Math Cup",
      editionLabel: "2025 · Зима · Отбор",
      title: "Math Cup 2025",
      stage: "Зимний отбор",
      date: "14 декабря 2025",
      description: "Отборочный этап зимнего турнира.",
      taskCount: 10,
      tasks: [],
      participants: []
    },
    {
      id: "math-cup-2025-winter-final",
      series: "math-cup",
      seriesLabel: "Math Cup",
      editionLabel: "2025 · Зима · Финал",
      title: "Math Cup 2025",
      stage: "Зимний финал",
      date: "21 декабря 2025",
      description: "Финальный этап зимнего турнира.",
      taskCount: 8,
      tasks: [],
      participants: []
    },
    {
      id: "vsosh-ai-2026-round-1",
      series: "vsosh-ai",
      seriesLabel: "ВсОШ по ИИ",
      editionLabel: "2026 · Финал · Тур 1",
      title: "ВсОШ по ИИ 2026",
      stage: "Финал · первый тур",
      date: "23 марта 2026",
      description: "Заключительный этап ВсОШ по информатике, профиль «Искусственный интеллект».",
      taskCount: 6,
      tasks: [],
      participants: []
    }
  ],
  catalog: [
    {
      id: "math-cup-2026",
      series: "Math Cup",
      year: "2026",
      title: "Math Cup 2026",
      description: "Отборочный тур и финал объединены в один выпуск.",
      stages: ["Отбор · 8 задач", "Финал · 9 задач"],
      status: "Таблица открыта",
      competitionId: "math-cup-2026-final",
      accent: "dark"
    },
    {
      id: "math-cup-2025-spring",
      series: "Math Cup",
      year: "2025",
      title: "Math Cup 2025 · Весна",
      description: "Весенний финал в отдельном выпуске.",
      stages: ["Финал", "9 задач"],
      status: "Открыть",
      competitionId: "math-cup-2025-spring-final",
      accent: "dark"
    },
    {
      id: "math-cup-2025-winter",
      series: "Math Cup",
      year: "2025",
      title: "Math Cup 2025 · Зима",
      description: "Отборочный тур и финал показаны вместе.",
      stages: ["Отбор · 10 задач", "Финал · 8 задач"],
      status: "Открыть",
      competitionId: "math-cup-2025-winter-final",
      accent: "dark"
    },
    {
      id: "vsosh-ai-2026",
      series: "ВсОШ по ИИ",
      year: "2026",
      title: "ВсОШ по ИИ 2026",
      description: "Заключительный этап профиля «Искусственный интеллект».",
      stages: ["Финал · тур 1", "6 задач"],
      status: "Открыть",
      competitionId: "vsosh-ai-2026-round-1",
      accent: "dark"
    }
  ]
};

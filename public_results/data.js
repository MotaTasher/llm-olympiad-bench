window.RESULTS_DATA = {
  releases: [
    {
      id: "math-cup-2026-final",
      benchmarkId: "math-cup",
      series: "Math Cup",
      year: "2026",
      stageLabel: "Финал",
      title: "Math Cup 2026 · Финал",
      description: "Финальный этап Math Cup 2026.",
      competitionIds: ["math-cup-2026-final"]
    },
    {
      id: "math-cup-2026-qualifying",
      benchmarkId: "math-cup",
      series: "Math Cup",
      year: "2026",
      stageLabel: "Отбор",
      title: "Math Cup 2026 · Отбор",
      description: "Отборочный этап Math Cup 2026.",
      competitionIds: ["math-cup-2026-qualifying"]
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
      competitionRules: [
        "На финале команды решали задачи в течение трёхчасового устного тура и могли сделать до трёх попыток сдать каждую задачу.",
        "Каждая модель отвечает на задачу один раз, без инструментов, поиска и доступа к коду.",
        "Каждое решение независимо проверяют несколько экспертов. Совпавшие оценки за полное или неверное решение фиксируются автоматически; при расхождении или частичном балле эксперты обсуждают работу и согласуют итоговый вердикт. Такой итог сопровождается комментарием экспертов."
      ],
      taskCount: 9,
      scoreFormat: "percent",
      tasks: [
        { id: "task_01", short: "01", title: "Задача 1", maxScore: 2 },
        { id: "task_02", short: "02", title: "Задача 2", maxScore: 2 },
        { id: "task_03", short: "03", title: "Задача 3", maxScore: 2 },
        { id: "task_04", short: "04", title: "Задача 4", maxScore: 2 },
        { id: "task_05", short: "05", title: "Задача 5", maxScore: 2 },
        { id: "task_06", short: "06", title: "Задача 6", maxScore: 2 },
        { id: "task_07", short: "07", title: "Задача 7", maxScore: 2 },
        { id: "task_08", short: "08", title: "Строки", maxScore: 2 },
        { id: "task_09", short: "09", title: "Задача 9", maxScore: 2 }
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
          name: "Мысланты",
          members: "Алексей Львов, Иван Гайдай-Турлов, Максим Туревский",
          scores: [100, 100, 100, 100, 100, 0, 100, 100, 100],
          points: 800,
          accuracy: 88.9,
          prizeRub: 150000,
          prizeUsd: 1922.65,
          prizeRateRubPerUsd: 78.0172,
          prizeRateDate: "28.07.2026"
        },
        {
          id: "team-silver",
          type: "team",
          medal: "🥈",
          rank: 2,
          name: "придумайте что-нибудь, я устал придумывать названия",
          members: "Егор Сапрунов, Михаил Югов, Церен Французов",
          scores: [100, 100, 100, 0, 100, 0, 100, 100, 100],
          points: 700,
          accuracy: 77.8,
          prizeRub: 100000,
          prizeUsd: 1281.77,
          prizeRateRubPerUsd: 78.0172,
          prizeRateDate: "28.07.2026"
        },
        {
          id: "team-bronze",
          type: "team",
          medal: "🥉",
          rank: 3,
          name: "239 15-1",
          members: "Владимир Давидюк, Иван Бахарев, Таисия Коротченко",
          scores: [100, 100, 100, 0, 100, 0, 50, 50, 100],
          points: 600,
          accuracy: 66.7,
          prizeRub: 50000,
          prizeUsd: 640.88,
          prizeRateRubPerUsd: 78.0172,
          prizeRateDate: "28.07.2026"
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
      description: "Отборочный тур Math Cup 2026.",
      competitionRules: [
        "В задачах A–F участники сдавали только ответы. В задачах G и H — ответ и полное решение.",
        "Для моделей сохраняем тот же формат: в A–F проверяем ответ, в G и H — ответ вместе с решением. Каждая модель отвечает на задачу один раз, без инструментов, поиска и доступа к коду.",
        "Каждую работу независимо проверяют несколько экспертов. Совпавшие оценки за полный или нулевой балл фиксируются автоматически; при расхождении или частичном балле эксперты обсуждают работу и согласуют итоговый вердикт. Такой итог сопровождается комментарием экспертов."
      ],
      taskCount: 8,
      tasks: [
        { id: "task_01", short: "01", title: "Задача A", maxScore: 4 },
        { id: "task_02", short: "02", title: "Задача B", maxScore: 4 },
        { id: "task_03", short: "03", title: "Задача C", maxScore: 4 },
        { id: "task_04", short: "04", title: "Задача D", maxScore: 4 },
        { id: "task_05", short: "05", title: "Задача E", maxScore: 4 },
        { id: "task_06", short: "06", title: "Задача F", maxScore: 4 },
        { id: "task_07", short: "07", title: "Задача G · ответ + решение", maxScore: 4 },
        { id: "task_08", short: "08", title: "Задача H · ответ + решение", maxScore: 4 }
      ],
      participants: [
        {
          id: "qualifying-team-gold",
          type: "team",
          medal: "🥇",
          rank: 1,
          name: "Фанаты КСП",
          members: "Сергей Барсуков, Даниил Игнатьев, Антон Плюснин",
          scores: [4, 4, 4, 4, 4, 4, 1.5, 2],
          points: 27.5,
          accuracy: 85.9
        },
        {
          id: "qualifying-team-silver",
          type: "team",
          medal: "🥈",
          rank: 2,
          name: "ZigIsTheBestLanguage",
          members: "Надежда Осипова, Александр Мискин",
          scores: [0, 4, 4, 4, 4, 4, 4, 2],
          points: 26,
          accuracy: 81.3
        },
        {
          id: "qualifying-team-bronze",
          type: "team",
          medal: "🥉",
          rank: 3,
          name: "ФМШТО",
          members: "Герман Кузнецов, Алексей Янин, Георгий Киприянов",
          scores: [4, 1, 4, 4, 4, 4, 4, 0],
          points: 25,
          accuracy: 78.1
        }
      ]
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
      id: "math-cup-2026-final",
      series: "Math Cup",
      year: "2026",
      title: "Math Cup 2026",
      stageLabel: "Финал",
      taskLabel: "9 задач",
      competitionId: "math-cup-2026-final",
      accent: "dark"
    },
    {
      id: "math-cup-2026-qualifying",
      series: "Math Cup",
      year: "2026",
      title: "Math Cup 2026",
      stageLabel: "Отбор",
      taskLabel: "8 задач",
      competitionId: "math-cup-2026-qualifying",
      accent: "dark"
    }
  ]
};

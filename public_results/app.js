(function () {
  "use strict";

  const sourceBaselineData = window.RESULTS_DATA;
  const visibleBaselineModels = new Set([
    "GPT-5.6 Sol",
    "Claude Fable 5",
    "Claude Opus 5",
    "DeepSeek V4 Pro",
    "Gemini 3.1 Pro",
    "GigaChat 3 Ultra",
    "Grok 4.5",
    "GLM 5.2",
    "Alice AI LLM",
    "Kimi K3"
  ]);
  const baselineData = {
    ...sourceBaselineData,
    competitions: sourceBaselineData.competitions.map(normalizeBaselineCompetition)
  };
  const generatedData = window.RESULTS_DATA_GENERATED;
  const generatedCompetitions = new Map(
    (generatedData?.competitions || []).map((competition) => [competition.id, competition])
  );
  const competitions = baselineData.competitions.map((competition) => {
    const generated = generatedCompetitions.get(competition.id);
    if (!generated) return competition;
    const teams = competition.participants.filter((participant) => participant.type === "team");
    return {
      ...competition,
      ...generated,
      participants: [...generated.participants, ...teams]
    };
  });
  generatedCompetitions.forEach((competition, id) => {
    if (!competitions.some((item) => item.id === id)) competitions.push(competition);
  });
  const data = { ...baselineData, competitions };
  const page = document.body.dataset.page;
  const number = new Intl.NumberFormat("ru-RU");
  const sortByCompetition = new Map();
  const readingPreferencesKey = "reasoning-space:solution-sections:v1";
  let activeRelease = null;

  function siteBasePath() {
    const path = new URL(document.baseURI).pathname;
    return path.endsWith("/") ? path : `${path}/`;
  }

  function isLegacyDeployment() {
    return siteBasePath() !== "/";
  }

  function homeRoute(params = "") {
    return `${siteBasePath()}${isLegacyDeployment() ? "index.html" : ""}${params}`;
  }

  function catalogRoute() {
    return `${siteBasePath()}${isLegacyDeployment() ? "competitions.html" : "problems"}`;
  }

  function updateSiteLinks() {
    document.querySelectorAll('[data-site-link="home"]').forEach((link) => {
      link.href = homeRoute();
    });
    document.querySelectorAll('[data-site-link="catalog"]').forEach((link) => {
      link.href = catalogRoute();
    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function query() {
    return new URLSearchParams(window.location.search);
  }

  function cleanSolutionRoute() {
    const pathname = window.location.pathname.startsWith(siteBasePath())
      ? `/${window.location.pathname.slice(siteBasePath().length)}`
      : window.location.pathname;
    const match = pathname.match(
      /^\/problems\/([^/]+)\/([^/]+)\/([^/]+)\/?$/
    );
    if (!match) return null;
    return {
      competition: decodeURIComponent(match[1]),
      task: decodeURIComponent(match[2]),
      participant: decodeURIComponent(match[3])
    };
  }

  function cleanTaskRoute() {
    const pathname = window.location.pathname.startsWith(siteBasePath())
      ? `/${window.location.pathname.slice(siteBasePath().length)}`
      : window.location.pathname;
    const match = pathname.match(/^\/problems\/([^/]+)\/([^/]+)\/?$/);
    if (!match) return null;
    return {
      competition: decodeURIComponent(match[1]),
      task: decodeURIComponent(match[2])
    };
  }

  function taskRouteSlug(task) {
    if (task?.slug) return task.slug;
    const match = String(task?.id || "").match(/^task[_-]?0*(\d+)$/i);
    return match ? `task${Number(match[1])}` : String(task?.id || "task").toLowerCase();
  }

  function participantRouteSlug(participant) {
    if (participant?.slug) return participant.slug;
    let slug = String(participant?.id || "model").toLowerCase();
    const providerPrefixes = [
      "anthropic-", "deepseek-", "gigachat-", "google-", "openai-",
      "xai-", "yandexgpt-", "zai-", "kimi-"
    ];
    const prefix = providerPrefixes.find((candidate) => slug.startsWith(candidate));
    if (prefix) slug = slug.slice(prefix.length);
    return slug.endsWith("-sol") ? slug.slice(0, -4) : slug;
  }

  function solutionRoute(competition, participant, task) {
    if (isLegacyDeployment()) {
      const params = new URLSearchParams({
        competition: competition.id,
        participant: participant.id,
        task: task.id
      });
      return `${siteBasePath()}solution.html?${params}`;
    }
    return `/problems/${encodeURIComponent(competition.id)}/${encodeURIComponent(taskRouteSlug(task))}/${encodeURIComponent(participantRouteSlug(participant))}`;
  }

  function taskRoute(competition, task) {
    if (isLegacyDeployment()) {
      const params = new URLSearchParams({
        competition: competition.id,
        task: task.id
      });
      return `${siteBasePath()}task.html?${params}`;
    }
    return `/problems/${encodeURIComponent(competition.id)}/${encodeURIComponent(taskRouteSlug(task))}`;
  }

  function competitionById(id) {
    return data.competitions.find((competition) => competition.id === id);
  }

  function releaseById(id) {
    return data.releases.find((release) => release.id === id);
  }

  function releaseForCompetition(competitionId) {
    return data.releases.find((release) => release.competitionIds.includes(competitionId));
  }

  function normalizeBaselineCompetition(competition) {
    if (competition.scoreFormat !== "percent") return competition;
    const participants = competition.participants
      .filter((participant) => participant.type === "team" || visibleBaselineModels.has(participant.name))
      .map((participant) => {
        const scores = (participant.scores || []).map((score, index) => {
          if (score === null || score === undefined) return score;
          const maxScore = Number(competition.tasks[index]?.maxScore || 100);
          return Math.round((Number(score) / 100 * maxScore) * 10) / 10;
        });
        const numericScores = scores.filter((score) => typeof score === "number");
        return {
          ...participant,
          scores,
          points: numericScores.length
            ? numericScores.reduce((total, score) => total + score, 0)
            : null
        };
      });
    return { ...competition, participants };
  }

  function scoreClass(score, maxScore) {
    if (score === null || score === undefined) return "score-empty";
    if (score === 0) return "score-zero";
    if (score >= maxScore) return "score-full";
    return "score-partial";
  }

  function scoreText(score) {
    return score === null || score === undefined ? "—" : `${score}`;
  }

  function renderSolutionResult(score, maxScore, verdict) {
    const resultClass = scoreClass(score, maxScore);
    const scoreLabel = score == null ? "На проверке" : `${score} / ${maxScore}`;
    document.querySelectorAll("[data-solution-score]").forEach((element) => {
      element.textContent = scoreLabel;
    });
    document.querySelectorAll("[data-solution-verdict]").forEach((element) => {
      element.textContent = verdict;
    });
    document.querySelectorAll(".solution-result-badge").forEach((element) => {
      element.classList.remove("score-full", "score-partial", "score-zero", "score-empty");
      element.classList.add(resultClass);
    });
    document.body.dataset.resultState = resultClass.replace("score-", "");
  }

  function readReadingPreferences() {
    try {
      const value = JSON.parse(window.localStorage.getItem(readingPreferencesKey) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (_) {
      return {};
    }
  }

  function rememberReadingPreferences() {
    const preferences = readReadingPreferences();
    document.querySelectorAll("details[data-reading-section]").forEach((details) => {
      preferences[details.dataset.readingSection] = details.open;
    });
    try {
      window.localStorage.setItem(readingPreferencesKey, JSON.stringify(preferences));
    } catch (_) {
      // Private browsing or a storage policy may disable persistence.
    }
  }

  function restoreReadingPreferences(root = document) {
    const preferences = readReadingPreferences();
    root.querySelectorAll("details[data-reading-section]").forEach((details) => {
      const remembered = preferences[details.dataset.readingSection];
      if (typeof remembered === "boolean") details.open = remembered;
      if (details.dataset.readingPreferenceReady !== "true") {
        details.addEventListener("toggle", rememberReadingPreferences);
        details.dataset.readingPreferenceReady = "true";
      }
    });
  }

  function protectMath(source) {
    const chunks = [];
    const pattern = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\))/g;
    const protectedSource = source.replace(pattern, (match) => {
      const token = `@@MATH_${chunks.length}@@`;
      chunks.push(match);
      return token;
    });
    return { protectedSource, chunks };
  }

  function restoreMath(html, chunks) {
    return html.replace(/@@MATH_(\d+)@@/g, (_, index) =>
      escapeHtml(chunks[Number(index)] || "")
    );
  }

  function renderMarkdown(value, emptyText) {
    const source = String(value || "").trim();
    if (!source) return `<p>${escapeHtml(emptyText)}</p>`;
    const { protectedSource, chunks } = protectMath(source);
    const canRenderSafely = Boolean(window.marked && window.DOMPurify);
    const rendered = canRenderSafely
      ? window.marked.parse(protectedSource, { gfm: true, breaks: true })
      : `<p class="preformatted">${escapeHtml(protectedSource)}</p>`;
    const sanitized = canRenderSafely
      ? window.DOMPurify.sanitize(rendered)
      : rendered;
    return restoreMath(sanitized, chunks);
  }

  function renderMathInNode(node) {
    if (!window.renderMathInElement) return;
    try {
      window.renderMathInElement(node, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false }
        ],
        throwOnError: false
      });
      // KaTeX composes negated relations from a private-use slash glyph. Some
      // bundled/browser font combinations render that glyph as a missing-glyph
      // box, so replace only that internal overlay with a regular slash.
      node.querySelectorAll(".katex .rlap .inner .mrel").forEach((symbol) => {
        if (symbol.textContent === "\uE020") {
          symbol.textContent = "/";
          symbol.classList.add("math-negation-slash");
        }
      });
    } catch (_) {
      // Keep readable Markdown if one malformed formula cannot be rendered.
    }
  }

  function renderMarkdownInto(selector, value, emptyText) {
    const node = document.querySelector(selector);
    node.innerHTML = renderMarkdown(value, emptyText);
    renderMathInNode(node);
  }

  function renderFinalReview(review) {
    const section = document.querySelector("#expert-review-section");
    const container = document.querySelector("#expert-reviews");
    if (!section || !container) return;
    const feedback = String(review?.final?.feedback || "").trim();
    container.innerHTML = feedback
      ? `<article class="expert-review-card final"><div class="expert-review-copy prose">${renderMarkdown(feedback, "")}</div></article>`
      : "";
    section.hidden = !feedback;
    if (feedback) renderMathInNode(container);
  }

  function renderLeaderboard() {
    const requestedRelease = releaseById(query().get("release"));
    const legacyCompetition = competitionById(query().get("competition"));
    const initialRelease = requestedRelease
      || releaseForCompetition(legacyCompetition?.id)
      || data.releases[0];
    activeRelease = initialRelease;
    renderReleasePicker(initialRelease.id);
    renderRelease(initialRelease);
    document.querySelector("#competition-filters").addEventListener("click", (event) => {
      const link = event.target.closest("[data-release]");
      if (!link) return;
      event.preventDefault();
      const release = releaseById(link.dataset.release);
      if (!release) return;
      activeRelease = release;
      renderReleasePicker(release.id);
      renderRelease(release);
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("competition", release.competitionIds[0]);
      history.replaceState({}, "", url);
    });
    document.querySelector("#stage-stack").addEventListener("click", (event) => {
      const button = event.target.closest("[data-sort]");
      if (!button) return;
      const competitionId = button.dataset.competition;
      const key = button.dataset.sort;
      const current = sortState(competitionId);
      const defaultDirection = key === "name" || key === "rank" ? "asc" : "desc";
      sortByCompetition.set(competitionId, {
        key,
        direction: current.key === key
          ? (current.direction === "asc" ? "desc" : "asc")
          : defaultDirection
      });
      renderRelease(activeRelease);
    });
  }

  function renderReleasePicker(selectedId) {
    const selected = releaseById(selectedId) || data.releases[0];
    const benchmarkIds = [...new Set(data.releases.map((release) => release.benchmarkId))];
    const benchmarks = benchmarkIds.map((benchmarkId) => {
      const matching = data.releases.filter((release) => release.benchmarkId === benchmarkId);
      const target = matching.find((release) =>
        release.year === selected.year && release.stageLabel === selected.stageLabel
      ) || matching.find((release) => release.year === selected.year) || matching[0];
      return {
        label: matching[0].series,
        release: target,
        active: benchmarkId === selected.benchmarkId
      };
    });
    const years = [...new Set(
      data.releases
        .filter((release) => release.benchmarkId === selected.benchmarkId)
        .map((release) => release.year)
    )].map((year) => {
      const matching = data.releases.filter((release) =>
        release.benchmarkId === selected.benchmarkId && release.year === year
      );
      return {
        label: year,
        release: matching.find((release) => release.stageLabel === selected.stageLabel) || matching[0],
        active: year === selected.year
      };
    });
    const stages = data.releases
      .filter((release) =>
        release.benchmarkId === selected.benchmarkId && release.year === selected.year
      )
      .sort((left, right) => {
        const order = { "Отбор": 0, "Финал": 1 };
        return (order[left.stageLabel] ?? 10) - (order[right.stageLabel] ?? 10);
      })
      .map((release) => ({
        label: release.stageLabel,
        release,
        active: release.id === selected.id
      }));

    const row = (label, options) => `
      <div class="filter-row">
        <span class="filter-label">${escapeHtml(label)}</span>
        <div class="filter-options">
          ${options.map((option) => `
            <a class="filter-chip${option.active ? " active" : ""}"
               href="${homeRoute(`?competition=${encodeURIComponent(option.release.competitionIds[0])}`)}"
               data-release="${escapeHtml(option.release.id)}"
               ${option.active ? 'aria-current="true"' : ""}>
              ${escapeHtml(option.label)}
            </a>
          `).join("")}
        </div>
      </div>
    `;
    document.querySelector("#competition-filters").innerHTML = [
      row("Бенчмарк", benchmarks),
      row("Год", years),
      row("Этап", stages)
    ].join("");
  }

  function renderRelease(release) {
    document.title = `${release.title} — Reasoning Space`;
    const selectedCompetitions = release.competitionIds
      .map(competitionById)
      .filter(Boolean);
    document.querySelector("#stage-stack").innerHTML = selectedCompetitions
      .map(renderStage)
      .join("");
    renderCompetitionRules(selectedCompetitions[0]);
  }

  function renderCompetitionRules(competition) {
    const list = document.querySelector("#competition-rules");
    if (!list) return;
    const rules = competition?.competitionRules || [
      "Для этого набора действуют те же требования к ответам моделей, что и к работам участников.",
      "Каждая модель отвечает на задачу один раз."
    ];
    list.innerHTML = rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("");
  }

  function renderStage(competition) {
    const modelCount = competition.participants.filter((item) => item.type === "model").length;
    const teamCount = competition.participants.filter((item) => item.type === "team").length;
    const hasResults = competition.tasks.length && competition.participants.length;
    const content = hasResults
      ? `
        <div class="leaderboard-meta">
          <span>${competition.tasks.length} задач · ${modelCount} моделей${teamCount ? " · топ-3 команды" : ""}</span>
          <span>Нажмите на ячейку модели, чтобы открыть ответ</span>
        </div>
        <div class="matrix-shell">
          <div class="matrix-scroll" tabindex="0" aria-label="${escapeHtml(competition.stage)}: таблица результатов">
            ${matrixMarkup(competition)}
          </div>
        </div>
      `
      : `
        <div class="empty-state">
          <p class="eyebrow">Данные готовятся</p>
          <h3>${competition.taskCount} задач уже заведены</h3>
          <p>Этап остаётся видимым в составе выпуска. Матрица появится здесь после публикации результатов проверки.</p>
        </div>
      `;

    return `
      <article class="stage-block">
        <header class="stage-heading">
          <div>
            <p class="eyebrow">${escapeHtml(competition.date)}</p>
            <h3>${escapeHtml(competition.stage)}</h3>
          </div>
          <p>${escapeHtml(competition.description)}</p>
        </header>
        ${content}
      </article>
    `;
  }

  function matrixMarkup(competition) {
    const state = sortState(competition.id);
    const sortableHeader = (key, label, className, title = "") => {
      const active = state.key === key;
      const arrow = active ? (state.direction === "asc" ? "↑" : "↓") : "↕";
      const ariaSort = active
        ? ` aria-sort="${state.direction === "asc" ? "ascending" : "descending"}"`
        : "";
      return `
        <th class="${className}" scope="col"${ariaSort}${title ? ` title="${escapeHtml(title)}"` : ""}>
          <button class="sort-button${active ? " active" : ""}" type="button"
                  data-sort="${escapeHtml(key)}"
                  data-competition="${escapeHtml(competition.id)}">
            <span>${escapeHtml(label)}</span><b aria-hidden="true">${arrow}</b>
          </button>
        </th>
      `;
    };
    const head = `
      <thead>
        <tr>
          ${sortableHeader("rank", "#", "rank-column")}
          ${sortableHeader("name", "Модель / команда", "participant-column")}
          ${sortableHeader("cost", "Затраты", "metric-column")}
          ${sortableHeader("points", "Сумма", "metric-column")}
          ${sortableHeader("tokens", "Токены", "metric-column")}
          ${sortableHeader("accuracy", "Точность", "metric-column")}
          ${competition.tasks.map((task) => `
            <th class="task-column" scope="col" title="${escapeHtml(task.title)} · максимум ${task.maxScore} балла">
              <a class="task-header-link" href="${taskRoute(competition, task)}" aria-label="Открыть все решения: ${escapeHtml(task.title)}">
                ${escapeHtml(task.short)}
              </a>
            </th>
          `).join("")}
        </tr>
      </thead>
    `;

    const participants = competition.participants.filter(
      (item) => item.type === "model" || item.type === "team"
    );
    const ranks = rankingFor(participants);
    const rows = [...participants].sort((left, right) =>
      compareParticipants(left, right, state, ranks)
    );

    const body = rows.map((participant) => {
      const isTeam = participant.type === "team";
      // Номер общего рейтинга стоит у всех строк; медаль команды переехала
      // к названию, иначе в одном столбце соседствуют номер и значок.
      const rank = String(ranks.get(participant.id)).padStart(2, "0");
      const medal = isTeam
        ? `<span class="medal" aria-label="${participant.rank} место в олимпиаде" title="${participant.rank} место в олимпиаде">${participant.medal}</span>`
        : "";

      const cells = competition.tasks.map((task, index) => {
        const score = participant.scores[index];
        const solution = participant.solutions?.[index];
        const content = !isTeam && score == null && solution
          ? '<span class="review-status">На<br>проверке</span>'
          : `<span>${scoreText(score)}</span>`;
        if (isTeam || !solution) {
          return `<td class="result-cell ${scoreClass(score, task.maxScore)}">${content}</td>`;
        }
        const href = solutionRoute(competition, participant, task);
        const label = score == null ? "ответ на проверке" : `${score} баллов`;
        return `<td class="result-cell ${scoreClass(score, task.maxScore)}"><a href="${href}" aria-label="${escapeHtml(participant.name)}, ${escapeHtml(task.title)}: ${label}">${content}</a></td>`;
      }).join("");

      return `
        <tr class="${isTeam ? "team-row" : "model-row"}">
          <td class="rank-cell">${rank}</td>
          <th class="participant-cell" scope="row">
            <span class="participant-title">
              ${medal}
              <span class="participant-name" title="${escapeHtml(participant.name)}">${escapeHtml(participant.name)}</span>
            </span>
            ${isTeam ? `<span class="participant-meta" title="${escapeHtml(participant.members)}">${escapeHtml(participant.members)}</span>` : ""}
          </th>
          ${moneyCell(participant)}
          <td class="metric-cell strong">${formatPoints(participantPoints(participant))}</td>
          <td class="metric-cell">${participant.tokens == null ? "—" : number.format(participant.tokens)}</td>
          <td class="metric-cell strong">${participant.accuracy == null ? "—" : `${String(participant.accuracy).replace(".", ",")}%`}</td>
          ${cells}
        </tr>
      `;
    }).join("");

    return `<table class="leaderboard-table">${head}<tbody>${body}</tbody></table>`;
  }

  function sortState(competitionId) {
    return sortByCompetition.get(competitionId) || { key: "points", direction: "desc" };
  }

  function participantPoints(participant) {
    if (typeof participant.points === "number") return participant.points;
    const scores = (participant.scores || []).filter((score) => typeof score === "number");
    return scores.length ? scores.reduce((total, score) => total + score, 0) : null;
  }

  function formatPoints(value) {
    if (value === null || value === undefined) return "—";
    return Number.isInteger(value) ? number.format(value) : String(value).replace(".", ",");
  }

  function participantMoney(participant) {
    return participant.type === "team" ? participant.prizeUsd : participant.cost;
  }

  function moneyCell(participant) {
    const value = participantMoney(participant);
    if (value === null || value === undefined) return `<td class="metric-cell">—</td>`;
    if (participant.type !== "team") {
      return `<td class="metric-cell" title="Затраты модели">$${value.toFixed(2)}</td>`;
    }
    const rubles = number.format(participant.prizeRub);
    const title = `Призовые: ${rubles} ₽ · курс ${String(participant.prizeRateRubPerUsd).replace(".", ",")} ₽/$ на ${participant.prizeRateDate}`;
    return `<td class="metric-cell prize-cell" title="${escapeHtml(title)}"><span>$${value.toFixed(2)}</span><small>призовые</small></td>`;
  }

  function rankingFor(participants) {
    const ordered = [...participants].sort((left, right) => {
      const pointsDifference = (participantPoints(right) ?? -1) - (participantPoints(left) ?? -1);
      if (pointsDifference) return pointsDifference;
      const accuracyDifference = (right.accuracy ?? -1) - (left.accuracy ?? -1);
      if (accuracyDifference) return accuracyDifference;
      return left.name.localeCompare(right.name, "ru");
    });
    return new Map(ordered.map((participant, index) => [participant.id, index + 1]));
  }

  function sortValue(participant, key, ranks) {
    if (key === "rank") return ranks.get(participant.id);
    if (key === "name") return participant.name;
    if (key === "points") return participantPoints(participant);
    if (key === "accuracy") return participant.accuracy;
    if (key === "cost") return participantMoney(participant);
    if (key === "tokens") return participant.tokens;
    if (key.startsWith("task:")) {
      return participant.scores?.[Number(key.split(":")[1])];
    }
    return null;
  }

  function compareParticipants(left, right, state, ranks) {
    const leftValue = sortValue(left, state.key, ranks);
    const rightValue = sortValue(right, state.key, ranks);
    const leftMissing = leftValue === null || leftValue === undefined;
    const rightMissing = rightValue === null || rightValue === undefined;
    // Равные значения разводим общим рейтингом, а не алфавитом: иначе номера
    // в столбце «#» идут вразнобой (04, 06, 05) при сортировке по сумме.
    const byRank = (ranks.get(left.id) ?? 0) - (ranks.get(right.id) ?? 0);
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    if (leftMissing) return byRank;
    let comparison;
    if (typeof leftValue === "string") {
      comparison = leftValue.localeCompare(rightValue, "ru");
    } else {
      comparison = leftValue - rightValue;
    }
    if (comparison === 0) return byRank;
    return state.direction === "asc" ? comparison : -comparison;
  }

  function renderCatalog() {
    const grid = document.querySelector("#competition-grid");
    grid.innerHTML = data.catalog.map((item) => {
      const href = homeRoute(`?competition=${encodeURIComponent(item.competitionId)}`);
      const stages = item.stages.map((stage) => `<span>${escapeHtml(stage)}</span>`).join("");
      return `
        <a class="competition-card" href="${href}">
          <div class="competition-card-top">
            <span>${escapeHtml(item.series)}</span>
            <span>${escapeHtml(item.year)}</span>
          </div>
          <div class="competition-card-body">
            <h2>${escapeHtml(item.title)}</h2>
            <p>${escapeHtml(item.description)}</p>
          </div>
          <div class="competition-card-bottom">
            <div>${stages}</div>
            <strong>${escapeHtml(item.status)} <span aria-hidden="true">↗</span></strong>
          </div>
        </a>
      `;
    }).join("");
  }

  async function renderSolution() {
    restoreReadingPreferences();
    const params = query();
    const route = cleanSolutionRoute();
    const competitionId = route?.competition || params.get("competition");
    const participantId = route?.participant || params.get("participant");
    const taskId = route?.task || params.get("task");
    const competition = competitionById(competitionId) || data.competitions[0];
    const participant = competition.participants.find(
      (item) => item.id === participantId || participantRouteSlug(item) === participantId
    )
      || competition.participants.find((item) => item.type === "model");
    const taskIndex = competition.tasks.findIndex(
      (item) => item.id === taskId || taskRouteSlug(item) === taskId
    );
    const safeTaskIndex = taskIndex >= 0 ? taskIndex : 0;
    const task = competition.tasks[safeTaskIndex];
    const score = participant?.scores?.[safeTaskIndex];
    const maxScore = Number(task?.maxScore || 0);
    const solutionPath = participant?.solutions?.[safeTaskIndex];
    const release = releaseForCompetition(competition.id);
    const back = homeRoute(`?release=${encodeURIComponent(release?.id || data.releases[0].id)}`);

    document.querySelector("#solution-back").href = back;
    document.querySelector("#solution-competition").textContent = `${competition.title} · ${competition.stage}`;
    document.querySelector("#solution-task").textContent = task?.title || "Задача";
    document.querySelector("#solution-model").textContent = participant?.name || "Модель";
    const initialVerdict = score == null
      ? "На проверке"
      : score >= maxScore ? "Полное решение" : score > 0 ? "Частичное решение" : "Не зачтено";
    renderSolutionResult(score, maxScore, initialVerdict);
    document.querySelector("#solution-cost").textContent = "—";
    document.querySelector("#solution-tokens").textContent = "—";
    document.querySelector("#solution-text").innerHTML = "<p>Загружаем ответ…</p>";
    document.querySelector("#solution-statement").innerHTML = "<p>Загружаем условие…</p>";
    document.querySelector("#official-solution-text").innerHTML = "<p>Загружаем авторское решение…</p>";
    renderFinalReview(null);
    if (!solutionPath) {
      document.querySelector("#solution-text").innerHTML = "<p>Для этой ячейки нет опубликованного ответа.</p>";
      document.querySelector("#solution-statement").innerHTML = "<p>Условие недоступно.</p>";
      document.querySelector("#official-solution-text").innerHTML = "<p>Авторское решение недоступно.</p>";
      return;
    }

    try {
      const response = await fetch(
        `${siteBasePath()}${solutionPath.replace(/^\/+/, "")}`,
        { cache: "no-store" }
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const documentData = await response.json();
      const result = documentData.result || {};
      const documentMaxScore = Number(documentData.task?.maxScore || maxScore);
      const competitionTitle = documentData.competition?.title || competition.title;
      const competitionStage = documentData.competition?.stage || competition.stage;
      document.querySelector("#solution-competition").textContent =
        competitionStage && !competitionTitle.toLocaleLowerCase("ru").includes(competitionStage.toLocaleLowerCase("ru"))
          ? `${competitionTitle} · ${competitionStage}`
          : competitionTitle;
      document.querySelector("#solution-task").textContent = documentData.task?.title || task?.title || "Задача";
      document.querySelector("#solution-model").textContent = documentData.model?.name || participant?.name || "Модель";
      renderSolutionResult(
        result.score,
        documentMaxScore,
        result.verdict || (result.score == null ? "На проверке" : "Нет публичной оценки")
      );
      document.querySelector("#solution-cost").textContent =
        result.cost == null ? "—" : `$${Number(result.cost).toFixed(4)}`;
      document.querySelector("#solution-tokens").textContent =
        result.tokens == null ? "—" : number.format(result.tokens);
      renderFinalReview(documentData.review);
      renderMarkdownInto(
        "#solution-statement",
        documentData.task?.statement,
        "Условие задачи не опубликовано."
      );
      renderMarkdownInto("#solution-text", result.answer, "Текст ответа пуст.");
      renderMarkdownInto(
        "#official-solution-text",
        documentData.task?.officialSolution,
        "Авторское решение не опубликовано."
      );
    } catch (error) {
      document.querySelector("#solution-text").innerHTML =
        "<p>Не удалось загрузить опубликованный ответ. Попробуйте обновить страницу.</p>";
      document.querySelector("#solution-statement").innerHTML =
        "<p>Условие задачи временно недоступно.</p>";
      document.querySelector("#official-solution-text").innerHTML =
        "<p>Авторское решение временно недоступно.</p>";
    }
  }

  function taskVerdict(score, maxScore) {
    if (score == null) return "На проверке";
    if (score >= maxScore) return "Полное решение";
    if (score > 0) return "Частичное решение";
    return "Не зачтено";
  }

  async function fetchPublishedSolution(path) {
    if (!path) return null;
    const response = await fetch(
      `${siteBasePath()}${path.replace(/^\/+/, "")}`,
      { cache: "no-store" }
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function renderTask() {
    const params = query();
    const route = cleanTaskRoute();
    const competitionId = route?.competition || params.get("competition");
    const taskId = route?.task || params.get("task");
    const competition = competitionById(competitionId) || data.competitions[0];
    const taskIndex = competition.tasks.findIndex(
      (item) => item.id === taskId || taskRouteSlug(item) === taskId
    );
    const safeTaskIndex = taskIndex >= 0 ? taskIndex : 0;
    const task = competition.tasks[safeTaskIndex];
    const models = competition.participants.filter((item) => item.type === "model");
    const release = releaseForCompetition(competition.id);
    document.title = `${task?.title || "Задача"} — Reasoning Space`;
    document.querySelector("#task-back").href = homeRoute(
      `?release=${encodeURIComponent(release?.id || data.releases[0].id)}`
    );
    document.querySelector("#task-competition").textContent = `${competition.title} · ${competition.stage}`;
    document.querySelector("#task-title").textContent = task?.title || "Задача";

    const list = document.querySelector("#task-model-solutions");
    list.innerHTML = models.map((model) => {
      const score = model.scores?.[safeTaskIndex];
      const maxScore = Number(task?.maxScore || 0);
      const state = scoreClass(score, maxScore);
      return `
        <details class="reading-solution task-model-solution ${state}"
                 data-reading-section="model:${escapeHtml(participantRouteSlug(model))}"
                 data-model-id="${escapeHtml(model.id)}">
          <summary>
            <span><small>Решение модели</small>${escapeHtml(model.name)}</span>
            <span class="task-model-summary-result">
              <em class="task-verdict ${state}">${escapeHtml(taskVerdict(score, maxScore))} · ${score == null ? "—" : escapeHtml(`${score} / ${maxScore}`)}</em>
              <b aria-hidden="true">+</b>
            </span>
          </summary>
          <div class="task-model-body">
            <div class="prose" data-task-answer><p>Загружаем ответ…</p></div>
            <div class="task-final-comment" data-task-comment hidden></div>
          </div>
        </details>
      `;
    }).join("");
    restoreReadingPreferences(document);

    const firstPath = models.map((model) => model.solutions?.[safeTaskIndex]).find(Boolean);
    try {
      const firstDocument = await fetchPublishedSolution(firstPath);
      renderMarkdownInto("#task-statement", firstDocument?.task?.statement, "Условие задачи не опубликовано.");
      renderMarkdownInto("#task-official", firstDocument?.task?.officialSolution, "Авторское решение не опубликовано.");
    } catch (_) {
      renderMarkdownInto("#task-statement", "", "Условие задачи временно недоступно.");
      renderMarkdownInto("#task-official", "", "Авторское решение временно недоступно.");
    }

    await Promise.all(models.map(async (model) => {
      const card = list.querySelector(`[data-model-id="${CSS.escape(model.id)}"]`);
      const answer = card?.querySelector("[data-task-answer]");
      if (!answer) return;
      try {
        const documentData = await fetchPublishedSolution(model.solutions?.[safeTaskIndex]);
        if (!documentData) {
          answer.innerHTML = "<p>Для этой модели нет опубликованного ответа.</p>";
          return;
        }
        answer.innerHTML = renderMarkdown(documentData.result?.answer, "Текст ответа пуст.");
        renderMathInNode(answer);
        const feedback = String(documentData.review?.final?.feedback || "").trim();
        const comment = card.querySelector("[data-task-comment]");
        if (feedback && comment) {
          comment.hidden = false;
          comment.innerHTML = `<p class="eyebrow">Комментарий экспертов</p><div class="prose">${renderMarkdown(feedback, "")}</div>`;
          renderMathInNode(comment);
        }
      } catch (_) {
        answer.innerHTML = "<p>Не удалось загрузить опубликованный ответ.</p>";
      }
    }));
  }

  updateSiteLinks();
  if (page === "leaderboard") renderLeaderboard();
  if (page === "competitions") renderCatalog();
  if (page === "solution") renderSolution();
  if (page === "task") renderTask();
})();

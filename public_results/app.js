(function () {
  "use strict";

  const baselineData = window.RESULTS_DATA;
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
  let activeRelease = null;

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

  function competitionById(id) {
    return data.competitions.find((competition) => competition.id === id);
  }

  function releaseById(id) {
    return data.releases.find((release) => release.id === id);
  }

  function releaseForCompetition(competitionId) {
    return data.releases.find((release) => release.competitionIds.includes(competitionId));
  }

  function scoreClass(score) {
    if (score === null || score === undefined) return "score-empty";
    if (score === 0) return "score-zero";
    if (score >= 100) return "score-full";
    return "score-partial";
  }

  function scoreText(score) {
    return score === null || score === undefined ? "—" : `${score}`;
  }

  function renderPlainText(value, emptyText) {
    const text = String(value || "").trim();
    if (!text) return `<p>${escapeHtml(emptyText)}</p>`;
    return `<p class="preformatted">${escapeHtml(text)}</p>`;
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
    document.querySelector("#release-tabs").addEventListener("click", (event) => {
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
      url.searchParams.set("release", release.id);
      history.replaceState({}, "", url);
      window.scrollTo({ top: 0, behavior: "smooth" });
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
    const tabs = document.querySelector("#release-tabs");
    tabs.innerHTML = data.releases.map((release) => `
      <a class="release-tab${release.id === selectedId ? " active" : ""}"
         href="index.html?release=${encodeURIComponent(release.id)}"
         data-release="${escapeHtml(release.id)}"
         ${release.id === selectedId ? 'aria-current="page"' : ""}>
        <span>${escapeHtml(release.series)}</span>
        <strong>${escapeHtml(release.shortTitle)}</strong>
        <small>${release.competitionIds.length} ${release.competitionIds.length === 1 ? "этап" : "этапа"}</small>
      </a>
    `).join("");

  }

  function renderRelease(release) {
    document.querySelector("#release-title").textContent = release.title;
    document.querySelector("#release-kicker").textContent = `${release.series} · ${release.year}`;
    document.querySelector("#release-description").textContent = release.description;
    document.title = `${release.title} — CS Space Arena`;

    const competitions = release.competitionIds
      .map(competitionById)
      .filter(Boolean);
    document.querySelector("#stage-stack").innerHTML = competitions
      .map(renderStage)
      .join("");
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
          ${competition.tasks.map((task, index) => sortableHeader(`task:${index}`, task.short, "task-column", task.title)).join("")}
          ${sortableHeader("points", "Баллы", "metric-column")}
          ${sortableHeader("accuracy", "Точность", "metric-column")}
          ${sortableHeader("cost", "Деньги", "metric-column")}
          ${sortableHeader("tokens", "Токены", "metric-column")}
        </tr>
      </thead>
    `;

    const unsortedModels = competition.participants.filter((item) => item.type === "model");
    const ranks = rankingFor(unsortedModels);
    const modelRows = [...unsortedModels].sort((left, right) =>
      compareParticipants(left, right, state, ranks)
    );
    const teamRows = competition.participants.filter((item) => item.type === "team");
    const rows = teamRows.length
      ? [...modelRows, { type: "separator" }, ...teamRows]
      : modelRows;

    const body = rows.map((participant) => {
      if (participant.type === "separator") {
        return `<tr class="section-row"><th colspan="${competition.tasks.length + 6}">Топ-3 человеческие команды</th></tr>`;
      }
      const isTeam = participant.type === "team";
      const participantMeta = isTeam
        ? participant.members
        : participant.provider;
      const rank = isTeam
        ? `<span class="medal" aria-label="${participant.rank} место">${participant.medal}</span>`
        : String(ranks.get(participant.id)).padStart(2, "0");

      const cells = competition.tasks.map((task, index) => {
        const score = participant.scores[index];
        const solution = participant.solutions?.[index];
        const content = `<span>${scoreText(score)}</span>`;
        if (isTeam || !solution) {
          return `<td class="result-cell ${scoreClass(score)}">${content}</td>`;
        }
        const href = `solution.html?competition=${encodeURIComponent(competition.id)}&participant=${encodeURIComponent(participant.id)}&task=${encodeURIComponent(task.id)}`;
        const label = score == null ? "ответ без публичной оценки" : `${score} баллов`;
        return `<td class="result-cell ${scoreClass(score)}"><a href="${href}" aria-label="${escapeHtml(participant.name)}, ${escapeHtml(task.title)}: ${label}">${content}</a></td>`;
      }).join("");

      return `
        <tr class="${isTeam ? "team-row" : "model-row"}">
          <td class="rank-cell">${rank}</td>
          <th class="participant-cell" scope="row">
            <span class="participant-name">${escapeHtml(participant.name)}</span>
            <span class="participant-meta">${escapeHtml(participantMeta)}</span>
          </th>
          ${cells}
          <td class="metric-cell strong">${formatPoints(participantPoints(participant))}</td>
          <td class="metric-cell strong">${participant.accuracy == null ? "—" : `${String(participant.accuracy).replace(".", ",")}%`}</td>
          <td class="metric-cell">${participant.cost == null ? "—" : `$${participant.cost.toFixed(2)}`}</td>
          <td class="metric-cell">${participant.tokens == null ? "—" : number.format(participant.tokens)}</td>
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
    if (key === "cost") return participant.cost;
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
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    if (leftMissing) return left.name.localeCompare(right.name, "ru");
    let comparison;
    if (typeof leftValue === "string") {
      comparison = leftValue.localeCompare(rightValue, "ru");
    } else {
      comparison = leftValue - rightValue;
    }
    if (comparison === 0) return left.name.localeCompare(right.name, "ru");
    return state.direction === "asc" ? comparison : -comparison;
  }

  function renderCatalog() {
    const grid = document.querySelector("#competition-grid");
    grid.innerHTML = data.catalog.map((item) => {
      const href = `index.html?release=${encodeURIComponent(item.id)}`;
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
    const params = query();
    const competition = competitionById(params.get("competition")) || data.competitions[0];
    const participant = competition.participants.find((item) => item.id === params.get("participant"))
      || competition.participants.find((item) => item.type === "model");
    const taskIndex = competition.tasks.findIndex((item) => item.id === params.get("task"));
    const safeTaskIndex = taskIndex >= 0 ? taskIndex : 0;
    const task = competition.tasks[safeTaskIndex];
    const score = participant?.scores?.[safeTaskIndex];
    const solutionPath = participant?.solutions?.[safeTaskIndex];
    const release = releaseForCompetition(competition.id);
    const back = `index.html?release=${encodeURIComponent(release?.id || data.releases[0].id)}`;

    document.querySelector("#solution-back").href = back;
    document.querySelector("#solution-footer-back").href = back;
    document.querySelector("#solution-competition").textContent = `${competition.title} · ${competition.stage}`;
    document.querySelector("#solution-task").textContent = task?.title || "Задача";
    document.querySelector("#solution-model").textContent = participant?.name || "Модель";
    document.querySelector("#solution-score").textContent = score == null ? "—" : `${score} / 100`;
    document.querySelector("#solution-verdict").textContent = score == null
      ? "Нет оценки"
      : score >= 100 ? "Полное решение" : score > 0 ? "Частичное решение" : "Не зачтено";
    document.querySelector("#solution-cost").textContent = "—";
    document.querySelector("#solution-tokens").textContent = "—";
    document.querySelector("#solution-text").innerHTML = "<p>Загружаем ответ…</p>";
    document.querySelector("#official-solution-text").innerHTML = "<p>Загружаем авторское решение…</p>";

    if (!solutionPath) {
      document.querySelector("#solution-text").innerHTML = "<p>Для этой ячейки нет опубликованного ответа.</p>";
      document.querySelector("#official-solution-text").innerHTML = "<p>Авторское решение недоступно.</p>";
      return;
    }

    try {
      const response = await fetch(solutionPath, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const documentData = await response.json();
      const result = documentData.result || {};
      const competitionTitle = documentData.competition?.title || competition.title;
      const competitionStage = documentData.competition?.stage || competition.stage;
      document.querySelector("#solution-competition").textContent =
        competitionStage && !competitionTitle.toLocaleLowerCase("ru").includes(competitionStage.toLocaleLowerCase("ru"))
          ? `${competitionTitle} · ${competitionStage}`
          : competitionTitle;
      document.querySelector("#solution-task").textContent = documentData.task?.title || task?.title || "Задача";
      document.querySelector("#solution-model").textContent = documentData.model?.name || participant?.name || "Модель";
      document.querySelector("#solution-score").textContent = result.score == null ? "—" : `${result.score} / 100`;
      document.querySelector("#solution-verdict").textContent = result.verdict || "Нет публичной оценки";
      document.querySelector("#solution-cost").textContent =
        result.cost == null ? "—" : `$${Number(result.cost).toFixed(4)}`;
      document.querySelector("#solution-tokens").textContent =
        result.tokens == null ? "—" : number.format(result.tokens);
      document.querySelector("#solution-text").innerHTML =
        renderPlainText(result.answer, "Текст ответа пуст.");
      document.querySelector("#official-solution-text").innerHTML =
        renderPlainText(documentData.task?.officialSolution, "Авторское решение не опубликовано.");
    } catch (error) {
      document.querySelector("#solution-text").innerHTML =
        "<p>Не удалось загрузить опубликованный ответ. Попробуйте обновить страницу.</p>";
      document.querySelector("#official-solution-text").innerHTML =
        "<p>Авторское решение временно недоступно.</p>";
    }
  }

  if (page === "leaderboard") renderLeaderboard();
  if (page === "competitions") renderCatalog();
  if (page === "solution") renderSolution();
})();

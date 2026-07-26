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
    renderReleasePicker(initialRelease.id);
    renderRelease(initialRelease);
    document.querySelector("#release-tabs").addEventListener("click", (event) => {
      const link = event.target.closest("[data-release]");
      if (!link) return;
      event.preventDefault();
      const release = releaseById(link.dataset.release);
      if (!release) return;
      renderReleasePicker(release.id);
      renderRelease(release);
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("release", release.id);
      history.replaceState({}, "", url);
      window.scrollTo({ top: 0, behavior: "smooth" });
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
    const head = `
      <thead>
        <tr>
          <th class="rank-column" scope="col">#</th>
          <th class="participant-column" scope="col">Модель / команда</th>
          ${competition.tasks.map((task) => `<th class="task-column" scope="col" title="${escapeHtml(task.title)}">${escapeHtml(task.short)}</th>`).join("")}
          <th class="metric-column" scope="col">Решено</th>
          <th class="metric-column" scope="col">Точность</th>
          <th class="metric-column" scope="col">Деньги</th>
          <th class="metric-column" scope="col">Токены</th>
        </tr>
      </thead>
    `;

    const modelRows = competition.participants.filter((item) => item.type === "model");
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
        : String(participant.rank).padStart(2, "0");

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
          <td class="metric-cell strong">${participant.solved ?? "—"}</td>
          <td class="metric-cell strong">${participant.accuracy == null ? "—" : `${String(participant.accuracy).replace(".", ",")}%`}</td>
          <td class="metric-cell">${participant.cost == null ? "—" : `$${participant.cost.toFixed(3)}`}</td>
          <td class="metric-cell">${participant.tokens == null ? "—" : number.format(participant.tokens)}</td>
        </tr>
      `;
    }).join("");

    return `<table class="leaderboard-table">${head}<tbody>${body}</tbody></table>`;
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

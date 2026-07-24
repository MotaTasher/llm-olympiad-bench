(function () {
  "use strict";

  const data = window.RESULTS_DATA;
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
    const hasResults = competition.tasks.length && competition.participants.length;
    const content = hasResults
      ? `
        <div class="leaderboard-meta">
          <span>${competition.tasks.length} задач · ${modelCount} моделей · топ-3 команды</span>
          <span>Нажмите на балл модели, чтобы открыть решение</span>
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
    const rows = [
      ...modelRows,
      { type: "separator" },
      ...teamRows
    ];

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
        const content = `<span>${scoreText(score)}</span>`;
        if (isTeam || score === null || score === undefined) {
          return `<td class="result-cell ${scoreClass(score)}">${content}</td>`;
        }
        const href = `solution.html?competition=${encodeURIComponent(competition.id)}&participant=${encodeURIComponent(participant.id)}&task=${encodeURIComponent(task.id)}`;
        return `<td class="result-cell ${scoreClass(score)}"><a href="${href}" aria-label="${escapeHtml(participant.name)}, ${escapeHtml(task.title)}: ${score} баллов">${content}</a></td>`;
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

  function renderSolution() {
    const params = query();
    const competition = competitionById(params.get("competition")) || data.competitions[0];
    const participant = competition.participants.find((item) => item.id === params.get("participant"))
      || competition.participants.find((item) => item.type === "model");
    const taskIndex = competition.tasks.findIndex((item) => item.id === params.get("task"));
    const safeTaskIndex = taskIndex >= 0 ? taskIndex : 0;
    const task = competition.tasks[safeTaskIndex];
    const score = participant?.scores?.[safeTaskIndex];
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
    document.querySelector("#solution-cost").textContent = participant?.cost == null ? "—" : `$${participant.cost.toFixed(3)} за соревнование`;
    document.querySelector("#solution-tokens").textContent = participant?.tokens == null ? "—" : `${number.format(participant.tokens)} за соревнование`;
    document.querySelector("#solution-text").innerHTML = `
      <p>Это рабочий прототип страницы чтения конкретного ответа. Ячейка уже сохраняет контекст соревнования, модели и задачи в URL.</p>
      <p>На следующем этапе сюда будет подставляться полный неизменённый текст ответа из run-log, связанный по <code>competition_id + problem_id + result_id</code>. Рядом останутся вердикт, стоимость, токены и раскрывающееся авторское решение.</p>
      <h3>Структура будущего ответа</h3>
      <p>Формализация условия, введённые обозначения, последовательное доказательство и финальный вывод модели будут показаны в одной комфортной колонке без элементов внутреннего scoring-интерфейса.</p>
    `;
  }

  if (page === "leaderboard") renderLeaderboard();
  if (page === "competitions") renderCatalog();
  if (page === "solution") renderSolution();
})();

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicResultsStaticTests(unittest.TestCase):
    def test_solution_sections_have_stable_persistence_ids(self) -> None:
        html = (ROOT / "public_results" / "solution.html").read_text(encoding="utf-8")
        for section in ("statement", "model", "official"):
            self.assertIn(f'data-reading-section="{section}"', html)
        statement = html.index('data-reading-section="statement"')
        official = html.index('data-reading-section="official"')
        model = html.index('data-reading-section="model"')
        result = html.index('class="solution-review-section"')
        self.assertLess(result, statement)
        self.assertLess(statement, model)
        self.assertLess(model, official)
        self.assertEqual(html.count('data-solution-score'), 1)
        self.assertNotIn('id="expert-review-section" hidden', html)
        self.assertIn('id="expert-review-comment" hidden', html)

    def test_solution_ui_persists_sections_and_colors_cards_by_result(self) -> None:
        app = (ROOT / "public_results" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public_results" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem(readingPreferencesKey)", app)
        self.assertIn("window.localStorage.setItem(readingPreferencesKey", app)
        self.assertIn("function enableReadingBackgroundCollapse()", app)
        self.assertIn('event.target.matches(', app)
        self.assertIn('".reading-solution, .task-model-body, .prose"', app)
        self.assertIn("document.body.dataset.resultState", app)
        self.assertIn('${renderMarkdown(feedback, "")}', app)
        self.assertIn("if (feedback) renderMathInNode(container)", app)
        for state in ("full", "partial", "zero"):
            self.assertIn(f'data-result-state="{state}"', styles)
        for color in ("#98b993", "#c9aa67", "#cb7f76"):
            self.assertIn(color, styles)
        for old_color in ("#d9ff72", "#ffd166", "#ff806d"):
            self.assertNotIn(old_color, styles)
        self.assertIn("border-color: rgba(var(--result-accent-rgb)", styles)
        self.assertNotIn('data-reading-section="model" open', (ROOT / "public_results" / "solution.html").read_text(encoding="utf-8"))
        self.assertIn(".reading-reference[open]", styles)
        reference_css = styles[styles.index(".reading-reference,"):styles.index(".task-model-list")]
        self.assertIn("border-color: var(--line);", reference_css)
        self.assertNotIn("rgba(var(--result-accent-rgb)", reference_css)

    def test_task_page_lists_all_models_and_task_headers_link_without_sorting(self) -> None:
        task_html = (ROOT / "public_results" / "task.html").read_text(encoding="utf-8")
        app = (ROOT / "public_results" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-page="task"', task_html)
        self.assertIn('id="task-model-solutions"', task_html)
        self.assertEqual(task_html.count("reading-reference"), 2)
        self.assertNotIn('data-reading-section="statement" open', task_html)
        self.assertNotIn('data-reading-section="official" open', task_html)
        self.assertIn("function taskRoute(competition, task)", app)
        self.assertIn('class="task-header-link"', app)
        self.assertNotIn('sortableHeader(`task:', app)
        self.assertIn('data-reading-section="model:', app)
        self.assertIn("compareParticipants(left, right, sortState(competition.id), ranks)", app)
        self.assertLess(app.index('class="task-result-panel"'), app.index('data-task-answer'))

    def test_model_page_lists_every_task_and_model_names_link_to_it(self) -> None:
        model_html = (ROOT / "public_results" / "model.html").read_text(encoding="utf-8")
        app = (ROOT / "public_results" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-page="model"', model_html)
        self.assertIn('id="model-task-solutions"', model_html)
        for field in ("model-rank", "model-points", "model-cost", "model-tokens", "model-accuracy"):
            self.assertIn(f'id="{field}"', model_html)
        self.assertIn("function modelPageSlug(participant)", app)
        self.assertIn('replace(/^claude-/, "")', app)
        self.assertIn("function modelRoute(competition, participant)", app)
        self.assertIn('class="participant-name participant-link"', app)
        self.assertIn('data-reading-section="model-set:', app)
        self.assertIn("function attemptMetricsMarkup()", app)
        self.assertIn("function renderAttemptMetrics(card, result)", app)
        self.assertIn('data-attempt-cost', app)
        self.assertEqual(app.count("renderAttemptMetrics(card, documentData.result || {})"), 2)
        self.assertIn('if (page === "model") renderModel()', app)

    def test_catalog_links_to_results_and_whole_problem_set(self) -> None:
        catalog_html = (ROOT / "public_results" / "competitions.html").read_text(encoding="utf-8")
        set_html = (ROOT / "public_results" / "problem-set.html").read_text(encoding="utf-8")
        app = (ROOT / "public_results" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public_results" / "styles.css").read_text(encoding="utf-8")
        data = (ROOT / "public_results" / "data.js").read_text(encoding="utf-8")

        self.assertNotIn("Опубликованные", catalog_html)
        self.assertNotIn("Для каждого этапа есть отдельная таблица", catalog_html)
        self.assertNotIn("Результаты моделей и трёх лучших команд", data)
        self.assertNotIn("Результаты моделей на задачах", data)
        self.assertIn('data-page="problem-set"', set_html)
        self.assertIn('id="problem-set-list"', set_html)
        self.assertIn("function problemSetRoute(competitionId)", app)
        self.assertIn('class="competition-card-link"', app)
        self.assertIn("Условия и авторские решения", app)
        self.assertIn("Таблица результатов", app)
        self.assertNotIn('class="catalog-action primary"', app)
        self.assertNotIn('class="catalog-action secondary"', app)
        self.assertNotIn('Таблица результатов <span aria-hidden="true">↗</span>', app)
        self.assertIn('class="competition-card-stage"', app)
        self.assertIn('stageLabel: "Финал"', data)
        self.assertIn('stageLabel: "Отбор"', data)
        self.assertIn('if (page === "problem-set") renderProblemSet()', app)
        self.assertIn(".cost-column, .cost-cell, .tokens-column", styles)
        self.assertIn("width: 148px; min-width: 148px; max-width: 148px;", styles)


if __name__ == "__main__":
    unittest.main()

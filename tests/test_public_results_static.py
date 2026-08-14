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
        self.assertIn("document.body.dataset.resultState", app)
        self.assertIn('${renderMarkdown(feedback, "")}', app)
        self.assertIn("if (feedback) renderMathInNode(container)", app)
        for state in ("full", "partial", "zero"):
            self.assertIn(f'data-result-state="{state}"', styles)
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
        self.assertIn('if (page === "problem-set") renderProblemSet()', app)
        self.assertIn(".cost-column, .cost-cell, .tokens-column", styles)
        self.assertIn("width: 148px; min-width: 148px; max-width: 148px;", styles)


if __name__ == "__main__":
    unittest.main()

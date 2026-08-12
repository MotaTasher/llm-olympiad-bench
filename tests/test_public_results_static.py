import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicResultsStaticTests(unittest.TestCase):
    def test_solution_sections_have_stable_persistence_ids(self) -> None:
        html = (ROOT / "public_results" / "solution.html").read_text(encoding="utf-8")
        for section in ("statement", "model", "official"):
            self.assertIn(f'data-reading-section="{section}"', html)

    def test_solution_ui_persists_sections_and_colors_cards_by_result(self) -> None:
        app = (ROOT / "public_results" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public_results" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem(readingPreferencesKey)", app)
        self.assertIn("window.localStorage.setItem(readingPreferencesKey", app)
        self.assertIn("document.body.dataset.resultState", app)
        for state in ("full", "partial", "zero"):
            self.assertIn(f'data-result-state="{state}"', styles)
        self.assertIn("linear-gradient", styles)


if __name__ == "__main__":
    unittest.main()

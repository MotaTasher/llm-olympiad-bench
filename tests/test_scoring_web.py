from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import runner

from scoring.app import app as scoring_app
from scoring.auth import create_user, get_user_by_username, set_user_active
from scoring.cost_estimator import cost_context
from scoring.repository import build_catalog, configured_model_columns


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ScoringWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.logs_dir = self.tmp / "logs"
        self.results_dir = self.tmp / "results"
        self.competitions_dir = self.tmp / "competitions"
        self.old_config = {
            "COMPETITIONS_DIR": scoring_app.config["COMPETITIONS_DIR"],
            "LOGS_DIR": scoring_app.config["LOGS_DIR"],
            "RESULTS_DIR": scoring_app.config["RESULTS_DIR"],
            "AUTH_DB": scoring_app.config.get("AUTH_DB"),
            "TESTING": scoring_app.config.get("TESTING"),
            "WTF_CSRF_TIME_LIMIT": scoring_app.config.get("WTF_CSRF_TIME_LIMIT"),
        }
        scoring_app.config.update(
            COMPETITIONS_DIR=self.competitions_dir,
            LOGS_DIR=self.logs_dir,
            RESULTS_DIR=self.results_dir,
            AUTH_DB=self.tmp / "auth.sqlite3",
            TESTING=True,
            WTF_CSRF_TIME_LIMIT=None,
        )
        self.username = "reviewer-01"
        _, self.password = create_user(Path(scoring_app.config["AUTH_DB"]), self.username)
        self.client = scoring_app.test_client()
        self.login()

    def tearDown(self) -> None:
        scoring_app.config.update(self.old_config)
        shutil.rmtree(self.tmp)

    def anonymous_client(self):
        return scoring_app.test_client()

    def csrf_token(self, path: str = "/login", *, client=None) -> str:
        client = client or self.client
        response = client.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match, response.get_data(as_text=True))
        return match.group(1)

    def login(self, *, username: str | None = None, password: str | None = None, client=None, next_url: str = "/"):
        client = client or self.client
        token = self.csrf_token(f"/login?next={next_url}", client=client)
        return client.post(
            f"/login?next={next_url}",
            data={
                "username": username or self.username,
                "password": password or self.password,
                "csrf_token": token,
            },
            follow_redirects=False,
        )

    def logout(self) -> None:
        token = self.csrf_token("/")
        response = self.client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def authorized_post(self, path: str, data: dict, *, token_path: str | None = None, follow_redirects: bool = False):
        payload = {**data, "csrf_token": self.csrf_token(token_path or "/")}
        return self.client.post(path, data=payload, follow_redirects=follow_redirects)

    def write_competition(self, competition_id: str, *, title: str, date: str | None = None) -> Path:
        path = self.competitions_dir / competition_id
        write_json(
            path / "competition.json",
            {
                "schema_version": 1,
                "id": competition_id,
                "title": title,
                "date": date,
                "metadata": {"max_score": 10},
            },
        )
        write_json(
            path / "task_01.json",
            {
                "schema_version": 1,
                "id": "task_01",
                "number": 1,
                "title": "Task One",
                "statement": "STATEMENT_TOKEN with $x_1+x_2$",
                "answer": "ANSWER_TOKEN",
                "solution": "SOLUTION_TOKEN",
                "metadata": {"max_score": 10},
            },
        )
        return path

    def write_run(
        self,
        *,
        competition_id: str = "math_2026",
        model_id: str = "gpt-5.5",
        provider: str = "openai",
        result_id: str = "res_a",
        answer: str = "MODEL_ANSWER_TOKEN",
        run_id: str = "run_active",
        timestamp: str = "2026-06-20T00:00:00Z",
    ) -> None:
        write_json(
            self.logs_dir / competition_id / "task_01" / f"{run_id}.json",
            {
                "schema_version": 2,
                "run_id": run_id,
                "timestamp": timestamp,
                "completed_at": timestamp,
                "competition_id": competition_id,
                "competition_title": "Math 2026",
                "problem_id": "task_01",
                "problem_title": "Task One",
                "results": [
                    {
                        "result_id": result_id,
                        "result_index": 0,
                        "provider": provider,
                        "model": model_id,
                        "requested_model_id": model_id,
                        "resolved_model_id": model_id,
                        "answer": answer,
                        "error": None,
                        "status": "success",
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "cost_usd": 0,
                        "latency_ms": 3,
                        "raw_response": {},
                    }
                ],
            },
        )

    def test_unauthenticated_get_routes_redirect_to_login(self) -> None:
        competition_path = self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        asset_path = competition_path / "assets" / "diagram.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"image-bytes")
        self.write_run()

        anon = self.anonymous_client()
        paths = [
            "/",
            "/competition/math_2026",
            "/competition/math_2026/stats",
            "/competition/math_2026/problem/task_01",
            "/competition/math_2026/problem/task_01/anonymous?seed=fixed&n=1",
            "/competition/math_2026/problem/assets/diagram.png",
            "/competition/math_2026/problem/task_01/assets/diagram.png",
            "/competition/math_2026/evaluations.csv",
            "/competition/math_2026/problem/task_01/evaluations.csv",
            "/competition/math_2026/problem/task_01/run/run_active",
            "/run/run_active",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = anon.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login?next=", response.headers["Location"])

    def test_unauthenticated_posts_do_not_write(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        anon = self.anonymous_client()
        sidecar_path = self.results_dir / "math_2026" / "task_01" / "run_active.json"

        requests = [
            (
                "/score",
                {
                    "competition_id": "math_2026",
                    "problem_id": "task_01",
                    "run_id": "run_active",
                    "result_id": "res_a",
                    "model_key": "openai:gpt-5.5",
                    "score": "7",
                },
            ),
            (
                "/score/delete",
                {
                    "competition_id": "math_2026",
                    "problem_id": "task_01",
                    "run_id": "run_active",
                    "result_id": "res_a",
                    "evaluation_id": "ev_missing",
                },
            ),
            ("/competition/math_2026/evaluations/import", {}),
            ("/competition/math_2026/problem/task_01/evaluations/import", {}),
        ]
        for path, data in requests:
            with self.subTest(path=path):
                response = anon.post(path, data=data)
                self.assertIn(response.status_code, {400, 401})
        self.assertFalse(sidecar_path.exists())

    def test_login_page_register_route_and_open_redirect(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(answer="MODEL_SECRET_TOKEN")
        anon = self.anonymous_client()

        login_page = anon.get("/login")
        self.assertEqual(login_page.status_code, 200)
        html = login_page.get_data(as_text=True)
        self.assertNotIn("STATEMENT_TOKEN", html)
        self.assertNotIn("MODEL_SECRET_TOKEN", html)
        self.assertNotIn("Стоимость прогона", html)

        token = self.csrf_token("/login?next=https://example.com/steal", client=anon)
        response = anon.post(
            "/login?next=https://example.com/steal",
            data={"username": self.username, "password": self.password, "csrf_token": token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        self.assertEqual(self.client.get("/register").status_code, 404)

    def test_cli_create_generates_random_password_and_hash_only(self) -> None:
        runner_cli = scoring_app.test_cli_runner()
        result = runner_cli.invoke(args=["user", "create", "cli-user"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("User created: cli-user", result.output)
        self.assertIn("Save this password now", result.output)
        match = re.search(r"Password: (\S+)", result.output)
        self.assertIsNotNone(match, result.output)
        password = match.group(1)
        self.assertGreaterEqual(len(password), 40)

        user = get_user_by_username(Path(scoring_app.config["AUTH_DB"]), "CLI-USER")
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password_hash, password)
        self.assertNotIn(user.password_hash, result.output)

        second = runner_cli.invoke(args=["user", "create", "cli-user"])
        self.assertNotEqual(second.exit_code, 0)

    def test_login_failures_disabled_reset_logout_and_csrf(self) -> None:
        anon = self.anonymous_client()
        bad_token = self.csrf_token("/login", client=anon)
        bad = anon.post(
            "/login",
            data={"username": self.username, "password": "wrong", "csrf_token": bad_token},
        )
        self.assertEqual(bad.status_code, 200)
        self.assertIn("Неверный логин или пароль", bad.get_data(as_text=True))
        self.assertEqual(anon.get("/").status_code, 302)

        unknown_token = self.csrf_token("/login", client=anon)
        unknown = anon.post(
            "/login",
            data={"username": "missing-user", "password": "wrong", "csrf_token": unknown_token},
        )
        self.assertEqual(unknown.status_code, 200)
        self.assertIn("Неверный логин или пароль", unknown.get_data(as_text=True))

        set_user_active(Path(scoring_app.config["AUTH_DB"]), self.username, False)
        disabled_token = self.csrf_token("/login", client=anon)
        disabled = anon.post(
            "/login",
            data={"username": self.username, "password": self.password, "csrf_token": disabled_token},
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertIn("Неверный логин или пароль", disabled.get_data(as_text=True))
        self.assertEqual(self.client.get("/").status_code, 302)

        set_user_active(Path(scoring_app.config["AUTH_DB"]), self.username, True)
        reset_result = scoring_app.test_cli_runner().invoke(args=["user", "reset-password", self.username])
        self.assertEqual(reset_result.exit_code, 0, reset_result.output)
        new_password = re.search(r"Password: (\S+)", reset_result.output).group(1)

        old_client = self.anonymous_client()
        old_token = self.csrf_token("/login", client=old_client)
        old_login = old_client.post(
            "/login",
            data={"username": self.username, "password": self.password, "csrf_token": old_token},
        )
        self.assertIn("Неверный логин или пароль", old_login.get_data(as_text=True))

        new_client = self.anonymous_client()
        new_login = self.login(password=new_password, client=new_client)
        self.assertEqual(new_login.status_code, 302)
        self.assertEqual(new_client.get("/").status_code, 200)

        self.assertEqual(new_client.post("/score", data={}).status_code, 400)
        self.assertEqual(new_client.get("/logout").status_code, 405)
        self.assertEqual(new_client.get("/").status_code, 200)
        logout_token = self.csrf_token("/", client=new_client)
        logout_response = new_client.post("/logout", data={"csrf_token": logout_token})
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(new_client.get("/").status_code, 302)

    def test_templates_do_not_contain_legacy_reviewer_controls(self) -> None:
        for path in Path("scoring/templates").glob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("global-reviewer", text, path)
            self.assertNotIn("olympiadScorerReviewer", text, path)
            self.assertNotIn('name="evaluator"', text, path)

    def test_csv_my_reviews_filters_by_current_username(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        write_json(
            self.results_dir / "math_2026" / "task_01" / "run_active.json",
            {
                "schema_version": 2,
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_active",
                "evaluation_pool": {
                    "res_a": [
                        {
                            "evaluation_id": "ev_mine",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": self.username,
                            "score": 7,
                            "max_score": 10,
                            "score_category": "partial",
                            "feedback": "mine",
                            "created_at": "2026-06-20T00:00:00Z",
                            "updated_at": "2026-06-20T00:00:00Z",
                        },
                        {
                            "evaluation_id": "ev_other",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": "other-reviewer",
                            "score": 5,
                            "max_score": 10,
                            "score_category": "partial",
                            "feedback": "other",
                            "created_at": "2026-06-20T00:00:01Z",
                            "updated_at": "2026-06-20T00:00:01Z",
                        },
                    ]
                },
            },
        )
        page = self.client.get("/competition/math_2026").get_data(as_text=True)
        self.assertIn(f"evaluator={self.username}", page)

        csv_response = self.client.get(f"/competition/math_2026/evaluations.csv?evaluator={self.username}")
        text = csv_response.get_data(as_text=True)
        self.assertIn("ev_mine", text)
        self.assertNotIn("ev_other", text)

    def test_task_pages_show_only_current_user_evaluations(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        write_json(
            self.results_dir / "math_2026" / "task_01" / "run_active.json",
            {
                "schema_version": 2,
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_active",
                "evaluation_pool": {
                    "res_a": [
                        {
                            "evaluation_id": "ev_mine",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": self.username,
                            "score": 7,
                            "max_score": 10,
                            "score_category": "partial",
                            "feedback": "mine-visible-feedback",
                            "created_at": "2026-06-20T00:00:00Z",
                            "updated_at": "2026-06-20T00:00:00Z",
                        },
                        {
                            "evaluation_id": "ev_other",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": "other-reviewer",
                            "score": 10,
                            "max_score": 10,
                            "score_category": "full",
                            "feedback": "other-hidden-feedback",
                            "created_at": "2026-06-20T00:00:01Z",
                            "updated_at": "2026-06-20T00:00:01Z",
                        },
                    ]
                },
            },
        )

        problem_html = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5").get_data(
            as_text=True
        )
        anonymous_html = self.client.get(
            "/competition/math_2026/problem/task_01/anonymous?seed=fixed&n=1"
        ).get_data(as_text=True)
        for html in (problem_html, anonymous_html):
            self.assertIn("Мои проверки", html)
            self.assertIn("mine-visible-feedback", html)
            self.assertIn("проверок: 1", html)
            self.assertNotIn("other-hidden-feedback", html)
            self.assertNotIn("other-reviewer", html)
            self.assertNotIn("проверок: 2", html)

        full_csv = self.client.get("/competition/math_2026/evaluations.csv").get_data(as_text=True)
        self.assertIn("mine-visible-feedback", full_csv)
        self.assertIn("other-hidden-feedback", full_csv)

        competition_html = self.client.get("/competition/math_2026").get_data(as_text=True)
        self.assertIn("Частично", competition_html)
        self.assertNotIn("Макс.", competition_html)
        self.assertNotIn("Максимум", competition_html)

    def test_problem_page_is_single_column_statement_reference_answer_order(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        response = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Условие"), html.index("Показать эталонное решение"))
        self.assertLess(html.index("Показать эталонное решение"), html.index("Ответ модели"))
        self.assertLess(html.index("Ответ модели"), html.index("MODEL_ANSWER_TOKEN"))
        self.assertIn('<div id="problem-statement" class="rendered scrollable-content" data-markdown>STATEMENT_TOKEN', html)
        self.assertIn("data-score-form", html)

    def test_problem_page_has_copy_source_and_json_buttons(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        response = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('data-copy-target="problem-statement"', html)
        self.assertIn('data-copy-target="reference-answer"', html)
        self.assertIn('data-copy-target="reference-solution"', html)
        self.assertIn('data-copy-target="model-answer"', html)
        self.assertIn('data-copy-target="result-json"', html)
        self.assertIn('id="result-json"', html)

    def test_anonymous_page_uses_same_sequence_and_full_width_selector(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        response = self.client.get("/competition/math_2026/problem/task_01/anonymous?seed=fixed&n=1")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Условие"), html.index("Показать эталонное решение"))
        self.assertLess(html.index("Показать эталонное решение"), html.index("Решение 1"))
        self.assertLess(html.index("Решение 1"), html.index("MODEL_ANSWER_TOKEN"))
        self.assertLess(html.index("MODEL_ANSWER_TOKEN"), html.index("Выбор решения"))
        self.assertIn('<div class="answer-layout">', html)
        self.assertIn('data-copy-target="problem-statement"', html)
        self.assertIn('Скопировать исходник', html)

    def test_problem_markdown_relative_assets_are_served(self) -> None:
        competition_path = self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        asset_path = competition_path / "assets" / "diagram.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"image-bytes")

        problem_relative = self.client.get("/competition/math_2026/problem/assets/diagram.png")
        self.assertEqual(problem_relative.status_code, 200)
        self.assertEqual(problem_relative.data, b"image-bytes")
        problem_relative.close()

        anonymous_relative = self.client.get("/competition/math_2026/problem/task_01/assets/diagram.png")
        self.assertEqual(anonymous_relative.status_code, 200)
        self.assertEqual(anonymous_relative.data, b"image-bytes")
        anonymous_relative.close()

    def test_score_uses_current_user_and_ignores_posted_evaluator(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        sidecar_path = self.results_dir / "math_2026" / "task_01" / "run_active.json"

        ok = self.authorized_post(
            "/score",
            {
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_active",
                "result_id": "res_a",
                "model_key": "openai:gpt-5.5",
                "evaluator": "BrowserSuppliedName",
                "score": "7",
                "feedback": "ok",
            },
            token_path="/competition/math_2026/problem/task_01?model=openai:gpt-5.5",
            follow_redirects=False,
        )
        self.assertEqual(ok.status_code, 302)
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["evaluation_pool"]["res_a"][0]["evaluator"], self.username)

    def test_active_model_catalog_contains_only_strong_models(self) -> None:
        expected = {
            "openai:gpt-5.5",
            "openai:gpt-5.4-mini",
            "anthropic:claude-opus-4-8",
            "anthropic:claude-haiku-4-5-20251001",
            "deepseek:deepseek-v4-pro",
            "deepseek:deepseek-v4-flash",
            "gigachat:GigaChat-2-Max",
            "gigachat:GigaChat-2",
            "yandexgpt:yandexgpt-5.1",
            "yandexgpt:yandexgpt-5-lite",
        }
        self.assertEqual(set(runner.active_model_specs()), expected)
        self.assertEqual(set(configured_model_columns()), expected)

    def test_problem_page_does_not_show_legacy_cost_calculator(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")

        response = self.client.get("/competition/math_2026/problem/task_01?max_tokens=2048&runs=3")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertNotIn("Калькулятор стоимости", html)
        self.assertNotIn("потолок 2048 output-токенов", html)
        self.assertNotIn("Пересчитать", html)
        self.assertNotIn("calculator-form", html)

    def test_active_budget_model_creates_scoring_column(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(model_id="gpt-5.4-mini", result_id="res_budget", run_id="run_budget")
        self.write_run(
            model_id="yandexgpt-5.1/latest",
            provider="yandexgpt",
            result_id="res_yandex",
            run_id="run_yandex",
            answer="YANDEX_ALIAS_ANSWER",
        )

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        competition = catalog["competition_map"]["math_2026"]
        model_keys = [column["model_key"] for column in competition["model_columns"]]
        self.assertIn("openai:gpt-5.4-mini", model_keys)
        self.assertIn("yandexgpt:yandexgpt-5.1", model_keys)

        problem = competition["problems"]["task_01"]
        active_attempts = {
            state["model_key"]: state["attempt_count"]
            for state in problem["model_states"]
        }
        self.assertEqual(active_attempts["openai:gpt-5.5"], 0)
        self.assertEqual(active_attempts["openai:gpt-5.4-mini"], 1)
        self.assertEqual(active_attempts["yandexgpt:yandexgpt-5.1"], 1)

        html = self.client.get("/competition/math_2026").get_data(as_text=True)
        self.assertIn("gpt-5.4-mini", html)

    def test_competitions_group_by_year_and_sort_chronologically_inside_year(self) -> None:
        self.write_competition("2026_05_math_cup_cs_space", title="May Cup", date=None)
        self.write_competition("math_2026_june", title="June Cup", date="2026-06-01")
        self.write_competition("math_2025_winter", title="Winter Cup", date="2025-12-01")
        self.write_competition("legacy_examples", title="Legacy Examples", date=None)
        self.write_run(competition_id="2026_05_math_cup_cs_space", run_id="may_run")
        self.write_run(competition_id="math_2026_june", run_id="june_run", timestamp="2026-06-10T00:00:00Z")
        self.write_run(competition_id="math_2025_winter", run_id="winter_run", timestamp="2025-12-10T00:00:00Z")

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        groups = catalog["competition_groups"]
        self.assertEqual([group["year"] for group in groups], [2026, 2025, None])
        self.assertEqual(
            [item["competition_id"] for item in groups[0]["competitions"]],
            ["2026_05_math_cup_cs_space", "math_2026_june"],
        )
        self.assertEqual(groups[-1]["competitions"][0]["competition_id"], "legacy_examples")

    def test_cost_context_contains_competition_and_exchange_rate(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        context = cost_context(catalog["competitions"])
        self.assertIn("exchangeRate", context)
        self.assertIn("usdRub", context["exchangeRate"])
        self.assertEqual(context["defaults"]["reasoningBudget"], 8000)
        self.assertEqual(context["competitions"][0]["competitionId"], "math_2026")
        self.assertTrue(context["competitions"][0]["models"])

    def test_competition_page_shows_cost_without_launch_routes(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(competition_id="math_2026", model_id="gpt-5.5", provider="openai")

        response = self.client.get("/competition/math_2026")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Стоимость прогона", html)
        self.assertIn("data-cost-context", html)
        self.assertIn("data-cost-range=\"reasoningBudget\"", html)
        self.assertIn("data-cost-number=\"finalTokens\"", html)
        self.assertIn("data-cost-competition=\"math_2026\"", html)
        self.assertIn("data-cost-model=\"openai:gpt-5.5\"", html)
        self.assertIn("cost-run-grid", html)
        self.assertIn("cost-run-summary", html)
        self.assertIn("Цена за 1K токенов", html)
        self.assertIn("data-cost-model-price", html)
        self.assertIn("data-cost-model-usd", html)
        self.assertIn("data-cost-model-rub", html)
        self.assertIn("data-cost-total-row=\"math_2026\"", html)
        self.assertIn("data-cost-total-usd", html)
        self.assertIn("Сумма", html)
        self.assertIn("API-вызовы не выполняются", html)
        self.assertNotIn("<th class=\"numeric\">Пар</th>", html)
        self.assertNotIn("<th class=\"numeric\">Пропущено</th>", html)
        self.assertNotIn("<th>Без price table</th>", html)
        self.assertNotIn("Пересчитать", html)
        self.assertNotIn("calculator-form", html)
        self.assertNotIn("Запустить соревнование", html)

        self.assertEqual(
            self.authorized_post(
                "/competition/math_2026/runs",
                {},
                token_path="/competition/math_2026",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/competition/math_2026/runs/job_missing").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()

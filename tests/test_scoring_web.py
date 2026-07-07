from __future__ import annotations

from html.parser import HTMLParser
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import runner

from scoring.app import app as scoring_app, competition_card_description, competition_date
from scoring.auth import create_user, get_user_by_username, set_user_active
from scoring.presentation import format_datetime_parts
from scoring.repository import (
    aggregate_scores,
    build_catalog,
    checks_statistics,
    competition_statistics,
    configured_model_columns,
    format_score_value,
    half_score_for,
    model_states_for_review,
    model_presentation,
    score_ticks_for,
    score_step_for,
)
from scripts.validate_problem_data import Finding, validate_competition_dir


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def joined(*parts: str) -> str:
    return "".join(parts)


class CompetitionCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict] = []
        self._current: dict | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "a" and "competition-card" in classes and self._current is None:
            self._current = {
                "tag": tag,
                "attrs": attr_map,
                "text": [],
                "nested_links": 0,
                "onclick": "onclick" in attr_map,
            }
            self._depth = 1
            return
        if self._current is not None:
            self._depth += 1
            if tag == "a":
                self._current["nested_links"] += 1

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        self._depth -= 1
        if self._depth == 0:
            self._current["text"] = " ".join("".join(self._current["text"]).split())
            self.cards.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"].append(data)


class CompetitionProgressParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.bars: list[dict] = []
        self.summaries: list[str] = []
        self._current_bar: dict | None = None
        self._current_summary: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "div" and "competition-progress" in classes:
            self._current_bar = {"attrs": attr_map, "segments": []}
            self.bars.append(self._current_bar)
        elif tag == "span" and self._current_bar is not None and "competition-progress-segment" in classes:
            self._current_bar["segments"].append(attr_map)
        elif tag == "div" and "competition-progress-summary" in classes:
            self._current_summary = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._current_summary is not None:
            self.summaries.append(compact_text(self._current_summary))
            self._current_summary = None
        elif tag == "div" and self._current_bar is not None:
            self._current_bar = None

    def handle_data(self, data: str) -> None:
        if self._current_summary is not None:
            self._current_summary.append(data)


def compact_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return compact_text(self.parts)


class CompetitionMatrixParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.wrapper_classes: set[str] = set()
        self.table_attrs: dict[str, str] = {}
        self.cols: list[set[str]] = []
        self.header_rows: list[list[dict]] = []
        self.body_rows: list[dict] = []
        self.tooltips: dict[str, str] = {}
        self.model_links: list[dict] = []
        self.task_links: list[dict] = []
        self.matrix_cells: list[dict] = []

        self._table_depth = 0
        self._in_table = False
        self._in_thead = False
        self._in_tbody = False
        self._current_header_row: list[dict] | None = None
        self._current_th: dict | None = None
        self._current_tooltip: dict | None = None
        self._current_link: dict | None = None
        self._current_matrix_cell: dict | None = None
        self._current_body_row: dict | None = None
        self._current_body_cell: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "div" and "competition-matrix-wrap" in classes:
            self.wrapper_classes = classes
        if tag == "table" and "competition-matrix" in classes:
            self._in_table = True
            self._table_depth = 1
            self.table_attrs = attr_map
            return
        if not self._in_table:
            return
        self._table_depth += 1
        if tag == "col":
            self.cols.append(classes)
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and self._in_thead:
            self._current_header_row = []
        elif tag == "tr" and self._in_tbody:
            self._current_body_row = {"cells": [], "model_cell_hrefs": [], "texts": [], "matrix_cells": []}
        elif tag == "th" and self._current_header_row is not None:
            self._current_th = {"attrs": attr_map, "text": [], "links": [], "tooltips": []}
        elif tag == "td" and self._current_body_row is not None:
            self._current_body_cell = {"text": [], "links": [], "matrix_cells": []}
        elif tag == "a" and self._current_th is not None:
            link = {"attrs": attr_map, "text": []}
            self._current_th["links"].append(link)
            if "model-header-link" in classes:
                self.model_links.append(link)
            self._current_link = link
        elif tag == "a" and self._current_body_cell is not None:
            link = {"attrs": attr_map, "text": []}
            self._current_body_cell["links"].append(link)
            if "matrix-cell" in classes and self._current_body_row is not None:
                self._current_body_row["model_cell_hrefs"].append(attr_map.get("href", ""))
                matrix_cell = {"tag": tag, "attrs": attr_map, "text": []}
                self._current_body_cell["matrix_cells"].append(matrix_cell)
                self._current_body_row["matrix_cells"].append(matrix_cell)
                self.matrix_cells.append(matrix_cell)
                self._current_matrix_cell = matrix_cell
            if "problem-link" in classes:
                self.task_links.append(link)
            self._current_link = link
        elif tag == "span" and self._current_body_cell is not None and "matrix-cell" in classes:
            matrix_cell = {"tag": tag, "attrs": attr_map, "text": []}
            self._current_body_cell["matrix_cells"].append(matrix_cell)
            if self._current_body_row is not None:
                self._current_body_row["matrix_cells"].append(matrix_cell)
            self.matrix_cells.append(matrix_cell)
            self._current_matrix_cell = matrix_cell
        elif tag == "span" and attr_map.get("role") == "tooltip" and self._current_th is not None:
            self._current_tooltip = {"attrs": attr_map, "text": []}
            self._current_th["tooltips"].append(self._current_tooltip)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag == "table":
            self._in_table = False
            self._table_depth = 0
            return
        if tag == "a" and self._current_link is not None:
            self._current_link["text"] = compact_text(self._current_link["text"])
            self._current_link = None
            if self._current_matrix_cell is not None and self._current_matrix_cell["tag"] == "a":
                self._current_matrix_cell["text"] = compact_text(self._current_matrix_cell["text"])
                self._current_matrix_cell = None
        elif tag == "span" and self._current_tooltip is not None:
            text = compact_text(self._current_tooltip["text"])
            tooltip_id = self._current_tooltip["attrs"].get("id", "")
            if tooltip_id:
                self.tooltips[tooltip_id] = text
            self._current_tooltip["text"] = text
            self._current_tooltip = None
        elif tag == "span" and self._current_matrix_cell is not None:
            self._current_matrix_cell["text"] = compact_text(self._current_matrix_cell["text"])
            self._current_matrix_cell = None
        elif tag == "th" and self._current_th is not None and self._current_header_row is not None:
            self._current_th["text"] = compact_text(self._current_th["text"])
            self._current_header_row.append(self._current_th)
            self._current_th = None
        elif tag == "td" and self._current_body_cell is not None and self._current_body_row is not None:
            self._current_body_cell["text"] = compact_text(self._current_body_cell["text"])
            self._current_body_row["cells"].append(self._current_body_cell)
            self._current_body_row["texts"].append(self._current_body_cell["text"])
            self._current_body_cell = None
        elif tag == "tr" and self._current_header_row is not None:
            self.header_rows.append(self._current_header_row)
            self._current_header_row = None
        elif tag == "tr" and self._current_body_row is not None:
            self.body_rows.append(self._current_body_row)
            self._current_body_row = None
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False

        self._table_depth -= 1
        if self._table_depth == 0:
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._current_link is not None:
            self._current_link["text"].append(data)
        if self._current_matrix_cell is not None:
            self._current_matrix_cell["text"].append(data)
        if self._current_tooltip is not None:
            self._current_tooltip["text"].append(data)
        elif self._current_th is not None:
            self._current_th["text"].append(data)
        elif self._current_body_cell is not None:
            self._current_body_cell["text"].append(data)


class CompetitionNavParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.navs: list[dict] = []
        self.onclick_count = 0
        self.nav_row_count = 0
        self._current: dict | None = None
        self._current_link: dict | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if "onclick" in attr_map:
            self.onclick_count += 1
        if "nav-row" in classes:
            self.nav_row_count += 1
        if tag == "nav" and "competition-tabs" in classes:
            self._current = {"attrs": attr_map, "links": []}
            self._depth = 1
            return
        if self._current is None:
            return
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self._depth += 1
        if tag == "a":
            self._current_link = {"attrs": attr_map, "text": []}
            self._current["links"].append(self._current_link)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._current_link is not None:
            self._current_link["text"] = compact_text(self._current_link["text"])
            self._current_link = None
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self._depth -= 1
        if self._depth == 0:
            self.navs.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current_link is not None:
            self._current_link["text"].append(data)


class AggregateSwitcherParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.containers = 0
        self.inputs: list[dict] = []
        self.labels: list[dict] = []
        self.cells: list[dict] = []
        self.anchors: list[dict] = []
        self._in_switcher = False
        self._switcher_depth = 0
        self._current_label: dict | None = None
        self._current_cell: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if "data-checks-aggregate" in attr_map:
            self.containers += 1
        if tag == "fieldset" and "aggregate-switcher" in classes:
            self._in_switcher = True
            self._switcher_depth = 1
            return
        if self._in_switcher:
            if tag not in {"br", "hr", "img", "input", "meta", "link"}:
                self._switcher_depth += 1
            if tag == "input":
                self.inputs.append(attr_map)
            elif tag == "label":
                self._current_label = {"attrs": attr_map, "text": []}
                self.labels.append(self._current_label)
            elif tag == "a":
                self.anchors.append(attr_map)
        if "data-aggregate-cell" in attr_map:
            self._current_cell = {"attrs": attr_map, "text": []}
            self.cells.append(self._current_cell)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._current_label is not None:
            self._current_label["text"] = compact_text(self._current_label["text"])
            self._current_label = None
        elif tag == "span" and self._current_cell is not None:
            self._current_cell["text"] = compact_text(self._current_cell["text"])
            self._current_cell = None
        if self._in_switcher and tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self._switcher_depth -= 1
            if self._switcher_depth == 0:
                self._in_switcher = False

    def handle_data(self, data: str) -> None:
        if self._current_label is not None:
            self._current_label["text"].append(data)
        if self._current_cell is not None:
            self._current_cell["text"].append(data)


class ScoreControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict] = []
        self._current: dict | None = None
        self._depth = 0
        self._button: dict | None = None
        self._in_tick = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if "data-score-control" in attr_map and self._current is None:
            self._current = {"attrs": attr_map, "ranges": [], "numbers": [], "buttons": [], "ticks": []}
            self._depth = 1
            return
        if self._current is None:
            return
        if tag not in {"input", "br", "hr", "img", "meta", "link"}:
            self._depth += 1
        if tag == "input" and attr_map.get("type") == "range":
            self._current["ranges"].append(attr_map)
        elif tag == "input" and attr_map.get("type") == "number":
            self._current["numbers"].append(attr_map)
        elif tag == "button":
            self._button = {"attrs": attr_map, "text": []}
            self._current["buttons"].append(self._button)
        elif tag == "span" and "score-tick" in classes:
            self._in_tick = True
            self._current["ticks"].append([])

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "button" and self._button is not None:
            self._button["text"] = compact_text(self._button["text"])
            self._button = None
        elif tag == "span" and self._in_tick:
            if self._current is not None and self._current["ticks"]:
                self._current["ticks"][-1] = compact_text(self._current["ticks"][-1])
            self._in_tick = False
        self._depth -= 1
        if self._depth == 0:
            self.controls.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._button is not None:
            self._button["text"].append(data)
        elif self._in_tick and self._current is not None and self._current["ticks"]:
            self._current["ticks"][-1].append(data)


class ModelTabsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict] = []
        self._in_tabs = False
        self._tabs_depth = 0
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "nav" and "model-tabs" in classes:
            self._in_tabs = True
            self._tabs_depth = 1
            return
        if not self._in_tabs:
            return
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self._tabs_depth += 1
        if tag == "a" and "model-tab" in classes:
            self._current = {"attrs": attr_map, "text": []}
            self.links.append(self._current)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_tabs:
            return
        if tag == "a" and self._current is not None:
            self._current["text"] = compact_text(self._current["text"])
            self._current = None
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self._tabs_depth -= 1
            if self._tabs_depth == 0:
                self._in_tabs = False

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"].append(data)


class HumanTimeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.times: list[dict] = []
        self._current: dict | None = None
        self._current_part: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "time" and "human-datetime" in classes:
            self._current = {"attrs": attr_map, "date": [], "time": [], "text": []}
        elif self._current is not None and tag == "span" and "human-date" in classes:
            self._current_part = "date"
        elif self._current is not None and tag == "span" and "human-time" in classes:
            self._current_part = "time"

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None and tag == "span":
            self._current_part = None
        elif self._current is not None and tag == "time":
            self._current["date"] = compact_text(self._current["date"])
            self._current["time"] = compact_text(self._current["time"])
            self._current["text"] = compact_text(self._current["text"])
            self.times.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        self._current["text"].append(data)
        if self._current_part:
            self._current[self._current_part].append(data)


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

    def write_competition(
        self,
        competition_id: str,
        *,
        title: str,
        date: str | None = None,
        description: str | None = None,
        max_score: float = 10,
        score_step: float | None = None,
    ) -> Path:
        path = self.competitions_dir / competition_id
        competition_metadata = {"max_score": max_score}
        if score_step is not None:
            competition_metadata["score_step"] = score_step
        problem_metadata = {"max_score": max_score}
        write_json(
            path / "competition.json",
            {
                "schema_version": 1,
                "id": competition_id,
                "title": title,
                "date": date,
                "description": description,
                "metadata": competition_metadata,
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
                "metadata": problem_metadata,
            },
        )
        return path

    def write_score(
        self,
        *,
        competition_id: str = "math_2026",
        problem_id: str = "task_01",
        run_id: str = "run_active",
        result_id: str = "res_a",
        model_key: str = "openai:gpt-5.5",
        model: str = "gpt-5.5",
        score: float = 7,
        max_score: float = 10,
        evaluator: str | None = None,
    ) -> None:
        write_json(
            self.results_dir / competition_id / problem_id / f"{run_id}.json",
            {
                "schema_version": 2,
                "competition_id": competition_id,
                "problem_id": problem_id,
                "run_id": run_id,
                "evaluation_pool": {
                    result_id: [
                        {
                            "evaluation_id": f"ev_{result_id}",
                            "result_id": result_id,
                            "result_index": 0,
                            "model_key": model_key,
                            "model": model,
                            "evaluator": evaluator or self.username,
                            "score": score,
                            "max_score": max_score,
                            "score_category": "partial",
                            "feedback": "",
                            "created_at": "2026-06-20T00:00:00Z",
                            "updated_at": "2026-06-20T00:00:00Z",
                        }
                    ]
                },
            },
        )

    def write_run(
        self,
        *,
        competition_id: str = "math_2026",
        problem_id: str = "task_01",
        model_id: str = "gpt-5.5",
        provider: str = "openai",
        result_id: str = "res_a",
        answer: str | None = "MODEL_ANSWER_TOKEN",
        error: str | None = None,
        run_id: str = "run_active",
        timestamp: str = "2026-06-20T00:00:00Z",
        cost_usd: float = 0.0,
    ) -> None:
        write_json(
            self.logs_dir / competition_id / problem_id / f"{run_id}.json",
            {
                "schema_version": 2,
                "run_id": run_id,
                "timestamp": timestamp,
                "completed_at": timestamp,
                "competition_id": competition_id,
                "competition_title": "Math 2026",
                "problem_id": problem_id,
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
                        "error": error,
                        "status": "error" if error else "success",
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "cost_usd": cost_usd,
                        "latency_ms": 3,
                        "raw_response": {},
                    }
                ],
            },
        )

    def active_model_columns(self) -> list[dict]:
        return list(configured_model_columns().values())

    def total_matrix_cells(self, problem_count: int = 1) -> int:
        return len(self.active_model_columns()) * problem_count

    def index_progress(self) -> dict:
        html = self.client.get("/").get_data(as_text=True)
        parser = CompetitionProgressParser()
        parser.feed(html)
        visible = VisibleTextParser()
        visible.feed(html)
        self.assertEqual(len(parser.bars), 1, html)
        bar = parser.bars[0]
        counts = {
            segment["data-progress-state"]: int(segment["data-progress-count"])
            for segment in bar["segments"]
        }
        return {
            "bar": bar,
            "counts": counts,
            "summaries": parser.summaries,
            "visible_text": visible.text,
            "html": html,
        }

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
        self.assertNotIn(joined("Стоимость ", "прогона"), html)
        self.assertRegex(html, r"<button\s+type=\"submit\">\s*Войти\s*</button>")
        self.assertNotRegex(html, r"<input[^>]+type=\"submit\"")

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
        self.assertIn("Все проверки", competition_html)
        competition_matrix = CompetitionMatrixParser()
        competition_matrix.feed(competition_html)
        scored_cell = next(cell for cell in competition_matrix.matrix_cells if "cell-partial" in cell["attrs"].get("class", ""))
        self.assertEqual(scored_cell["text"], "7")
        self.assertNotIn("Частично", scored_cell["text"])
        self.assertNotIn("Макс.", competition_html)
        self.assertNotIn(">Макс.<", competition_html)

        checks_max = self.client.get("/competition/math_2026/checks?mode=max").get_data(as_text=True)
        self.assertIn("Все проверки", checks_max)
        self.assertIn("other-reviewer", checks_max)
        self.assertIn("other-hidden-feedback", checks_max)
        self.assertNotIn("?mode=", checks_max)
        checks_matrix = CompetitionMatrixParser()
        checks_matrix.feed(checks_max)
        aggregate_cell = next(cell for cell in checks_matrix.matrix_cells if cell["attrs"].get("data-median-text"))
        self.assertEqual(aggregate_cell["text"], "8.5")
        self.assertEqual(aggregate_cell["attrs"].get("data-median-text"), "8.5")
        self.assertEqual(aggregate_cell["attrs"].get("data-avg-text"), "8.5")
        self.assertEqual(aggregate_cell["attrs"].get("data-max-text"), "10")
        self.assertEqual(aggregate_cell["attrs"].get("data-min-text"), "7")

    def assert_competition_tabs(self, html: str, active_label: str) -> None:
        parser = CompetitionNavParser()
        parser.feed(html)
        self.assertEqual(len(parser.navs), 1)
        self.assertEqual(parser.navs[0]["attrs"].get("aria-label"), "Разделы соревнования")
        self.assertEqual(parser.nav_row_count, 0)
        self.assertEqual(parser.onclick_count, 0)
        links = parser.navs[0]["links"]
        self.assertEqual([link["text"] for link in links], ["Меню соревнования", "Статистика моделей", "Все проверки"])
        self.assertEqual(
            [link["attrs"].get("href") for link in links],
            ["/competition/math_2026", "/competition/math_2026/stats", "/competition/math_2026/checks"],
        )
        active = [link for link in links if link["attrs"].get("aria-current") == "page"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["text"], active_label)

    def test_competition_routes_share_accessible_tabs(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        routes = [
            ("/competition/math_2026", "Меню соревнования"),
            ("/competition/math_2026/stats", "Статистика моделей"),
            ("/competition/math_2026/checks", "Все проверки"),
        ]
        for path, active_label in routes:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_competition_tabs(response.get_data(as_text=True), active_label)

    def test_checks_aggregate_selector_is_radio_control_without_mode_links(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        self.write_score(score=0, result_id="res_a")
        html = self.client.get("/competition/math_2026/checks?mode=max").get_data(as_text=True)
        parser = AggregateSwitcherParser()
        parser.feed(html)

        self.assertEqual(parser.containers, 1)
        self.assertEqual([item.get("type") for item in parser.inputs], ["radio"] * 4)
        self.assertEqual([item.get("value") for item in parser.inputs], ["median", "avg", "max", "min"])
        self.assertEqual([label["text"] for label in parser.labels], ["Медиана", "Среднее", "Максимум", "Минимум"])
        self.assertEqual(parser.inputs[0].get("checked"), "")
        self.assertFalse(parser.anchors)
        self.assertNotIn("?mode=", html)
        self.assertNotIn("mode=max", html)
        self.assertNotIn("mode=avg", html)
        self.assertNotIn("mode=min", html)
        self.assertTrue(parser.cells)
        scored = next(cell for cell in parser.cells if cell["attrs"].get("data-median-text") == "0")
        for mode in ("median", "avg", "max", "min"):
            self.assertIn(f"data-{mode}-text", scored["attrs"])
            self.assertIn(f"data-{mode}-class", scored["attrs"])
            self.assertIn(f"data-{mode}-label", scored["attrs"])
        self.assertEqual(scored["text"], "0")

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

    def test_model_tabs_are_compact_and_stably_grouped_by_review_status(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(
            provider="anthropic",
            model_id="claude-opus-4-8",
            run_id="run_scored",
            result_id="res_scored",
            answer="SCORED",
        )
        self.write_score(run_id="run_scored", result_id="res_scored", score=8)
        self.write_run(
            provider="anthropic",
            model_id="claude-haiku-4-5-20251001",
            run_id="run_pending_first",
            result_id="res_pending_first",
            answer="PENDING_FIRST",
        )
        self.write_run(
            provider="openai",
            model_id="gpt-5.5",
            run_id="run_pending_second",
            result_id="res_pending_second",
            answer="PENDING_SECOND",
        )

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        states = model_states_for_review(catalog["competition_map"]["math_2026"]["problems"]["task_01"])
        self.assertEqual(
            [state["model_key"] for state in states[:3]],
            [
                "anthropic:claude-haiku-4-5-20251001",
                "openai:gpt-5.5",
                "anthropic:claude-opus-4-8",
            ],
        )

        html = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5").get_data(
            as_text=True
        )
        parser = ModelTabsParser()
        parser.feed(html)
        self.assertEqual([link["text"] for link in parser.links[:3]], ["Haiku 4.5", "GPT-5.5", "Opus 4.8"])
        self.assertNotIn("Ожидает проверки", [link["text"] for link in parser.links])
        self.assertNotIn("Максимальный балл", [link["text"] for link in parser.links])
        self.assertNotIn("0 баллов", [link["text"] for link in parser.links])

    def test_score_redirects_to_next_unscored_existing_model_attempt_after_save(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(provider="anthropic", model_id="claude-opus-4-8", run_id="run_wrap", result_id="res_wrap")
        self.write_run(provider="openai", model_id="gpt-5.5", run_id="run_current", result_id="res_current")
        self.write_run(
            provider="yandexgpt",
            model_id="yandexgpt-5.1",
            run_id="run_next",
            result_id="res_next",
        )

        response = self.authorized_post(
            "/score",
            {
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_current",
                "result_id": "res_current",
                "model_key": "openai:gpt-5.5",
                "score": "7",
                "feedback": "",
            },
            token_path="/competition/math_2026/problem/task_01?model=openai:gpt-5.5",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/competition/math_2026/problem/task_01?model=yandexgpt:yandexgpt-5.1&attempt=res_next",
        )

    def test_anonymous_entry_starts_with_unscored_solution_when_reviewed_exists(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(
            provider="anthropic",
            model_id="claude-opus-4-8",
            run_id="run_scored",
            result_id="res_scored",
            answer="REVIEWED_ANSWER_TOKEN",
        )
        self.write_score(run_id="run_scored", result_id="res_scored", score=10)
        self.write_run(
            provider="openai",
            model_id="gpt-5.5",
            run_id="run_unscored",
            result_id="res_unscored",
            answer="PENDING_ANSWER_TOKEN",
        )

        entry = self.client.get("/competition/math_2026/problem/task_01/anonymous")
        self.assertEqual(entry.status_code, 302)
        location = entry.headers["Location"]
        self.assertRegex(location, r"/competition/math_2026/problem/task_01/anonymous\?seed=[^&]+&n=\d+")

        html = self.client.get(location).get_data(as_text=True)
        self.assertIn("PENDING_ANSWER_TOKEN", html)
        self.assertNotIn("REVIEWED_ANSWER_TOKEN", html)
        self.assertIn("без оценки", html)

    def test_integer_scores_render_without_trailing_zero_in_review_tables(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        self.write_score(score=2, max_score=2.0)

        problem_html = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5").get_data(
            as_text=True
        )
        checks_html = self.client.get("/competition/math_2026/checks").get_data(as_text=True)

        self.assertIn("2 / 2", problem_html)
        self.assertNotIn("2 / 2.0", problem_html)
        self.assertIn("2 / 2", checks_html)
        self.assertNotIn("2 / 2.0", checks_html)
        self.assertEqual(format_score_value(2.0), "2")
        self.assertEqual(format_score_value(2.5), "2.5")

    def test_stats_aggregate_all_reviewers_by_solution_weight(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(run_id="run_a", result_id="res_a", timestamp="2026-06-20T10:20:30.123456Z")
        self.write_run(run_id="run_b", result_id="res_b", timestamp="2026-06-21T11:22:33Z")
        write_json(
            self.results_dir / "math_2026" / "task_01" / "run_a.json",
            {
                "schema_version": 2,
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_a",
                "evaluation_pool": {
                    "res_a": [
                        {
                            "evaluation_id": "ev_a_1",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": self.username,
                            "score": 10,
                            "max_score": 10,
                            "feedback": "",
                            "created_at": "2026-06-20T10:21:00Z",
                            "updated_at": "2026-06-20T10:21:00Z",
                        },
                        {
                            "evaluation_id": "ev_a_2",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": "reviewer-02",
                            "score": 0,
                            "max_score": 10,
                            "feedback": "",
                            "created_at": "2026-06-20T10:22:00Z",
                            "updated_at": "2026-06-20T10:22:00Z",
                        },
                    ]
                },
            },
        )
        write_json(
            self.results_dir / "math_2026" / "task_01" / "run_b.json",
            {
                "schema_version": 2,
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_b",
                "evaluation_pool": {
                    "res_b": [
                        {
                            "evaluation_id": "ev_b_1",
                            "result_id": "res_b",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": self.username,
                            "score": 10,
                            "max_score": 10,
                            "feedback": "",
                            "created_at": "2026-06-21T11:23:00Z",
                            "updated_at": "2026-06-21T11:23:00Z",
                        }
                    ]
                },
            },
        )

        data = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        stats = competition_statistics(data["competition_map"]["math_2026"])
        row = next(model for model in stats["models"] if model["model_key"] == "openai:gpt-5.5")
        self.assertEqual(row["solution_count"], 2)
        self.assertEqual(row["scored_solution_count"], 2)
        self.assertEqual(row["evaluation_count"], 3)
        self.assertEqual(row["problem_count"], 1)
        self.assertAlmostEqual(row["average_percent"], 75.0)
        self.assertEqual(row["full_solution_count"], 1)

        html = self.client.get("/competition/math_2026/stats").get_data(as_text=True)
        visible = VisibleTextParser()
        visible.feed(html)
        self.assertIn("Проверок", visible.text)
        self.assertIn("75.0", visible.text)
        self.assertIn("3", visible.text)
        self.assertNotIn("Модель-задача", visible.text)
        self.assertNotIn("ждёт проверки", visible.text)
        self.assertNotIn("Статистика модель-задача", html)

        detail = self.client.get("/competition/math_2026/stats?model=openai:gpt-5.5").get_data(as_text=True)
        detail_visible = VisibleTextParser()
        detail_visible.feed(detail)
        self.assertIn("Средний балл", detail_visible.text)
        self.assertIn("Максимум", detail_visible.text)
        self.assertIn("75.0", detail_visible.text)
        self.assertIn("21 июня 2026", detail_visible.text)
        self.assertNotIn("2026-06-21T11:22:33Z", detail_visible.text)

        unknown = self.client.get("/competition/math_2026/stats?model=missing:model")
        self.assertEqual(unknown.status_code, 200)
        self.assertIn("По моделям", unknown.get_data(as_text=True))

    def test_stats_include_other_reviewer_evaluations_for_single_solution(self) -> None:
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
                            "score": 6,
                            "max_score": 10,
                            "feedback": "",
                            "created_at": "2026-06-20T00:00:00Z",
                            "updated_at": "2026-06-20T00:00:00Z",
                        },
                        {
                            "evaluation_id": "ev_other",
                            "result_id": "res_a",
                            "result_index": 0,
                            "model_key": "openai:gpt-5.5",
                            "model": "gpt-5.5",
                            "evaluator": "reviewer-02",
                            "score": 10,
                            "max_score": 10,
                            "feedback": "",
                            "created_at": "2026-06-20T00:01:00Z",
                            "updated_at": "2026-06-20T00:01:00Z",
                        },
                    ]
                },
            },
        )
        stats = competition_statistics(
            build_catalog(
                competitions_dir=self.competitions_dir,
                logs_dir=self.logs_dir,
                results_dir=self.results_dir,
            )["competition_map"]["math_2026"]
        )
        row = next(model for model in stats["models"] if model["model_key"] == "openai:gpt-5.5")
        self.assertEqual(row["solution_count"], 1)
        self.assertEqual(row["scored_solution_count"], 1)
        self.assertEqual(row["evaluation_count"], 2)
        self.assertAlmostEqual(row["average_percent"], 80.0)

        html = self.client.get("/competition/math_2026/stats").get_data(as_text=True)
        self.assertIn("80.0", html)
        self.assertIn(">2</td>", html)

    def test_aggregate_scores_math_and_formatting(self) -> None:
        self.assertEqual(aggregate_scores([0, 10, 5])["median"], 5)
        self.assertEqual(aggregate_scores([0, 10])["median"], 5)
        self.assertEqual(aggregate_scores([0, 0, 9])["avg"], 3)
        minmax = aggregate_scores([2, 7, 4])
        self.assertEqual(minmax["max"], 7)
        self.assertEqual(minmax["min"], 2)
        self.assertEqual(aggregate_scores([0, 10, 5]), aggregate_scores([5, 0, 10]))
        self.assertEqual(aggregate_scores([]), {"median": None, "avg": None, "max": None, "min": None})
        self.assertEqual(format_score_value(0.0), "0")
        self.assertEqual(format_score_value(5.0), "5")
        self.assertEqual(format_score_value(2.5), "2.5")
        self.assertEqual(format_score_value(3.333333), "3.33")

    def test_score_step_resolver_and_catalog_fields(self) -> None:
        self.assertEqual(
            score_step_for({"metadata": {"score_step": 2}}, {"metadata": {"score_step": 0.5}}, 10),
            0.5,
        )
        self.assertEqual(score_step_for({"metadata": {"score_step": 2}}, {"metadata": {}}, 10), 2)
        self.assertEqual(score_step_for({"metadata": {}}, {"metadata": {}}, 10), 1)
        self.assertEqual(score_step_for({"metadata": {"score_step": "2.5"}}, {"metadata": {}}, 10), 2.5)
        invalid_values = [0, -1, True, float("nan"), float("inf"), 11]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertEqual(score_step_for({"metadata": {"score_step": value}}, {"metadata": {}}, 10), 1)
        self.assertEqual(half_score_for(10, 1), 5)
        self.assertEqual(half_score_for(50, 5), 25)
        self.assertIsNone(half_score_for(7, 1))
        self.assertIsNone(half_score_for(3, 3))
        self.assertEqual(half_score_for(0.6, 0.1), 0.3)
        self.assertEqual(score_ticks_for(50, 5), [float(value) for value in range(0, 51, 5)])
        self.assertEqual(score_ticks_for(3, 3), [0.0, 3.0])

        self.write_competition("math_2026", title="Math 2026", max_score=50, score_step=5)
        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        problem = catalog["competition_map"]["math_2026"]["problems"]["task_01"]
        self.assertEqual(problem["max_score"], 50)
        self.assertEqual(problem["score_step"], 5)
        self.assertEqual(problem["half_score"], 25)
        self.assertEqual(problem["score_ticks"], [float(value) for value in range(0, 51, 5)])
        self.assertEqual(problem["score_interval_count"], 10)

    def test_score_forms_render_range_number_and_conditional_half(self) -> None:
        cases = [
            ("scale_50", 50, 5, True, "25", [str(value) for value in range(0, 51, 5)], "10"),
            ("scale_3", 3, 3, False, None, ["0", "3"], "1"),
            ("scale_7", 7, 1, False, None, [str(value) for value in range(0, 8)], "7"),
        ]
        for competition_id, max_score, score_step, has_half, half_value, ticks, intervals in cases:
            with self.subTest(competition_id=competition_id):
                self.write_competition(competition_id, title=competition_id, max_score=max_score, score_step=score_step)
                self.write_run(competition_id=competition_id)
                for path in (
                    f"/competition/{competition_id}/problem/task_01?model=openai:gpt-5.5",
                    f"/competition/{competition_id}/problem/task_01/anonymous?seed=fixed&n=1",
                ):
                    html = self.client.get(path).get_data(as_text=True)
                    parser = ScoreControlParser()
                    parser.feed(html)
                    self.assertEqual(len(parser.controls), 1)
                    control = parser.controls[0]
                    self.assertEqual(control["ranges"][0]["min"], "0")
                    self.assertEqual(control["ranges"][0]["max"], f"{max_score:g}")
                    self.assertEqual(control["ranges"][0]["step"], f"{score_step:g}")
                    self.assertEqual(control["numbers"][0]["step"], "any")
                    self.assertEqual(control["ticks"], ticks)
                    self.assertEqual(control["attrs"].get("data-score-intervals"), intervals)
                    self.assertIn(f"--score-intervals: {intervals}", control["attrs"].get("style", ""))
                    buttons = {button["text"]: button["attrs"].get("data-score-value") for button in control["buttons"]}
                    self.assertEqual(buttons.get("0"), "0")
                    self.assertEqual(buttons.get("Максимум"), f"{max_score:g}")
                    if has_half:
                        self.assertEqual(buttons.get("Половина"), half_value)
                    else:
                        self.assertNotIn("Половина", buttons)

    def test_score_save_accepts_fractional_escape_hatch_and_rejects_invalid_values(self) -> None:
        self.write_competition("math_2026", title="Math 2026", max_score=50, score_step=5)
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
                "score": "12.5",
            },
            token_path="/competition/math_2026/problem/task_01?model=openai:gpt-5.5",
        )
        self.assertEqual(ok.status_code, 302)
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["evaluation_pool"]["res_a"][0]["score"], 12.5)

        invalid_values = ["-1", "50.1", "nan", "inf", "", "not-a-number"]
        for index, value in enumerate(invalid_values, start=1):
            with self.subTest(value=value):
                response = self.authorized_post(
                    "/score",
                    {
                        "competition_id": "math_2026",
                        "problem_id": "task_01",
                        "run_id": "run_active",
                        "result_id": "res_a",
                        "model_key": "openai:gpt-5.5",
                        "score": value,
                    },
                    token_path="/competition/math_2026/problem/task_01?model=openai:gpt-5.5",
                )
                self.assertEqual(response.status_code, 302, index)
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["evaluation_pool"]["res_a"]), 1)

    def test_datetime_formatter_and_visible_html(self) -> None:
        self.assertEqual(
            format_datetime_parts("2026-06-29T13:24:18.381921Z"),
            {
                "date": "29 июня 2026",
                "time": "13:24",
                "text": "29 июня 2026, 13:24",
                "iso": "2026-06-29T13:24:18.381921Z",
            },
        )
        self.assertEqual(format_datetime_parts("2026-01-09T03:04:59+03:00")["date"], "9 января 2026")
        self.assertEqual(format_datetime_parts("2026-01-09T03:04:59+03:00")["time"], "03:04")
        self.assertEqual(format_datetime_parts("2026-01-09")["text"], "9 января 2026")
        self.assertEqual(format_datetime_parts(None)["text"], "")
        self.assertEqual(format_datetime_parts("")["text"], "")
        self.assertEqual(format_datetime_parts("not-a-date")["text"], "not-a-date")

        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(timestamp="2026-06-29T13:24:18.381921Z")
        self.write_score()
        pages = [
            (
                "/competition/math_2026/problem/task_01?model=openai:gpt-5.5",
                "2026-06-29T13:24:18.381921Z",
                "29 июня 2026",
                "13:24",
            ),
            (
                "/competition/math_2026/problem/task_01/anonymous?seed=fixed&n=1",
                "2026-06-20T00:00:00Z",
                "20 июня 2026",
                "00:00",
            ),
            (
                "/competition/math_2026/checks",
                "2026-06-20T00:00:00Z",
                "20 июня 2026",
                "00:00",
            ),
            (
                "/competition/math_2026/stats?model=openai:gpt-5.5",
                "2026-06-29T13:24:18.381921Z",
                "29 июня 2026",
                "13:24",
            ),
        ]
        for path, raw_timestamp, date_text, time_text in pages:
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                visible = VisibleTextParser()
                visible.feed(html)
                time_parser = HumanTimeParser()
                time_parser.feed(html)
                self.assertIn(raw_timestamp, html)
                self.assertNotIn(raw_timestamp, visible.text)
                self.assertNotIn(raw_timestamp[11:19], visible.text)
                self.assertNotIn("381921", visible.text)
                self.assertTrue(any(item["date"] == date_text for item in time_parser.times))
                self.assertTrue(any(item["time"] == time_text for item in time_parser.times))

    def test_validate_problem_data_accepts_optional_score_step_and_rejects_invalid_values(self) -> None:
        competition_dir = self.write_competition("math_2026", title="Math 2026", max_score=10, score_step=5)
        findings: list[Finding] = []
        validate_competition_dir(competition_dir, findings)
        self.assertFalse([finding for finding in findings if finding.level == "ERROR"])

        write_json(
            competition_dir / "competition.json",
            {
                "schema_version": 1,
                "id": "math_2026",
                "title": "Math 2026",
                "metadata": {"score_step": 11},
            },
        )
        findings = []
        validate_competition_dir(competition_dir, findings)
        self.assertTrue(any("score_step" in finding.message for finding in findings))

    def test_active_model_catalog_contains_only_strong_models(self) -> None:
        expected = {
            "openai:gpt-5.5",
            "openai:gpt-5.4-mini",
            "anthropic:claude-opus-4-8",
            "anthropic:claude-haiku-4-5-20251001",
            "deepseek:deepseek-v4-pro",
            "deepseek:deepseek-v4-flash",
            "google:gemini-3.1-pro-preview",
            "google:gemini-3.5-flash",
            "gigachat:GigaChat-2-Max",
            "gigachat:GigaChat-2",
            "xai:grok-4.3",
            "xai:grok-build-0.1",
            "zai:glm-5.2",
            "zai:glm-4.7-flash",
            "yandexgpt:yandexgpt-5.1",
            "yandexgpt:yandexgpt-5-lite",
        }
        expected_order = [
            "anthropic:claude-opus-4-8",
            "anthropic:claude-haiku-4-5-20251001",
            "deepseek:deepseek-v4-pro",
            "deepseek:deepseek-v4-flash",
            "google:gemini-3.1-pro-preview",
            "google:gemini-3.5-flash",
            "gigachat:GigaChat-2-Max",
            "gigachat:GigaChat-2",
            "xai:grok-4.3",
            "xai:grok-build-0.1",
            "zai:glm-5.2",
            "zai:glm-4.7-flash",
            "openai:gpt-5.5",
            "openai:gpt-5.4-mini",
            "yandexgpt:yandexgpt-5.1",
            "yandexgpt:yandexgpt-5-lite",
        ]
        self.assertEqual(set(runner.active_model_specs()), expected)
        self.assertEqual(set(configured_model_columns()), expected)
        self.assertEqual(runner.active_model_specs(), expected_order)
        self.assertEqual(runner.requested_aliases("all"), expected_order)
        self.assertEqual(len(runner.requested_aliases("all")), 16)
        self.assertEqual(len(set(runner.requested_aliases("all"))), 16)
        for alias, provider in {
            "gemini": "google",
            "google": "google",
            "grok": "xai",
            "xai": "xai",
            "glm": "zai",
            "zai": "zai",
            "zhipu": "zai",
        }.items():
            self.assertEqual(runner.provider_for_alias(alias), provider)

    def test_competition_catalog_groups_model_columns_by_provider_order(self) -> None:
        from models.claude.versions import VERSIONS as CLAUDE_VERSIONS
        from models.deepseek.versions import VERSIONS as DEEPSEEK_VERSIONS
        from models.gemini.versions import VERSIONS as GEMINI_VERSIONS
        from models.gigachat.versions import VERSIONS as GIGACHAT_VERSIONS
        from models.grok.versions import VERSIONS as GROK_VERSIONS
        from models.glm.versions import VERSIONS as GLM_VERSIONS
        from models.gpt.versions import VERSIONS as GPT_VERSIONS
        from models.yandexgpt.versions import VERSIONS as YANDEX_VERSIONS

        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        competition = catalog["competition_map"]["math_2026"]

        expected_groups = [
            ("anthropic", "Claude", list(CLAUDE_VERSIONS)),
            ("deepseek", "DeepSeek", list(DEEPSEEK_VERSIONS)),
            ("google", "Gemini", list(GEMINI_VERSIONS)),
            ("gigachat", "GigaChat", list(GIGACHAT_VERSIONS)),
            ("xai", "Grok", list(GROK_VERSIONS)),
            ("zai", "GLM", list(GLM_VERSIONS)),
            ("openai", "OpenAI", list(GPT_VERSIONS)),
            ("yandexgpt", "Яндекс", list(YANDEX_VERSIONS)),
        ]
        groups = competition["model_groups"]
        self.assertEqual([group["provider"] for group in groups], [item[0] for item in expected_groups])
        self.assertEqual([group["label"] for group in groups], [item[1] for item in expected_groups])
        self.assertTrue(all(len(group["models"]) == 2 for group in groups))
        for group, (provider, _label, versions) in zip(groups, expected_groups, strict=True):
            self.assertEqual([model["model_id"] for model in group["models"]], versions)
            self.assertEqual([model["model_key"] for model in group["models"]], [f"{provider}:{model}" for model in versions])

        flat_from_groups = [model["model_key"] for group in groups for model in group["models"]]
        self.assertEqual([column["model_key"] for column in competition["model_columns"]], flat_from_groups)
        problem = competition["problems"]["task_01"]
        self.assertEqual([state["model_key"] for state in problem["model_states"]], flat_from_groups)

    def test_model_short_labels_and_unknown_fallback(self) -> None:
        columns = configured_model_columns()
        expected = {
            "claude-opus-4-8": "Opus 4.8",
            "claude-haiku-4-5-20251001": "Haiku 4.5",
            "deepseek-v4-pro": "V4 Pro",
            "deepseek-v4-flash": "V4 Flash",
            "gemini-3.1-pro-preview": "3.1 Pro",
            "gemini-3.5-flash": "3.5 Flash",
            "GigaChat-2-Max": "2 Max",
            "GigaChat-2": "2",
            "grok-4.3": "4.3",
            "grok-build-0.1": "Build 0.1",
            "glm-5.2": "5.2",
            "glm-4.7-flash": "4.7 Flash",
            "gpt-5.5": "GPT-5.5",
            "gpt-5.4-mini": "GPT-5.4 mini",
            "yandexgpt-5.1": "5.1",
            "yandexgpt-5-lite": "5 Lite",
        }
        actual = {column["model_id"]: column["short_label"] for column in columns.values()}
        for model_id, short_label in expected.items():
            self.assertEqual(actual[model_id], short_label)

        fallback = model_presentation("future_provider", "future-model_x")
        self.assertEqual(fallback["provider_label"], "future_provider")
        self.assertEqual(fallback["provider_order"], 8)
        self.assertEqual(fallback["model_order"], 10000)
        self.assertTrue(fallback["short_label"])
        self.assertEqual(fallback["short_label"], "future model x")

    def test_competition_matrix_header_groups_models_and_tooltips(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        html = self.client.get("/competition/math_2026").get_data(as_text=True)
        parser = CompetitionMatrixParser()
        parser.feed(html)

        self.assertEqual(len(parser.header_rows), 2)
        provider_headers = parser.header_rows[0][1:]
        self.assertEqual([cell["attrs"].get("scope") for cell in provider_headers], ["colgroup"] * 8)
        self.assertEqual([cell["attrs"].get("colspan") for cell in provider_headers], ["2"] * 8)
        self.assertEqual([cell["text"] for cell in provider_headers], ["Claude", "DeepSeek", "Gemini", "GigaChat", "Grok", "GLM", "OpenAI", "Яндекс"])

        expected_links = [
            ("anthropic:claude-opus-4-8", "claude-opus-4-8", "Opus 4.8"),
            ("anthropic:claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001", "Haiku 4.5"),
            ("deepseek:deepseek-v4-pro", "deepseek-v4-pro", "V4 Pro"),
            ("deepseek:deepseek-v4-flash", "deepseek-v4-flash", "V4 Flash"),
            ("google:gemini-3.1-pro-preview", "gemini-3.1-pro-preview", "3.1 Pro"),
            ("google:gemini-3.5-flash", "gemini-3.5-flash", "3.5 Flash"),
            ("gigachat:GigaChat-2-Max", "GigaChat-2-Max", "2 Max"),
            ("gigachat:GigaChat-2", "GigaChat-2", "2"),
            ("xai:grok-4.3", "grok-4.3", "4.3"),
            ("xai:grok-build-0.1", "grok-build-0.1", "Build 0.1"),
            ("zai:glm-5.2", "glm-5.2", "5.2"),
            ("zai:glm-4.7-flash", "glm-4.7-flash", "4.7 Flash"),
            ("openai:gpt-5.5", "gpt-5.5", "GPT-5.5"),
            ("openai:gpt-5.4-mini", "gpt-5.4-mini", "GPT-5.4 mini"),
            ("yandexgpt:yandexgpt-5.1", "yandexgpt-5.1", "5.1"),
            ("yandexgpt:yandexgpt-5-lite", "yandexgpt-5-lite", "5 Lite"),
        ]
        self.assertEqual([link["text"] for link in parser.model_links], [item[2] for item in expected_links])
        for link, (model_key, model_id, short_label) in zip(parser.model_links, expected_links, strict=True):
            attrs = link["attrs"]
            self.assertEqual(attrs.get("href"), f"/competition/math_2026/stats?model={model_key}")
            self.assertEqual(attrs.get("title"), model_id)
            self.assertIn(model_id, attrs.get("aria-label", ""))
            self.assertIn(short_label, attrs.get("aria-label", ""))
            tooltip_id = attrs.get("aria-describedby", "")
            self.assertIn(tooltip_id, parser.tooltips)
            self.assertIn(model_id, parser.tooltips[tooltip_id])
        self.assertTrue(all(tooltip["attrs"].get("role") == "tooltip" for row in parser.header_rows for cell in row for tooltip in cell["tooltips"]))

    def test_competition_matrix_task_cell_shows_only_problem_title(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        html = self.client.get("/competition/math_2026").get_data(as_text=True)
        matrix = CompetitionMatrixParser()
        matrix.feed(html)
        visible = VisibleTextParser()
        visible.feed(html)

        self.assertEqual(len(matrix.task_links), 1)
        self.assertEqual(matrix.task_links[0]["text"], "1. Task One")
        self.assertEqual(matrix.task_links[0]["attrs"].get("href"), "/competition/math_2026/problem/task_01/anonymous")
        self.assertIn("1. Task One", visible.text)
        self.assertNotIn("анонимная проверка", visible.text)
        self.assertNotIn("task_01", visible.text)
        self.assertNotIn("максимум", visible.text)

    def test_competition_matrix_compact_structure_and_css_contract(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        html = self.client.get("/competition/math_2026").get_data(as_text=True)
        parser = CompetitionMatrixParser()
        parser.feed(html)

        self.assertIn("competition-matrix-wrap", parser.wrapper_classes)
        self.assertIn("competition-matrix", parser.table_attrs.get("class", ""))
        self.assertEqual(sum("competition-matrix-problem-column" in classes for classes in parser.cols), 1)
        self.assertEqual(sum("competition-matrix-model-column" in classes for classes in parser.cols), 16)
        self.assertNotIn("max-height", parser.table_attrs.get("style", ""))
        self.assertEqual(len(parser.body_rows), 1)
        self.assertEqual(len(parser.body_rows[0]["model_cell_hrefs"]), 16)

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        expected_order = [column["model_key"] for column in catalog["competition_map"]["math_2026"]["model_columns"]]
        self.assertEqual(
            parser.body_rows[0]["model_cell_hrefs"],
            [f"/competition/math_2026/problem/task_01?model={model_key}" for model_key in expected_order],
        )

        css = Path("scoring/templates/base.html").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.competition-matrix-wrap\s*\{[^}]*max-height:\s*none")
        self.assertRegex(css, r"\.competition-matrix\s*\{[^}]*width:\s*max-content")
        self.assertRegex(css, r"\.competition-matrix\s*\{[^}]*86px \* 16")
        self.assertRegex(css, r"\.competition-matrix th:first-child,\s*\.competition-matrix td:first-child\s*\{[^}]*min-width:\s*200px")
        self.assertRegex(css, r"\.competition-matrix-model-column\s*\{[^}]*width:\s*86px")
        self.assertRegex(css, r"\.competition-matrix \.matrix-cell\s*\{[^}]*min-width:\s*0")
        self.assertRegex(css, r"\.competition-matrix \.matrix-cell\s*\{[^}]*min-height:\s*44px")
        self.assertRegex(css, r"\.model-header:hover \.model-header-tooltip")
        self.assertRegex(css, r"\.model-header-link:focus-visible \+ \.model-header-tooltip")
        self.assertRegex(css, r"button,\s*\.button\s*\{[^}]*transition:")
        self.assertRegex(css, r"button:hover,\s*\.button:hover")
        self.assertRegex(css, r"button:active,\s*\.button:active")
        self.assertRegex(css, r"button:focus-visible,\s*\.button:focus-visible")
        self.assertRegex(css, r"button:disabled,\s*button\[aria-disabled=\"true\"\],\s*\.button\[aria-disabled=\"true\"\]")
        self.assertIn("document.body.appendChild(tooltip)", css)
        self.assertIn("model-header-tooltip.is-portal", css)

    def test_checks_matrix_uses_common_markup_and_compact_cells(self) -> None:
        competition_dir = self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        problem_specs = [
            ("task_02", 2, "Only Error"),
            ("task_03", 3, "Unscored"),
            ("task_04", 4, "Zero Score"),
            ("task_05", 5, "Partial Score"),
            ("task_06", 6, "Full Score"),
        ]
        for problem_id, number, title in problem_specs:
            write_json(
                competition_dir / f"{problem_id}.json",
                {
                    "schema_version": 1,
                    "id": problem_id,
                    "number": number,
                    "title": title,
                    "statement": title,
                    "metadata": {"max_score": 10},
                },
            )
        self.write_run(problem_id="task_02", run_id="run_error", result_id="res_error", answer="", error="provider failed")
        self.write_run(problem_id="task_03", run_id="run_unscored", result_id="res_unscored")
        self.write_run(problem_id="task_04", run_id="run_zero", result_id="res_zero")
        self.write_score(problem_id="task_04", run_id="run_zero", result_id="res_zero", score=0)
        self.write_run(problem_id="task_05", run_id="run_partial", result_id="res_partial")
        self.write_score(problem_id="task_05", run_id="run_partial", result_id="res_partial", score=5)
        self.write_run(problem_id="task_06", run_id="run_full", result_id="res_full")
        self.write_score(problem_id="task_06", run_id="run_full", result_id="res_full", score=10)

        overview_html = self.client.get("/competition/math_2026").get_data(as_text=True)
        overview = CompetitionMatrixParser()
        overview.feed(overview_html)
        checks_html = self.client.get("/competition/math_2026/checks").get_data(as_text=True)
        checks = CompetitionMatrixParser()
        checks.feed(checks_html)

        self.assertEqual([cell["text"] for cell in checks.header_rows[0]], [cell["text"] for cell in overview.header_rows[0]])
        self.assertEqual([link["text"] for link in checks.model_links], [link["text"] for link in overview.model_links])
        self.assertEqual(
            [link["attrs"].get("href") for link in checks.model_links],
            [link["attrs"].get("href") for link in overview.model_links],
        )
        self.assertIn("competition-matrix-wrap", checks.wrapper_classes)
        self.assertIn("competition-matrix", checks.table_attrs.get("class", ""))
        self.assertEqual(sum("competition-matrix-problem-column" in classes for classes in checks.cols), 1)
        self.assertEqual(sum("competition-matrix-model-column" in classes for classes in checks.cols), 16)

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        model_keys = [column["model_key"] for column in catalog["competition_map"]["math_2026"]["model_columns"]]
        openai_index = model_keys.index("openai:gpt-5.5")
        self.assertTrue(all(len(row["matrix_cells"]) == len(model_keys) for row in checks.body_rows))
        self.assertEqual([link["text"] for link in checks.task_links], ["Task One", "Only Error", "Unscored", "Zero Score", "Partial Score", "Full Score"])
        self.assertTrue(all(link["attrs"].get("href", "").endswith("/anonymous") for link in checks.task_links))
        aggregate_problem_text = " ".join(row["cells"][0]["text"] for row in checks.body_rows)
        self.assertNotIn("task_01", aggregate_problem_text)
        self.assertNotIn("1. Task One", aggregate_problem_text)

        not_run_cell = checks.body_rows[0]["matrix_cells"][0]
        error_cell = checks.body_rows[1]["matrix_cells"][openai_index]
        unscored_cell = checks.body_rows[2]["matrix_cells"][openai_index]
        zero_cell = checks.body_rows[3]["matrix_cells"][openai_index]
        partial_cell = checks.body_rows[4]["matrix_cells"][openai_index]
        full_cell = checks.body_rows[5]["matrix_cells"][openai_index]

        expectations = [
            (not_run_cell, "cell-not-run", ""),
            (error_cell, "cell-error", ""),
            (unscored_cell, "cell-unscored", "?"),
            (zero_cell, "cell-zero", "0"),
            (partial_cell, "cell-partial", "5"),
            (full_cell, "cell-full", "10"),
        ]
        for cell, css_class, text in expectations:
            with self.subTest(css_class=css_class):
                self.assertIn(css_class, cell["attrs"].get("class", ""))
                self.assertEqual(cell["text"], text)
                self.assertNotIn("/ 10", cell["text"])
                self.assertNotIn("проверок", cell["text"])
                self.assertNotIn("%", cell["text"])
                self.assertIn("data-avg-class", cell["attrs"])
                self.assertIn("data-max-class", cell["attrs"])
                self.assertIn("data-min-class", cell["attrs"])
        self.assertNotIn("Ждёт", checks_html)
        self.assertNotIn("Макс.", checks_html)

        overview_expectations = [
            (overview.body_rows[0]["matrix_cells"][0], "cell-not-run", ""),
            (overview.body_rows[1]["matrix_cells"][openai_index], "cell-error", ""),
            (overview.body_rows[2]["matrix_cells"][openai_index], "cell-unscored", "?"),
            (overview.body_rows[3]["matrix_cells"][openai_index], "cell-zero", "0"),
            (overview.body_rows[4]["matrix_cells"][openai_index], "cell-partial", "5"),
            (overview.body_rows[5]["matrix_cells"][openai_index], "cell-full", "10"),
        ]
        for cell, css_class, text in overview_expectations:
            with self.subTest(overview_class=css_class):
                self.assertIn(css_class, cell["attrs"].get("class", ""))
                self.assertEqual(cell["text"], text)
        self.assertNotIn("Ждёт", overview_html)
        self.assertNotIn(">Частично<", overview_html)
        self.assertNotIn("Макс.", overview_html)

    def test_problem_page_does_not_show_legacy_cost_calculator(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")

        response = self.client.get("/competition/math_2026/problem/task_01?max_tokens=2048&runs=3")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertNotIn(joined("Калькулятор ", "стоимости"), html)
        self.assertNotIn("потолок 2048 output-токенов", html)
        self.assertNotIn("Пересчитать", html)
        self.assertNotIn("calculator-form", html)

    def test_cost_calculator_is_removed_from_public_scoring_pages(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(competition_id="math_2026", model_id="gpt-5.5", provider="openai")

        index_response = self.client.get("/")
        competition_response = self.client.get("/competition/math_2026")
        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(competition_response.status_code, 200)

        forbidden = [
            joined("Калькулятор ", "стоимости задач"),
            joined("Стоимость ", "прогона"),
            joined("Послед", "ние:"),
            joined("Все ", "логи:"),
            joined("Про", "гон:"),
            joined("data-", "cost-context"),
            joined("data-", "cost-range"),
            joined("data-", "cost-number"),
            joined("data-", "cost-competition"),
            joined("data-", "cost-actual"),
            joined("data-", "cost-model"),
            joined("data-", "cost-total"),
            joined("cost-", "run-grid"),
            joined("cost-", "disclosure"),
            joined("cost-", "controls"),
        ]
        for html in (index_response.get_data(as_text=True), competition_response.get_data(as_text=True)):
            for needle in forbidden:
                with self.subTest(needle=needle):
                    self.assertNotIn(needle, html)
        self.assertNotIn(joined("scoring.", "cost_estimator"), sys.modules)

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
        parser = CompetitionMatrixParser()
        parser.feed(html)
        budget_link = next(link for link in parser.model_links if link["attrs"].get("title") == "gpt-5.4-mini")
        self.assertEqual(budget_link["text"], "GPT-5.4 mini")
        self.assertIn("gpt-5.4-mini", budget_link["attrs"].get("aria-label", ""))
        self.assertIn("gpt-5.4-mini", parser.tooltips[budget_link["attrs"]["aria-describedby"]])

    def test_new_provider_columns_exist_without_logs_and_fake_logs_do_not_merge(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        new_models = [
            ("google", "gemini-3.1-pro-preview", "res_gemini_pro"),
            ("google", "gemini-3.5-flash", "res_gemini_flash"),
            ("xai", "grok-4.3", "res_grok"),
            ("xai", "grok-build-0.1", "res_grok_build"),
            ("zai", "glm-5.2", "res_glm_paid"),
            ("zai", "glm-4.7-flash", "res_glm_free"),
        ]
        empty_catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        empty_problem = empty_catalog["competition_map"]["math_2026"]["problems"]["task_01"]
        empty_states = {state["model_key"]: state for state in empty_problem["model_states"]}
        for provider, model_id, _result_id in new_models:
            key = f"{provider}:{model_id}"
            self.assertIn(key, empty_states)
            self.assertTrue(empty_states[key]["configured"])
            self.assertEqual(empty_states[key]["status"], "not_run")
            self.assertEqual(empty_states[key]["cell_text"], "")

        for index, (provider, model_id, result_id) in enumerate(new_models, start=1):
            self.write_run(
                provider=provider,
                model_id=model_id,
                result_id=result_id,
                run_id=f"run_new_{index}",
                answer=f"ANSWER_{result_id}",
            )
        self.write_run(
            provider="xai",
            model_id="grok-code-fast-1",
            result_id="res_grok_legacy",
            run_id="run_grok_legacy",
            answer="ANSWER_GROK_LEGACY_ALIAS",
        )

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        problem = catalog["competition_map"]["math_2026"]["problems"]["task_01"]
        states = {state["model_key"]: state for state in problem["model_states"]}
        for provider, model_id, result_id in new_models:
            key = f"{provider}:{model_id}"
            self.assertEqual(states[key]["attempt_count"], 1 if model_id != "grok-build-0.1" else 2)
            answers = [attempt["result"]["answer"] for attempt in states[key]["attempts"]]
            if model_id == "grok-build-0.1":
                self.assertIn("ANSWER_GROK_LEGACY_ALIAS", answers)
            self.assertTrue(any(result_id in attempt["result_id"] for attempt in states[key]["attempts"]))
        self.assertNotIn("xai:grok-code-fast-1", states)

        for key in states:
            response = self.client.get(f"/competition/math_2026/stats?model={key}")
            self.assertEqual(response.status_code, 200, key)

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

    def test_index_card_is_single_accessible_link_with_public_fields(self) -> None:
        self.write_competition(
            "math_2026",
            title="Math 2026",
            date="2026-06-01",
            description="Main card description",
        )
        self.write_run(timestamp="2026-06-20T00:00:00Z")

        html = self.client.get("/").get_data(as_text=True)
        parser = CompetitionCardParser()
        parser.feed(html)
        self.assertEqual(len(parser.cards), 1)
        card = parser.cards[0]
        self.assertEqual(card["tag"], "a")
        self.assertEqual(card["attrs"].get("href"), "/competition/math_2026")
        self.assertEqual(card["nested_links"], 0)
        self.assertFalse(card["onclick"])
        text = card["text"]
        self.assertIn("Math 2026", text)
        self.assertIn("Main card description", text)
        self.assertIn("1 задач", text)
        self.assertIn("1 июня", text)
        self.assertIn('class="competition-grid"', html)
        self.assertIn('class="muted competition-card-description"', html)
        self.assertNotIn("math_2026", text)
        self.assertNotIn("моделей", text)
        self.assertNotIn("ответов", text)
        self.assertNotIn("0 проверено", text)
        self.assertNotIn("Проверено", text)
        self.assertNotIn("Запусков пока нет", text)
        self.assertNotIn("Последний запуск", text)
        self.assertNotIn("2026-06-20T00:00:00Z", html)

    def test_competition_date_filter_formats_russian_date_safely(self) -> None:
        self.assertEqual(competition_date("2026-01-09"), "9 января")
        self.assertEqual(competition_date(None), "")
        self.assertEqual(competition_date("not-a-date"), "not-a-date")

        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn(">2026<", html)
        self.assertIn("1 июня", html)
        self.assertNotIn("2026-06-01", html)

    def test_index_card_description_hides_full_name_prefix(self) -> None:
        self.assertEqual(
            competition_card_description("Полное название: Очень длинное название. Краткое описание."),
            "Краткое описание.",
        )
        self.assertEqual(competition_card_description("Полное название: Только полное название"), "")
        self.write_competition(
            "math_2026",
            title="Math 2026",
            date="2026-06-01",
            description="Полное название: Очень длинное название. Краткое описание.",
        )

        html = self.client.get("/").get_data(as_text=True)
        parser = CompetitionCardParser()
        parser.feed(html)
        self.assertEqual(len(parser.cards), 1)
        text = parser.cards[0]["text"]
        self.assertIn("Краткое описание.", text)
        self.assertNotIn("Полное название", text)
        self.assertNotIn("Очень длинное название", text)

    def test_index_hides_competitions_without_year_but_direct_url_works(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_competition("sandbox", title="Practice Set", date=None)

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Math 2026", html)
        self.assertNotIn("Practice Set", html)
        self.assertNotIn("Без года", html)

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        self.assertIn(None, [group["year"] for group in catalog["competition_groups"]])
        self.assertIn("sandbox", catalog["competition_map"])
        self.assertEqual(self.client.get("/competition/sandbox").status_code, 200)

    def test_index_empty_after_hiding_yearless_competitions(self) -> None:
        self.write_competition("sandbox", title="Practice Set", date=None)

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Соревнования не найдены.", html)
        self.assertNotIn("Practice Set", html)

    def test_index_progress_empty_state(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 0, "unreviewed": 0, "not_run": total},
        )
        self.assertEqual(progress["bar"]["attrs"]["aria-valuemax"], str(total))
        self.assertEqual(progress["bar"]["attrs"]["aria-valuenow"], "0")
        self.assertIn(
            f"Проверено 0, ожидает проверки 0, не запущено {total}",
            progress["bar"]["attrs"]["aria-valuetext"],
        )
        self.assertEqual(progress["bar"]["attrs"]["aria-label"], "Прогресс проверки")
        self.assertEqual(progress["summaries"], [])
        self.assertNotIn(f"Проверено 0, ожидает проверки 0, не запущено {total}", progress["visible_text"])
        self.assertNotIn("competition-progress-summary", progress["html"])
        self.assertNotIn("Запусков пока нет", progress["html"])
        self.assertNotIn("competition-progress-fill", progress["html"])

    def test_index_progress_unreviewed_state(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 0, "unreviewed": 1, "not_run": total - 1},
        )
        self.assertEqual(sum(progress["counts"].values()), total)
        self.assertEqual(progress["bar"]["attrs"]["aria-valuemax"], str(total))
        self.assertEqual(progress["bar"]["attrs"]["aria-valuenow"], "0")
        self.assertIn(
            f"Проверено 0, ожидает проверки 1, не запущено {total - 1}",
            progress["bar"]["attrs"]["aria-valuetext"],
        )
        self.assertEqual(progress["summaries"], [])
        self.assertNotIn(f"Проверено 0, ожидает проверки 1, не запущено {total - 1}", progress["visible_text"])

    def test_index_progress_empty_answer_counts_as_not_run(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(answer="", error="provider returned no visible output")

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 0, "unreviewed": 0, "not_run": total},
        )
        self.assertEqual(sum(progress["counts"].values()), total)
        self.assertIn(
            f"Проверено 0, ожидает проверки 0, не запущено {total}",
            progress["bar"]["attrs"]["aria-valuetext"],
        )
        self.assertEqual(progress["summaries"], [])
        self.assertNotIn(f"Проверено 0, ожидает проверки 0, не запущено {total}", progress["visible_text"])

    def test_index_progress_partially_reviewed_state(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        columns = self.active_model_columns()
        reviewed_column, unreviewed_column = columns[0], columns[1]
        self.write_run(
            run_id="run_reviewed",
            result_id="res_reviewed",
            provider=reviewed_column["provider"],
            model_id=reviewed_column["model_id"],
            timestamp="2026-06-20T00:00:00Z",
        )
        self.write_score(
            run_id="run_reviewed",
            result_id="res_reviewed",
            model_key=reviewed_column["model_key"],
            model=reviewed_column["model_id"],
        )
        self.write_run(
            run_id="run_unreviewed",
            result_id="res_unreviewed",
            provider=unreviewed_column["provider"],
            model_id=unreviewed_column["model_id"],
            timestamp="2026-06-21T00:00:00Z",
        )

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 1, "unreviewed": 1, "not_run": total - 2},
        )
        self.assertEqual(sum(progress["counts"].values()), total)
        self.assertEqual(progress["bar"]["attrs"]["aria-valuenow"], "1")
        self.assertIn(
            f"Проверено 1, ожидает проверки 1, не запущено {total - 2}",
            progress["bar"]["attrs"]["aria-valuetext"],
        )
        self.assertEqual(progress["summaries"], [])
        self.assertNotIn(f"Проверено 1, ожидает проверки 1, не запущено {total - 2}", progress["visible_text"])

    def test_index_progress_fully_reviewed_state(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        for index, column in enumerate(self.active_model_columns()):
            run_id = f"run_{index}"
            result_id = f"res_{index}"
            self.write_run(
                run_id=run_id,
                result_id=result_id,
                provider=column["provider"],
                model_id=column["model_id"],
                timestamp=f"2026-06-20T00:00:{index:02d}Z",
            )
            self.write_score(
                run_id=run_id,
                result_id=result_id,
                model_key=column["model_key"],
                model=column["model_id"],
            )

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": total, "unreviewed": 0, "not_run": 0},
        )
        self.assertEqual(sum(progress["counts"].values()), total)
        self.assertEqual(progress["bar"]["attrs"]["aria-valuenow"], str(total))
        self.assertIn(
            f"Проверено {total}, ожидает проверки 0, не запущено 0",
            progress["bar"]["attrs"]["aria-valuetext"],
        )
        self.assertEqual(progress["summaries"], [])
        self.assertNotIn(f"Проверено {total}, ожидает проверки 0, не запущено 0", progress["visible_text"])

    def test_index_progress_multiple_attempts_count_as_one_cell(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(run_id="run_a", result_id="res_a", timestamp="2026-06-20T00:00:00Z")
        self.write_run(run_id="run_b", result_id="res_b", timestamp="2026-06-21T00:00:00Z")

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 0, "unreviewed": 1, "not_run": total - 1},
        )
        self.assertEqual(sum(progress["counts"].values()), total)

    def test_index_progress_other_reviewer_score_does_not_review_for_current_user(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        self.write_score(evaluator="other-reviewer")

        progress = self.index_progress()
        total = self.total_matrix_cells()
        self.assertEqual(
            progress["counts"],
            {"reviewed": 0, "unreviewed": 1, "not_run": total - 1},
        )
        self.assertEqual(progress["bar"]["attrs"]["aria-valuenow"], "0")


if __name__ == "__main__":
    unittest.main()

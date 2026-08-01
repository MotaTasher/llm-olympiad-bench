from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from models.kimi import KimiModel


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, object]) -> None:
        self.status_code = status_code
        self._data = data
        self.ok = status_code < 400
        self.text = "response body"

    def json(self) -> dict[str, object]:
        return self._data


class KimiAdapterTests(unittest.TestCase):
    def test_k3_request_is_text_only_and_uses_current_completion_parameter(self) -> None:
        calls: list[dict[str, object]] = []

        def post(*_args: object, **kwargs: object) -> FakeResponse:
            calls.append(kwargs)
            return FakeResponse(
                200,
                {
                    "id": "cmpl-test",
                    "model": "kimi-k3",
                    "choices": [{"finish_reason": "stop", "message": {"content": "solution"}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 200,
                        "total_tokens": 300,
                        "completion_tokens_details": {"reasoning_tokens": 50},
                    },
                },
            )

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key", "KIMI_TEMPERATURE": "1"}, clear=False), patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)}):
            result = KimiModel().solve("Solve this", max_tokens=256_000)

        payload = calls[0]["json"]
        self.assertEqual(payload["model"], "kimi-k3")
        self.assertEqual(payload["max_completion_tokens"], 256_000)
        self.assertEqual(payload["temperature"], 1.0)
        self.assertNotIn("max_tokens", payload)
        self.assertFalse({"tools", "tool_choice", "functions", "function_call", "web_search_options"} & set(payload))
        self.assertEqual(result.answer, "solution")
        self.assertEqual(result.usage["reasoning_tokens"], 50)
        self.assertAlmostEqual(result.cost_usd, 0.0033)

    def test_api_error_is_preserved_without_credentials(self) -> None:
        def post(*_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse(400, {"error": {"type": "invalid_request_error", "message": "bad parameter"}})

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key", "KIMI_TEMPERATURE": "1"}, clear=False), patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)}):
            result = KimiModel().solve("Solve this", max_tokens=256_000)

        self.assertIn("bad parameter", result.error or "")
        self.assertEqual(result.raw_response["error"]["type"], "invalid_request_error")


if __name__ == "__main__":
    unittest.main()

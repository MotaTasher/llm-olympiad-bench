from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import patch

from models.common import SYSTEM_PROMPT
from models.grok import GrokModel
from models.grok.versions import VERSIONS
from scoring.repository import canonical_model_key, configured_model_columns


class FakeUsageDetails:
    reasoning_tokens = 5
    cached_tokens = 4


class FakeUsage:
    input_tokens = 10
    output_tokens = 20
    total_tokens = 30
    output_tokens_details = FakeUsageDetails()
    input_tokens_details = FakeUsageDetails()


class FakeResponse:
    id = "xai-resp-1"
    model = "grok-4.3"
    created_at = 123
    usage = FakeUsage()
    output_text = "GROK_ANSWER"
    cost_in_usd_ticks = 123_000_000

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "created_at": self.created_at,
            "status": "completed",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 5},
                "input_tokens_details": {"cached_tokens": 4},
            },
            "output": [{"type": "message", "content": [{"type": "output_text", "text": self.output_text}]}],
            "cost_in_usd_ticks": self.cost_in_usd_ticks,
            "Authorization": "Bearer secret",
        }


class FakeResponses:
    calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeOpenAI:
    last_client = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.responses = FakeResponses()
        FakeOpenAI.last_client = self


class GrokAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeResponses.calls = []

    def fake_openai_module(self, client_class=FakeOpenAI):
        return patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=client_class)})

    def test_default_override_versions_and_grok_43_reasoning(self) -> None:
        self.assertEqual(GrokModel().model_id, VERSIONS[0])
        self.assertEqual(GrokModel(VERSIONS[1]).model_id, VERSIONS[1])
        with self.fake_openai_module(), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-4.3").solve("problem", max_tokens=123)

        call = FakeResponses.calls[0]
        self.assertEqual(FakeOpenAI.last_client.kwargs["base_url"], "https://api.x.ai/v1")
        self.assertEqual(call["model"], "grok-4.3")
        self.assertEqual(call["input"][0]["content"], SYSTEM_PROMPT)
        self.assertEqual(call["input"][1]["content"], "problem")
        self.assertEqual(call["max_output_tokens"], 123)
        self.assertEqual(call["reasoning"]["effort"], "high")
        self.assertTrue(call["store"])
        self.assertNotIn("tools", json.dumps(call).lower())
        self.assertEqual(result.provider, "xai")
        self.assertEqual(result.answer, "GROK_ANSWER")
        self.assertEqual(result.usage["reasoning_tokens"], 5)
        self.assertEqual(result.usage["cached_input_tokens"], 4)
        self.assertEqual(result.cost_usd, 0.0123)
        self.assertFalse(result.cost["estimated"])
        self.assertEqual(result.raw_response["last_response"]["Authorization"], "[REDACTED]")

    def test_build_skips_reasoning_and_legacy_alias_canonicalizes(self) -> None:
        with self.fake_openai_module(), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-code-fast-1").solve("problem", max_tokens=64)
        call = FakeResponses.calls[0]
        self.assertEqual(call["model"], "grok-build-0.1")
        self.assertNotIn("reasoning", call)
        self.assertEqual(result.requested_model_id, "grok-build-0.1")
        self.assertEqual(canonical_model_key("xai", "grok-code-fast-1"), "xai:grok-build-0.1")
        self.assertIn("xai:grok-build-0.1", configured_model_columns())
        self.assertNotIn("xai:grok-code-fast-1", configured_model_columns())

    def test_empty_visible_answer_is_error(self) -> None:
        class EmptyUsageDetails:
            reasoning_tokens = 255
            cached_tokens = 4

        class EmptyUsage:
            input_tokens = 10
            output_tokens = 256
            total_tokens = 266
            output_tokens_details = EmptyUsageDetails()
            input_tokens_details = EmptyUsageDetails()

        class EmptyResponse(FakeResponse):
            usage = EmptyUsage()
            output_text = ""

            def model_dump(self) -> dict:
                data = super().model_dump()
                data["status"] = "incomplete"
                data["incomplete_details"] = {"reason": "max_output_tokens"}
                data["usage"]["output_tokens"] = 256
                data["usage"]["output_tokens_details"]["reasoning_tokens"] = 255
                data["usage"]["total_tokens"] = 266
                return data

        class EmptyResponses(FakeResponses):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return EmptyResponse()

        class EmptyOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.responses = EmptyResponses()

        with self.fake_openai_module(EmptyOpenAI), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-build-0.1").solve("problem", max_tokens=256)

        self.assertTrue(result.error)
        self.assertIn("no visible output", result.error)
        self.assertEqual(result.finish_reason, "max_output_tokens")
        self.assertEqual(result.usage["reasoning_tokens"], 255)

    def test_empty_response_continues_with_previous_response_id(self) -> None:
        class FirstResponse(FakeResponse):
            id = "first-response"
            output_text = ""

        class SecondResponse(FakeResponse):
            id = "second-response"
            output_text = "FINAL"

        class MultiResponses(FakeResponses):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FirstResponse() if len(self.calls) == 1 else SecondResponse()

        class MultiOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.responses = MultiResponses()

        with self.fake_openai_module(MultiOpenAI), patch.dict(
            "os.environ",
            {"XAI_API_KEY": "test-key", "XAI_MAX_OUTPUT_TOKENS_PER_REQUEST": "100"},
            clear=True,
        ):
            result = GrokModel("grok-4.3").solve("problem", max_tokens=200)

        calls = FakeResponses.calls
        self.assertEqual(len(calls), 2)
        self.assertNotIn("previous_response_id", calls[0])
        self.assertEqual(calls[1]["previous_response_id"], "first-response")
        self.assertEqual(result.answer, "FINAL")
        self.assertTrue(result.raw_response["multi_request"]["enabled"])

    def test_exception_and_missing_key_return_error_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            missing = GrokModel("grok-4.3").solve("problem")
        self.assertTrue(missing.error)
        self.assertEqual(missing.provider, "xai")

        class FailingResponses(FakeResponses):
            def create(self, **kwargs):
                raise RuntimeError("boom api_key=hidden")

        class FailingOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.responses = FailingResponses()

        with self.fake_openai_module(FailingOpenAI), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-4.3").solve("problem")
        self.assertTrue(result.error)
        self.assertNotIn("hidden", result.error)


if __name__ == "__main__":
    unittest.main()

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
    prompt_tokens = 10
    completion_tokens = 20
    total_tokens = 30
    completion_tokens_details = FakeUsageDetails()
    prompt_tokens_details = FakeUsageDetails()


class FakeMessage:
    content = "GROK_ANSWER"


class FakeChoice:
    message = FakeMessage()
    finish_reason = "stop"


class FakeResponse:
    id = "xai-resp-1"
    model = "grok-4.3"
    created = 123
    usage = FakeUsage()
    choices = [FakeChoice()]
    cost_in_usd_ticks = 123_000_000

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "created": self.created,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
                "completion_tokens_details": {"reasoning_tokens": 5},
                "prompt_tokens_details": {"cached_tokens": 4},
            },
            "choices": [{"finish_reason": "stop", "message": {"content": "GROK_ANSWER"}}],
            "cost_in_usd_ticks": self.cost_in_usd_ticks,
            "Authorization": "Bearer secret",
        }


class FakeCompletions:
    calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeOpenAI:
    last_client = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.chat = FakeChat()
        FakeOpenAI.last_client = self


class GrokAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeCompletions.calls = []

    def fake_openai_module(self, client_class=FakeOpenAI):
        return patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=client_class)})

    def test_default_override_versions_and_grok_43_reasoning(self) -> None:
        self.assertEqual(GrokModel().model_id, VERSIONS[0])
        self.assertEqual(GrokModel(VERSIONS[1]).model_id, VERSIONS[1])
        with self.fake_openai_module(), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-4.3").solve("problem", max_tokens=123)

        call = FakeCompletions.calls[0]
        self.assertEqual(FakeOpenAI.last_client.kwargs["base_url"], "https://api.x.ai/v1")
        self.assertEqual(call["model"], "grok-4.3")
        self.assertEqual(call["messages"][0]["content"], SYSTEM_PROMPT)
        self.assertEqual(call["messages"][1]["content"], "problem")
        self.assertEqual(call["max_tokens"], 123)
        self.assertEqual(call["extra_body"]["reasoning_effort"], "high")
        self.assertNotIn("tools", json.dumps(call).lower())
        self.assertEqual(result.provider, "xai")
        self.assertEqual(result.answer, "GROK_ANSWER")
        self.assertEqual(result.usage["reasoning_tokens"], 5)
        self.assertEqual(result.usage["cached_input_tokens"], 4)
        self.assertEqual(result.cost_usd, 0.0123)
        self.assertFalse(result.cost["estimated"])
        self.assertEqual(result.raw_response["Authorization"], "[REDACTED]")

    def test_build_skips_reasoning_and_legacy_alias_canonicalizes(self) -> None:
        with self.fake_openai_module(), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-code-fast-1").solve("problem", max_tokens=64)
        call = FakeCompletions.calls[0]
        self.assertEqual(call["model"], "grok-build-0.1")
        self.assertNotIn("extra_body", call)
        self.assertEqual(result.requested_model_id, "grok-build-0.1")
        self.assertEqual(canonical_model_key("xai", "grok-code-fast-1"), "xai:grok-build-0.1")
        self.assertIn("xai:grok-build-0.1", configured_model_columns())
        self.assertNotIn("xai:grok-code-fast-1", configured_model_columns())

    def test_exception_and_missing_key_return_error_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            missing = GrokModel("grok-4.3").solve("problem")
        self.assertTrue(missing.error)
        self.assertEqual(missing.provider, "xai")

        class FailingCompletions(FakeCompletions):
            def create(self, **kwargs):
                raise RuntimeError("boom api_key=hidden")

        class FailingChat:
            def __init__(self) -> None:
                self.completions = FailingCompletions()

        class FailingOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.chat = FailingChat()

        with self.fake_openai_module(FailingOpenAI), patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=True):
            result = GrokModel("grok-4.3").solve("problem")
        self.assertTrue(result.error)
        self.assertNotIn("hidden", result.error)


if __name__ == "__main__":
    unittest.main()

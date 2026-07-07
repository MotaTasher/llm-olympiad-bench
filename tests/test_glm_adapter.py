from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import patch

from models.common import SYSTEM_PROMPT
from models.glm import GLMModel
from models.glm.versions import VERSIONS
from models.pricing import estimate_cost


class FakeUsageDetails:
    reasoning_tokens = 6
    cached_tokens = 3


class FakeUsage:
    prompt_tokens = 12
    completion_tokens = 24
    total_tokens = 36
    completion_tokens_details = FakeUsageDetails()
    prompt_tokens_details = FakeUsageDetails()


class FakeMessage:
    content = "GLM_ANSWER"
    reasoning_content = "hidden reasoning"


class FakeChoice:
    message = FakeMessage()
    finish_reason = "stop"


class FakeResponse:
    id = "zai-resp-1"
    model = "glm-5.2"
    created = 456
    usage = FakeUsage()
    choices = [FakeChoice()]

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "created": self.created,
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 24,
                "total_tokens": 36,
                "completion_tokens_details": {"reasoning_tokens": 6},
                "prompt_tokens_details": {"cached_tokens": 3},
            },
            "choices": [{"finish_reason": "stop", "message": {"content": "GLM_ANSWER", "reasoning_content": "hidden reasoning"}}],
            "api_key": "secret",
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


class GLMAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeCompletions.calls = []

    def fake_openai_module(self, client_class=FakeOpenAI):
        return patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=client_class)})

    def test_default_override_versions_and_glm_52_reasoning(self) -> None:
        self.assertEqual(GLMModel().model_id, VERSIONS[0])
        self.assertEqual(GLMModel(VERSIONS[1]).model_id, VERSIONS[1])
        with self.fake_openai_module(), patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
            result = GLMModel("glm-5.2").solve("problem", max_tokens=123)

        call = FakeCompletions.calls[0]
        self.assertEqual(FakeOpenAI.last_client.kwargs["base_url"], "https://api.z.ai/api/paas/v4/")
        self.assertEqual(call["model"], "glm-5.2")
        self.assertEqual(call["messages"][0]["content"], SYSTEM_PROMPT)
        self.assertEqual(call["messages"][1]["content"], "problem")
        self.assertEqual(call["max_tokens"], 123)
        self.assertEqual(call["extra_body"]["thinking"]["type"], "enabled")
        self.assertEqual(call["extra_body"]["reasoning_effort"], "max")
        self.assertNotIn("tools", json.dumps(call).lower())
        self.assertEqual(result.provider, "zai")
        self.assertEqual(result.answer, "GLM_ANSWER")
        self.assertNotIn("hidden reasoning", result.answer)
        self.assertEqual(result.raw_response["reasoning_content"], "hidden reasoning")
        self.assertEqual(result.raw_response["api_key"], "[REDACTED]")
        self.assertEqual(result.usage["reasoning_tokens"], 6)
        self.assertEqual(result.usage["cached_input_tokens"], 3)

    def test_flash_has_thinking_but_no_reasoning_effort_and_free_rate_is_exact(self) -> None:
        with self.fake_openai_module(), patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
            result = GLMModel("glm-4.7-flash").solve("problem", max_tokens=64)
        call = FakeCompletions.calls[0]
        self.assertEqual(call["model"], "glm-4.7-flash")
        self.assertEqual(call["extra_body"]["thinking"]["type"], "enabled")
        self.assertNotIn("reasoning_effort", call["extra_body"])
        self.assertEqual(result.cost["total"], 0.0)
        self.assertEqual(
            estimate_cost("zai", "glm-4.7-flash", input_tokens=1000, output_tokens=1000)["total"],
            0.0,
        )
        self.assertGreater(
            estimate_cost("zai", "glm-4.7-flashx", input_tokens=1000, output_tokens=1000)["total"],
            0.0,
        )

    def test_empty_visible_answer_is_error(self) -> None:
        class EmptyMessage:
            content = ""
            reasoning_content = "hidden"

        class EmptyChoice:
            message = EmptyMessage()
            finish_reason = "length"

        class EmptyResponse(FakeResponse):
            choices = [EmptyChoice()]

            def model_dump(self) -> dict:
                data = super().model_dump()
                data["choices"] = [
                    {
                        "finish_reason": "length",
                        "message": {"content": "", "reasoning_content": "hidden"},
                    }
                ]
                return data

        class EmptyCompletions(FakeCompletions):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return EmptyResponse()

        class EmptyChat:
            def __init__(self) -> None:
                self.completions = EmptyCompletions()

        class EmptyOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.chat = EmptyChat()

        with self.fake_openai_module(EmptyOpenAI), patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
            result = GLMModel("glm-5.2").solve("problem", max_tokens=64)

        self.assertTrue(result.error)
        self.assertIn("no visible output", result.error)
        self.assertEqual(result.finish_reason, "length")

    def test_exception_and_missing_key_return_error_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            missing = GLMModel("glm-5.2").solve("problem")
        self.assertTrue(missing.error)
        self.assertEqual(missing.provider, "zai")

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

        with self.fake_openai_module(FailingOpenAI), patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
            result = GLMModel("glm-5.2").solve("problem")
        self.assertTrue(result.error)
        self.assertNotIn("hidden", result.error)


if __name__ == "__main__":
    unittest.main()

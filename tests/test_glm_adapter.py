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


class FakeStream:
    def __init__(self, response) -> None:
        data = response.model_dump()
        message = data["choices"][0]["message"]
        reasoning = message.get("reasoning_content", "")
        content = message.get("content", "")
        split = max(1, len(reasoning) // 2)
        self.chunks = [
            {
                "id": data["id"],
                "model": data["model"],
                "created": data["created"],
                "choices": [{"delta": {"reasoning_content": reasoning[:split]}, "finish_reason": None}],
            },
            {
                "id": data["id"],
                "model": data["model"],
                "created": data["created"],
                "choices": [{"delta": {"reasoning_content": reasoning[split:], "content": content}, "finish_reason": data["choices"][0]["finish_reason"]}],
            },
            {"id": data["id"], "model": data["model"], "created": data["created"], "choices": [], "usage": data["usage"]},
        ]
        self.closed = False

    def __iter__(self):
        return iter(self.chunks)

    def close(self) -> None:
        self.closed = True


def maybe_stream(kwargs: dict, response):
    return FakeStream(response) if kwargs.get("stream") else response


class FakeCompletions:
    calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return maybe_stream(kwargs, FakeResponse())


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
        self.assertTrue(call["stream"])
        self.assertEqual(call["stream_options"], {"include_usage": True})
        self.assertEqual(call["extra_body"]["thinking"]["type"], "enabled")
        self.assertEqual(call["extra_body"]["reasoning_effort"], "max")
        self.assertFalse(call["extra_body"]["clear_thinking"])
        self.assertNotIn("tools", json.dumps(call).lower())
        self.assertEqual(result.provider, "zai")
        self.assertEqual(result.answer, "GLM_ANSWER")
        self.assertNotIn("hidden reasoning", result.answer)
        self.assertEqual(result.raw_response["last_response"]["reasoning_content"], "hidden reasoning")
        self.assertNotIn("api_key", result.raw_response["last_response"])
        self.assertEqual(result.usage["reasoning_tokens"], 6)
        self.assertEqual(result.usage["cached_input_tokens"], 3)

    def test_flash_has_thinking_but_no_reasoning_effort_and_free_rate_is_exact(self) -> None:
        with self.fake_openai_module(), patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
            result = GLMModel("glm-4.7-flash").solve("problem", max_tokens=64)
        call = FakeCompletions.calls[0]
        self.assertEqual(call["model"], "glm-4.7-flash")
        self.assertFalse(call["stream"])
        self.assertNotIn("stream_options", call)
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
                return maybe_stream(kwargs, EmptyResponse())

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

    def test_empty_response_preserves_reasoning_for_continuation(self) -> None:
        class FirstMessage:
            content = ""
            reasoning_content = "complete unmodified reasoning"

        class FirstChoice:
            message = FirstMessage()
            finish_reason = "length"

        class FirstResponse(FakeResponse):
            id = "first-response"
            choices = [FirstChoice()]

            def model_dump(self) -> dict:
                data = super().model_dump()
                data["id"] = self.id
                data["choices"] = [{
                    "finish_reason": "length",
                    "message": {
                        "content": "",
                        "reasoning_content": "complete unmodified reasoning",
                    },
                }]
                return data

        class SecondResponse(FakeResponse):
            id = "second-response"

        class MultiCompletions(FakeCompletions):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                response = FirstResponse() if len(self.calls) == 1 else SecondResponse()
                return maybe_stream(kwargs, response)

        class MultiChat:
            def __init__(self) -> None:
                self.completions = MultiCompletions()

        class MultiOpenAI(FakeOpenAI):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.chat = MultiChat()

        with self.fake_openai_module(MultiOpenAI), patch.dict(
            "os.environ",
            {"ZAI_API_KEY": "test-key", "ZAI_MAX_TOKENS_PER_REQUEST": "64"},
            clear=True,
        ):
            result = GLMModel("glm-5.2").solve("problem", max_tokens=128)

        calls = FakeCompletions.calls
        self.assertEqual(len(calls), 2)
        continued_messages = calls[1]["messages"]
        self.assertEqual(continued_messages[-2]["reasoning_content"], "complete unmodified reasoning")
        self.assertEqual(continued_messages[-1]["role"], "user")
        self.assertFalse(calls[1]["extra_body"]["clear_thinking"])
        self.assertEqual(result.answer, "GLM_ANSWER")
        self.assertTrue(result.raw_response["multi_request"]["enabled"])

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

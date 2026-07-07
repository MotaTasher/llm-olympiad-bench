from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from models.claude.claude import (
    ANTHROPIC_CONTINUATION_INPUT,
    ANTHROPIC_NONSTREAMING_MAX_TOKENS,
    ClaudeModel,
)


class FakeUsage:
    input_tokens = 11
    output_tokens = 22
    cache_creation_input_tokens = 3
    cache_read_input_tokens = 4
    output_tokens_details = {"reasoning_tokens": 5}


class FakeBlock:
    type = "text"
    text = "ok"


class FakeMessage:
    id = "msg_1"
    model = "claude-opus-4-8"
    stop_reason = "end_turn"
    usage = FakeUsage()
    content = [FakeBlock()]


class FakeStream:
    def __init__(self, outer):
        self.outer = outer

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get_final_message(self):
        self.outer.stream_final_called = True
        return FakeMessage()


class FakeMessages:
    def __init__(self):
        self.create_called = False
        self.stream_called = False
        self.stream_final_called = False
        self.kwargs = None

    def create(self, **kwargs):
        self.create_called = True
        self.kwargs = kwargs
        return FakeMessage()

    def stream(self, **kwargs):
        self.stream_called = True
        self.kwargs = kwargs
        return FakeStream(self)


class FakeAnthropicClient:
    last_messages = None

    def __init__(self, api_key):
        self.api_key = api_key
        self.messages = FakeMessages()
        FakeAnthropicClient.last_messages = self.messages


class ClaudeAdapterTests(unittest.TestCase):
    def fake_anthropic_module(self):
        module = types.SimpleNamespace(Anthropic=FakeAnthropicClient)
        return patch.dict(sys.modules, {"anthropic": module})

    def test_small_requests_use_non_streaming_messages_create(self) -> None:
        with self.fake_anthropic_module(), patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}, clear=False):
            result = ClaudeModel("claude-opus-4-8").solve("problem", max_tokens=ANTHROPIC_NONSTREAMING_MAX_TOKENS)

        messages = FakeAnthropicClient.last_messages
        self.assertIsNotNone(messages)
        self.assertTrue(messages.create_called)
        self.assertFalse(messages.stream_called)
        self.assertEqual(messages.kwargs["max_tokens"], ANTHROPIC_NONSTREAMING_MAX_TOKENS)
        self.assertEqual(result.answer, "ok")
        self.assertFalse(result.request["stream"])
        self.assertEqual(result.usage["reasoning_tokens"], 5)
        self.assertEqual(result.usage["cached_input_tokens"], 4)
        self.assertEqual(result.usage["cache_creation_input_tokens"], 3)
        self.assertEqual(result.cost["reasoning"], 0.000125)

    def test_large_requests_use_streaming_messages_api(self) -> None:
        with self.fake_anthropic_module(), patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}, clear=False):
            result = ClaudeModel("claude-opus-4-8").solve("problem", max_tokens=128000)

        messages = FakeAnthropicClient.last_messages
        self.assertIsNotNone(messages)
        self.assertFalse(messages.create_called)
        self.assertTrue(messages.stream_called)
        self.assertTrue(messages.stream_final_called)
        self.assertEqual(messages.kwargs["max_tokens"], 128000)
        self.assertEqual(result.answer, "ok")
        self.assertTrue(result.request["stream"])

    def test_large_budget_continues_with_previous_content_blocks_until_text(self) -> None:
        class ThinkingBlock:
            type = "thinking"

            def model_dump(self):
                return {"type": "thinking", "thinking": "work", "signature": "sig"}

        class ThinkingOnlyMessage(FakeMessage):
            id = "msg_thinking"
            stop_reason = "max_tokens"
            content = [ThinkingBlock()]

        class TextMessage(FakeMessage):
            id = "msg_text"
            stop_reason = "end_turn"
            content = [FakeBlock()]

        class SequenceStream:
            def __init__(self, messages, response):
                self.messages = messages
                self.response = response

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def get_final_message(self):
                self.messages.stream_final_called = True
                return self.response

        class SequenceMessages(FakeMessages):
            def __init__(self):
                super().__init__()
                self.responses = [ThinkingOnlyMessage(), TextMessage()]
                self.calls = []

            def create(self, **kwargs):
                self.create_called = True
                self.kwargs = kwargs
                self.calls.append(kwargs)
                return self.responses.pop(0)

            def stream(self, **kwargs):
                self.stream_called = True
                self.kwargs = kwargs
                self.calls.append(kwargs)
                return SequenceStream(self, self.responses.pop(0))

        class SequenceAnthropicClient(FakeAnthropicClient):
            def __init__(self, api_key):
                self.api_key = api_key
                self.messages = SequenceMessages()
                FakeAnthropicClient.last_messages = self.messages

        module = types.SimpleNamespace(Anthropic=SequenceAnthropicClient)
        with patch.dict(sys.modules, {"anthropic": module}), patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}, clear=False):
            result = ClaudeModel("claude-opus-4-8").solve("problem", max_tokens=130000)

        messages = FakeAnthropicClient.last_messages
        self.assertEqual(result.answer, "ok")
        self.assertEqual(len(messages.calls), 2)
        self.assertEqual(messages.calls[0]["max_tokens"], 128000)
        self.assertEqual(messages.calls[1]["max_tokens"], 2000)
        self.assertTrue(messages.stream_called)
        self.assertTrue(messages.create_called)
        self.assertEqual(messages.calls[1]["messages"][-2]["role"], "assistant")
        self.assertEqual(messages.calls[1]["messages"][-2]["content"][0]["type"], "thinking")
        self.assertEqual(messages.calls[1]["messages"][-1], {"role": "user", "content": ANTHROPIC_CONTINUATION_INPUT})
        self.assertEqual(result.raw_response["multi_request"]["requests"], 2)
        self.assertTrue(result.raw_response["multi_request"]["stopped_after_visible_output"])

    def test_empty_visible_answer_is_error(self) -> None:
        class EmptyBlock:
            type = "text"
            text = ""

        class EmptyMessage(FakeMessage):
            content = [EmptyBlock()]
            stop_reason = "max_tokens"

        class EmptyMessages(FakeMessages):
            def create(self, **kwargs):
                self.create_called = True
                self.kwargs = kwargs
                return EmptyMessage()

        class EmptyAnthropicClient(FakeAnthropicClient):
            def __init__(self, api_key):
                self.api_key = api_key
                self.messages = EmptyMessages()
                FakeAnthropicClient.last_messages = self.messages

        module = types.SimpleNamespace(Anthropic=EmptyAnthropicClient)
        with patch.dict(sys.modules, {"anthropic": module}), patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}, clear=False):
            result = ClaudeModel("claude-opus-4-8").solve("problem", max_tokens=64)

        self.assertTrue(result.error)
        self.assertIn("no visible output", result.error)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import json
import os
import sys
import unittest
from pathlib import Path
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import runner
from models.base import SolveResult
from models.common import SYSTEM_PROMPT, code_system_prompt, ensure_text_only_request
from models.rosters import load_roster, roster_specs
from models.pricing import estimate_cost, token_price
from judging.records import extract_source, make_solution, write_solution

SOURCE = '#include <iostream>\nint main() { std::cout << 1; }\n'


class Node(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def model_dump(self):
        return dict(self)


class ModelCallTests(unittest.TestCase):
    def test_openai_continuation_keeps_code_instructions_and_prices_each_request(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return Node(id='step_' + str(len(calls)), status='completed',
                        model='gpt-6-astra', output=[], output_text='' if len(calls) == 1 else SOURCE,
                        usage=Node(input_tokens=150000, output_tokens=10, total_tokens=150010))
        sdk = SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
        prompt = code_system_prompt('cpp')
        with patch.dict(sys.modules, {'openai': sdk}), patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture'}, clear=True):
            result = runner.create_model('openai:gpt-6-astra', system_prompt=prompt).solve('CONDITION_ONLY', max_tokens=256000)
        self.assertIsNone(result.error)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['previous_response_id'], 'step_1')
        self.assertTrue(all(call['instructions'] == prompt for call in calls))
        # Total input exceeds the tier threshold, but neither individual request does.
        self.assertAlmostEqual(result.cost['input'], 3.0)

    def test_current_price_tiers_and_argon_expiry(self):
        for provider, model, threshold, short_rate, long_rate in [
            ('openai', 'gpt-6-astra', 272000, 10, 20),
            ('xai', 'grok-4.7', 200000, 2, 4),
        ]:
            short = estimate_cost(provider, model, input_tokens=threshold, output_tokens=0)
            long = estimate_cost(provider, model, input_tokens=threshold+1, output_tokens=0)
            self.assertAlmostEqual(short['input'], threshold*short_rate/1e6)
            self.assertAlmostEqual(long['input'], (threshold+1)*long_rate/1e6)
        for date, rate in [(datetime(2026, 11, 30, tzinfo=UTC), 2), (datetime(2026, 12, 1, tzinfo=UTC), 4)]:
            with patch('models.pricing.datetime') as clock:
                clock.now.return_value = date
                self.assertEqual(token_price('google', 'gemini-4-argon').input_per_1m, rate)

    def test_source_extraction_and_distinct_run_attribution(self):
        self.assertEqual(extract_source('```python\nprint(1)\n```', 'python'), 'print(1)')
        for answer in ['explanation\n```cpp\nint main() {}\n```', '```python\nprint(1)\n```']:
            with self.assertRaises(ValueError):
                extract_source(answer, 'cpp')
        with TemporaryDirectory() as directory:
            sources = []
            for run in ['run1', 'run2']:
                solution = make_solution(competition_id='cup', task_id='task_01',
                                         author={'type': 'model', 'id': 'gpt', 'name': 'GPT'},
                                         code=SOURCE, language='cpp', origin={'kind': 'model_generation'},
                                         generation={'run_id': run, 'result_id': 'res_' + run, 'model_key': 'openai:gpt-6-astra'})
                write_solution(Path(directory), solution)
                sources.append(solution)
            self.assertNotEqual(sources[0]['id'], sources[1]['id'])
            self.assertEqual(sources[0]['source']['sha256'], sources[1]['source']['sha256'])

    def test_truncated_code_is_logged_but_not_prepared_for_judging(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / 'task_01.md'
            task.write_text('CONDITION_ONLY')
            fake = SimpleNamespace(model_id='gpt-6-astra', solve=lambda *args, **kwargs:
                                   SolveResult('gpt-6-astra', SOURCE, 1, 1, 0, 1, {}, finish_reason='length'))
            with patch('runner.create_model', return_value=fake), patch('runner.print_progress'):
                run = runner.run_problem(problem_file=task, models_value='gpt', logs_dir=root / 'logs',
                                         settings=runner.RunSettings(solution_format='code'), code_solutions_dir=root / 'sources')
            result = run.log['results'][0]
            self.assertIn('before completion', result['error'])
            self.assertNotIn('code_solution_id', result)
            self.assertFalse((root / 'sources').exists())

    def test_all_nine_actual_adapters_build_current_text_only_code_requests(self):
        calls = []
        def response_call(**kwargs):
            calls.append(kwargs)
            return Node(id="response-test", model=kwargs["model"], status="completed", output_text=SOURCE,
                        usage=Node(input_tokens=5, output_tokens=10, total_tokens=15), output=[])
        def chat_call(**kwargs):
            calls.append(kwargs)
            usage = Node(prompt_tokens=5, completion_tokens=10, total_tokens=15)
            if kwargs.get("stream"):
                return iter([Node(id="chat-test", model=kwargs["model"], choices=[Node(delta=Node(content=SOURCE, reasoning_content="thinking"), finish_reason="stop")]),
                             Node(id="chat-test", model=kwargs["model"], choices=[], usage=usage)])
            return Node(id="chat-test", model=kwargs["model"], choices=[Node(message=Node(content=SOURCE), finish_reason="stop")], usage=usage)
        def anthropic_call(**kwargs):
            calls.append(kwargs)
            return Node(id="claude-test", model=kwargs["model"], stop_reason="end_turn",
                        content=[Node(type="text", text=SOURCE)], usage=Node(input_tokens=5, output_tokens=10))
        class MessageStream:
            def __init__(self, **kwargs): self.response = anthropic_call(**kwargs)
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get_final_message(self): return self.response
        def gemini_call(**kwargs):
            calls.append(kwargs)
            return Node(id="gemini-test", model=kwargs["model"], status="completed", output_text=SOURCE,
                        usage=Node(total_input_tokens=5, total_output_tokens=10, total_thought_tokens=2, total_tokens=17))
        class FakeGiga:
            def __init__(self, **kwargs): self.model = kwargs["model"]
            def chat(self, payload): return chat_call(model=self.model, **payload)
        class HTTPResponse:
            ok = True; status_code = 200; text = "fixture"
            def __init__(self, payload): self.payload = payload
            def json(self): return self.payload
            def raise_for_status(self): pass
        def post(url, **kwargs):
            payload = kwargs["json"]; calls.append(payload)
            if "foundationModels" in url:
                return HTTPResponse({"result": {"alternatives": [{"message": {"text": SOURCE}, "status": "ALTERNATIVE_STATUS_FINAL"}],
                                                "usage": {"inputTextTokens": "5", "completionTokens": "10", "totalTokens": "15"}}})
            return HTTPResponse({"model": payload["model"], "choices": [{"message": {"content": SOURCE}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 10}})
        genai = SimpleNamespace(Client=lambda **kwargs: SimpleNamespace(interactions=SimpleNamespace(create=gemini_call)), types=SimpleNamespace(HttpOptions=lambda **kwargs: kwargs))
        modules = {
            "openai": SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=response_call), chat=SimpleNamespace(completions=SimpleNamespace(create=chat_call)))),
            "anthropic": SimpleNamespace(Anthropic=lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=anthropic_call, stream=MessageStream))),
            "google": SimpleNamespace(genai=genai), "google.genai": genai,
            "gigachat": SimpleNamespace(GigaChat=FakeGiga), "requests": SimpleNamespace(post=post),
        }
        environment = {key: "fixture-key" for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ZAI_API_KEY", "KIMI_API_KEY", "YANDEX_API_KEY"]}
        environment.update(YANDEX_FOLDER_ID="fixture-folder", ANTHROPIC_THINKING_BUDGET_TOKENS="0",
                           GIGACHAT_CREDENTIALS=base64.b64encode(b"fixture:secret").decode(),
                           OPENAI_REASONING_EFFORT="high", KIMI_TEMPERATURE="0.1", GEMINI_TEMPERATURE="0.1")
        prompt = code_system_prompt("cpp")
        with patch.dict(os.environ, environment, clear=True), patch.dict(sys.modules, modules):
            for spec in roster_specs(load_roster("flagships-2026-11-05")):
                with self.subTest(spec=spec):
                    start = len(calls)
                    model = runner.create_model(spec, system_prompt=prompt)
                    result = model.solve("CONDITION_ONLY", max_tokens=256000)
                    self.assertIsNone(result.error, result.error)
                    self.assertEqual(result.answer.rstrip(), SOURCE.rstrip())
                    self.assertEqual(result.requested_model_id, spec.split(":", 1)[1])
                    self.assertGreater(len(calls), start)
                    for call in calls[start:]:
                        ensure_text_only_request(call)
                        text = json.dumps(call, ensure_ascii=False)
                        self.assertIn("CONDITION_ONLY", text)
                        self.assertIn(prompt, text)
                        self.assertNotIn(SYSTEM_PROMPT, text)
                    if spec.startswith("google:"):
                        self.assertNotIn("temperature", calls[start]["generation_config"])
                        self.assertLessEqual(calls[start]["generation_config"]["max_output_tokens"], 65536)
                    if spec.startswith("anthropic:"):
                        self.assertEqual(calls[start]['thinking']['type'], 'adaptive')
                    if spec.startswith("deepseek:"):
                        self.assertNotIn("temperature", calls[start])
                        self.assertEqual(calls[start]["extra_body"]["thinking"]["type"], "enabled")
                    if spec.startswith("kimi:"):
                        self.assertNotIn("temperature", calls[start])
                    if spec.startswith("gigachat:"):
                        self.assertEqual(calls[start]["max_tokens"], 8192)
                    if spec.startswith("yandexgpt:"):
                        self.assertEqual(calls[start]["completionOptions"]["maxTokens"], 8000)

    def test_runner_needs_only_statement_and_prepares_an_immutable_source(self):
        for language, source in [("cpp", SOURCE), ("python", 'print(1)\n')]:
            with self.subTest(language=language), TemporaryDirectory() as directory:
                root = Path(directory); competition = root / "cup"; competition.mkdir()
                (competition / "competition.json").write_text(json.dumps({"schema_version": 1, "id": "cup", "title": "Cup", "metadata": {"solution_format": "code", "code_language": language, "model_roster": "flagships-2026-11-05"}}))
                task = competition / "task_01.json"
                task.write_text(json.dumps({"schema_version": 1, "id": "task_01", "statement": "CONDITION_ONLY"}))
                seen = {}
                class FakeModel:
                    model_id = "gpt-6-astra"
                    def solve(self, text, max_tokens=None):
                        seen["condition"] = text
                        return SolveResult(self.model_id, source, 1, 1, 0, 1, {}, finish_reason="stop")
                with patch("runner.create_model", return_value=FakeModel()) as create, patch("runner.print_progress"):
                    run = runner.run_problem(problem_file=task, models_value="gpt", logs_dir=root / "logs", code_solutions_dir=root / "sources")
                self.assertEqual(seen["condition"], "CONDITION_ONLY")
                self.assertEqual(create.call_args.kwargs["system_prompt"], code_system_prompt(language))
                self.assertEqual(run.log["status"], "completed")
                result = run.log["results"][0]
                self.assertTrue(result["code_solution_id"].startswith("code_"))
                artifact = json.loads(next((root / "sources").rglob("*.json")).read_text())
                self.assertEqual(artifact["source"]["code"], source)
                self.assertEqual(artifact["generation"]["result_id"], result["result_id"])
                self.assertEqual(run.log["system_prompt"]["text"], code_system_prompt(language))
                self.assertFalse((root / "judge_jobs").exists())


if __name__ == "__main__":
    unittest.main()

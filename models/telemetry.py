from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


RUN_LOG_SCHEMA_VERSION = 2
SIDECAR_SCHEMA_VERSION = 2
SYSTEM_PROMPT_VERSION = "2026-06-29"

SECRET_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credentials",
    "iam_token",
    "password",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
    "x-api-key",
}

SAFE_TOKEN_KEYS = {
    "billable_output_tokens",
    "cached_input_tokens",
    "cached_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "completion_tokens",
    "completion_tokens_details",
    "completiontokens",
    "completiontokensdetails",
    "draft_max_tokens",
    "final_max_tokens",
    "input_tokens",
    "input_tokens_details",
    "input_tokens_by_modality",
    "inputtokens",
    "inputtokensdetails",
    "inputtexttokens",
    "max_completion_tokens",
    "max_output_tokens",
    "max_output_tokens_per_request",
    "max_output_tokens_total",
    "max_tokens",
    "maxtokens",
    "output_tokens",
    "output_tokens_details",
    "output_tokens_by_modality",
    "outputtokens",
    "outputtokensdetails",
    "prompt_tokens",
    "prompt_tokens_details",
    "prompttokensdetails",
    "reasoning_tokens",
    "reasoningtokens",
    "time_to_first_token_ms",
    "thoughts_token_count",
    "thoughtstokencount",
    "total_cached_tokens",
    "total_input_tokens",
    "total_output_tokens",
    "total_thought_tokens",
    "total_tool_use_tokens",
    "total_tokens",
    "totalcachedtokens",
    "totalinputtokens",
    "totaloutputtokens",
    "totalthoughttokens",
    "totaltokens",
    "totaltoolusetokens",
}

SAFE_ENV_ALLOWLIST = {
    "ANTHROPIC_MAX_TOKENS",
    "ANTHROPIC_THINKING_BUDGET_TOKENS",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MAX_TOKENS",
    "DEEPSEEK_TEMPERATURE",
    "GEMINI_MAX_OUTPUT_TOKENS",
    "GEMINI_TEMPERATURE",
    "GEMINI_THINKING_LEVEL",
    "GEMINI_TIMEOUT_SECONDS",
    "GIGACHAT_MAX_TOKENS",
    "GIGACHAT_REPETITION_PENALTY",
    "GIGACHAT_SCOPE",
    "GIGACHAT_TEMPERATURE",
    "GIGACHAT_TOP_P",
    "GIGACHAT_VERIFY_SSL",
    "OPENAI_MAX_COMPLETION_TOKENS",
    "OPENAI_MAX_RETRIES",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_TIMEOUT_SECONDS",
    "RUB_PER_USD",
    "XAI_BASE_URL",
    "XAI_MAX_OUTPUT_TOKENS",
    "XAI_MAX_RETRIES",
    "XAI_REASONING_EFFORT",
    "XAI_TIMEOUT_SECONDS",
    "YANDEX_MAX_TOKENS",
    "YANDEX_REASONING_MODE",
    "YANDEX_TEMPERATURE",
    "YANDEX_TIMEOUT",
    "ZAI_BASE_URL",
    "ZAI_MAX_RETRIES",
    "ZAI_MAX_TOKENS",
    "ZAI_REASONING_EFFORT",
    "ZAI_TEMPERATURE",
    "ZAI_THINKING",
    "ZAI_TIMEOUT_SECONDS",
}

SAFE_RESPONSE_HEADERS = {
    "anthropic-ratelimit-input-tokens-limit",
    "anthropic-ratelimit-input-tokens-remaining",
    "anthropic-ratelimit-output-tokens-limit",
    "anthropic-ratelimit-output-tokens-remaining",
    "openai-processing-ms",
    "openai-version",
    "x-request-id",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-session-id",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat_z(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def stable_result_id(run_id: str, index: int, alias: str, model_id: str | None = None) -> str:
    seed = f"{run_id}\n{index}\n{alias}\n{model_id or ''}\n{uuid.uuid4().hex}"
    return f"res_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def legacy_result_id(competition_id: str, problem_id: str, run_id: str, index: int, model: str) -> str:
    seed = f"{competition_id}\n{problem_id}\n{run_id}\n{index}\n{model}"
    return f"legacy_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _key_is_secret(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    if normalized in SAFE_TOKEN_KEYS:
        return False
    return any(part in normalized for part in SECRET_KEY_PARTS)


def _redact_url(value: str) -> str:
    if "://" not in value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    query = []
    changed = False
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if _key_is_secret(key):
            query.append((key, "[REDACTED]"))
            changed = True
        else:
            query.append((key, item))
    netloc = parts.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
        changed = True
    if not changed:
        return value
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _key_is_secret(key_text):
                result[key_text] = "[REDACTED]"
            elif key_text.lower() in {"headers", "response_headers", "x_headers"} and isinstance(item, dict):
                result[key_text] = {
                    str(header): redact(header_value)
                    for header, header_value in item.items()
                    if str(header).lower() in SAFE_RESPONSE_HEADERS
                }
            else:
                result[key_text] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        cleaned = _redact_url(value)
        cleaned = re.sub(
            r"(?i)(authorization|api[-_ ]?key|client[-_ ]?secret|access[-_ ]?token|refresh[-_ ]?token|credentials?)\s*[:=]\s*[^,\s)]+",
            lambda match: f"{match.group(1)}: [REDACTED]",
            cleaned,
        )
        return cleaned
    return value


def atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o664)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except OSError:
            pass
    return path


def safe_command(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for item in argv:
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        lower = item.lower()
        if any(part in lower for part in ("key", "secret", "token", "password", "credential")):
            if "=" in item:
                key, _ = item.split("=", 1)
                redacted.append(f"{key}=[REDACTED]")
            else:
                redacted.append(item)
                redact_next = True
        else:
            redacted.append(_redact_url(item))
    return redacted


def git_metadata() -> dict[str, Any]:
    def run_git(args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    try:
        full_hash = run_git(["rev-parse", "HEAD"])
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        dirty = bool(run_git(["status", "--porcelain"]))
        return {
            "hash": full_hash[:7] if full_hash else "",
            "full_hash": full_hash,
            "branch": branch or None,
            "dirty": dirty,
        }
    except Exception:
        return {"hash": "", "full_hash": "", "branch": None, "dirty": None}


def package_versions() -> dict[str, str]:
    names = ["anthropic", "flask", "gigachat", "google-genai", "openai", "python-dotenv", "requests"]
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions


def runtime_metadata(argv: list[str], requested_models: list[str], cli_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": safe_command(argv),
        "cli": redact(cli_params),
        "requested_models": requested_models,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": Path(sys.executable).name,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": package_versions(),
        "environment": {
            key: os.environ[key]
            for key in sorted(SAFE_ENV_ALLOWLIST)
            if key in os.environ and os.environ[key] != ""
        },
    }


def safe_traceback(exc: BaseException) -> str:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        text = text.replace(str(Path.home()), "~")
    except Exception:
        pass
    try:
        text = text.replace(str(Path.cwd()), ".")
    except Exception:
        pass
    return str(redact(text))


def structured_error(exc: BaseException | str, *, attempt: int = 1) -> dict[str, Any]:
    if isinstance(exc, BaseException):
        message = str(redact(str(exc)))
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        body = None
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                body = response.json()
            except Exception:
                body = getattr(response, "text", None)
        return {
            "type": type(exc).__name__,
            "message": message,
            "http_status": status_code,
            "provider_code": getattr(exc, "code", None),
            "request_id": getattr(exc, "request_id", None),
            "retryable": None,
            "attempt": attempt,
            "traceback": safe_traceback(exc),
            "provider_response": redact(body),
            "adapter_notes": [],
        }
    return {
        "type": "Error",
        "message": str(redact(str(exc))),
        "http_status": None,
        "provider_code": None,
        "request_id": None,
        "retryable": None,
        "attempt": attempt,
        "traceback": None,
        "provider_response": None,
        "adapter_notes": [],
    }


def sanitized_base_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return redact(url)
    return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in {None, ""}:
            return mapping[key]
    return None


def _raw_usage_from_response(raw_response: dict[str, Any]) -> dict[str, Any]:
    usage = raw_response.get("usage")
    if isinstance(usage, dict):
        return usage
    result = raw_response.get("result")
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        return result["usage"]
    last_response = raw_response.get("last_response")
    if isinstance(last_response, dict) and isinstance(last_response.get("usage"), dict):
        return last_response["usage"]
    return {}


def extract_usage(raw_response: dict[str, Any], prompt_tokens: int | None, completion_tokens: int | None) -> dict[str, Any]:
    raw_usage = _raw_usage_from_response(raw_response)
    prompt_details = raw_usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = raw_usage.get("input_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = raw_usage.get("promptTokensDetails")
    if not isinstance(prompt_details, dict):
        prompt_details = raw_usage.get("inputTokensDetails")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    completion_details = raw_usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = raw_usage.get("output_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = raw_usage.get("completionTokensDetails")
    if not isinstance(completion_details, dict):
        completion_details = raw_usage.get("outputTokensDetails")
    if not isinstance(completion_details, dict):
        completion_details = {}

    input_tokens = prompt_tokens if prompt_tokens not in {None, 0} else _first_present(
        raw_usage, ["prompt_tokens", "input_tokens", "inputTextTokens", "inputTokens", "total_input_tokens"]
    )
    output_tokens = completion_tokens if completion_tokens not in {None, 0} else _first_present(
        raw_usage, ["completion_tokens", "output_tokens", "completionTokens", "total_output_tokens"]
    )
    total_tokens = _first_present(raw_usage, ["total_tokens", "totalTokens"])
    cached_input_tokens = _first_present(
        prompt_details,
        ["cached_tokens", "cached_input_tokens", "cache_read_input_tokens"],
    )
    if cached_input_tokens is None:
        cached_input_tokens = _first_present(
            raw_usage,
            ["cached_input_tokens", "precached_prompt_tokens", "total_cached_tokens"],
        )
    cache_creation_tokens = _first_present(
        prompt_details,
        ["cache_creation_input_tokens", "cache_write_input_tokens"],
    )
    reasoning_tokens = _first_present(
        completion_details,
        ["reasoning_tokens", "reasoningTokens"],
    )
    if reasoning_tokens is None:
        reasoning_tokens = _first_present(
            raw_usage,
            ["reasoning_tokens", "reasoningTokens", "total_thought_tokens"],
        )

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_creation_input_tokens": cache_creation_tokens,
        "raw": redact(raw_usage),
        "source": "provider_response" if raw_usage else "legacy_fields",
    }


def extract_finish_reason(raw_response: dict[str, Any]) -> Any:
    choices = raw_response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0].get("finish_reason") or choices[0].get("stop_reason")
    return raw_response.get("stop_reason") or raw_response.get("finish_reason")


def extract_provider_request_id(raw_response: dict[str, Any]) -> Any:
    headers = raw_response.get("x_headers")
    if not isinstance(headers, dict):
        headers = raw_response.get("headers")
    if isinstance(headers, dict):
        for key in ("x-request-id", "request-id", "x-amzn-requestid"):
            if headers.get(key):
                return headers.get(key)
    return raw_response.get("request_id")


def extract_response_id(raw_response: dict[str, Any]) -> Any:
    for key in ("id", "message_id", "response_id"):
        if raw_response.get(key):
            return raw_response.get(key)
    return None


def extract_provider_timestamp(raw_response: dict[str, Any]) -> Any:
    return raw_response.get("created") or raw_response.get("created_at")


def normalize_legacy_result(
    result: dict[str, Any],
    *,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_index: int,
    provider: str | None = None,
) -> dict[str, Any]:
    raw_response = redact(result.get("raw_response") if isinstance(result.get("raw_response"), dict) else {})
    model = str(result.get("model") or "")
    usage = result.get("usage")
    if not isinstance(usage, dict):
        usage = extract_usage(
            raw_response,
            result.get("prompt_tokens"),
            result.get("completion_tokens"),
        )
    timing = result.get("timing") if isinstance(result.get("timing"), dict) else {}
    if "latency_ms" not in timing:
        timing = {
            **timing,
            "wall_ms": result.get("latency_ms"),
            "monotonic_ms": result.get("latency_ms"),
            "time_to_first_token_ms": None,
            "reasoning_ms": None,
            "retry_durations_ms": result.get("retry_durations_ms") or [],
            "attempts_total_ms": result.get("latency_ms"),
            "source": "runner",
        }
    cost = result.get("cost") if isinstance(result.get("cost"), dict) else {
        "currency": "USD",
        "input": None,
        "output": None,
        "cached_input": None,
        "reasoning": None,
        "total": result.get("cost_usd"),
        "pricing_source": "legacy",
        "pricing_version": None,
        "estimated": result.get("cost_usd") not in {None, 0, 0.0},
        "exchange_rate": None,
    }
    model_info = result.get("model_info") if isinstance(result.get("model_info"), dict) else {}
    result_id = result.get("result_id") or legacy_result_id(
        competition_id,
        problem_id,
        run_id,
        result_index,
        model,
    )
    error_info = result.get("error_info")
    if not isinstance(error_info, dict) and result.get("error"):
        error_info = structured_error(str(result.get("error")))
    return {
        **result,
        "result_id": result_id,
        "result_index": result_index,
        "provider": result.get("provider") or model_info.get("provider") or provider or "unknown",
        "alias": result.get("alias") or model_info.get("alias"),
        "adapter_class": result.get("adapter_class") or model_info.get("adapter_class"),
        "requested_model_id": result.get("requested_model_id") or model_info.get("requested_model_id") or model,
        "resolved_model_id": result.get("resolved_model_id") or model_info.get("resolved_model_id") or raw_response.get("model") or model,
        "attempt": result.get("attempt", 1),
        "status": result.get("status") or ("error" if result.get("error") else "success"),
        "usage": usage,
        "timing": timing,
        "cost": cost,
        "finish_reason": result.get("finish_reason") or extract_finish_reason(raw_response),
        "provider_request_id": result.get("provider_request_id") or extract_provider_request_id(raw_response),
        "response_id": result.get("response_id") or extract_response_id(raw_response),
        "provider_timestamp": result.get("provider_timestamp") or extract_provider_timestamp(raw_response),
        "raw_response": raw_response,
        "error_info": error_info,
        "prompt_tokens": result.get("prompt_tokens", usage.get("input_tokens") or 0),
        "completion_tokens": result.get("completion_tokens", usage.get("output_tokens") or 0),
        "cost_usd": result.get("cost_usd", cost.get("total") or 0.0),
        "latency_ms": result.get("latency_ms", timing.get("wall_ms") or 0),
        "error": result.get("error"),
        "score": result.get("score"),
        "scored_by": result.get("scored_by"),
        "scored_at": result.get("scored_at"),
        "score_comment": result.get("score_comment"),
    }


def normalize_run_log(data: dict[str, Any], path: Path | None = None, logs_dir: Path | None = None) -> dict[str, Any]:
    run_id = str(data.get("run_id") or (path.stem if path else "unknown"))
    competition_id = data.get("competition_id")
    problem_id = data.get("problem_id")
    if path is not None and logs_dir is not None:
        try:
            parts = path.relative_to(logs_dir).parts
        except ValueError:
            parts = ()
        if not competition_id and len(parts) >= 3:
            competition_id = parts[0]
        if not problem_id and len(parts) >= 3:
            problem_id = parts[1]
    problem = data.get("problem") if isinstance(data.get("problem"), dict) else {}
    competition_id = str(competition_id or "legacy")
    problem_id = str(problem_id or problem.get("id") or (path.stem if path else "unknown"))
    problem_text = data.get("problem_text") or problem.get("statement") or problem.get("text") or ""
    results = [
        normalize_legacy_result(
            item,
            competition_id=competition_id,
            problem_id=problem_id,
            run_id=run_id,
            result_index=index,
        )
        for index, item in enumerate(data.get("results") if isinstance(data.get("results"), list) else [])
        if isinstance(item, dict)
    ]
    if not results:
        answer = data.get("answer") or data.get("solution") or data.get("response") or data.get("output")
        if answer:
            results.append(
                normalize_legacy_result(
                    {"model": data.get("model") or run_id, "answer": answer},
                    competition_id=competition_id,
                    problem_id=problem_id,
                    run_id=run_id,
                    result_index=0,
                )
            )
    return {
        **data,
        "schema_version": data.get("schema_version") or 1,
        "run_id": run_id,
        "status": data.get("status") or ("failed" if results and all(item.get("error") for item in results) else "completed"),
        "timestamp": data.get("timestamp") or data.get("started_at") or "",
        "started_at": data.get("started_at") or data.get("timestamp") or "",
        "completed_at": data.get("completed_at") or data.get("timestamp") or "",
        "competition_id": competition_id,
        "competition_title": data.get("competition_title") or ("Старые прогоны" if competition_id == "legacy" else competition_id),
        "problem_id": problem_id,
        "problem_title": data.get("problem_title") or problem.get("title") or problem_id,
        "problem_file": data.get("problem_file") or "",
        "problem_text": problem_text,
        "problem": problem,
        "results": results,
        "_log_path": str(path) if path else data.get("_log_path"),
    }

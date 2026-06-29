from __future__ import annotations

import abc
from dataclasses import asdict, dataclass
from typing import Any, Optional

from .telemetry import (
    extract_finish_reason,
    extract_provider_request_id,
    extract_provider_timestamp,
    extract_response_id,
    extract_usage,
    redact,
    structured_error,
)


@dataclass
class SolveResult:
    model: str
    answer: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    raw_response: dict[str, Any]
    error: Optional[str] = None
    provider: Optional[str] = None
    requested_model_id: Optional[str] = None
    resolved_model_id: Optional[str] = None
    request: Optional[dict[str, Any]] = None
    usage: Optional[dict[str, Any]] = None
    timing: Optional[dict[str, Any]] = None
    cost: Optional[dict[str, Any]] = None
    finish_reason: Optional[str] = None
    provider_request_id: Optional[str] = None
    response_id: Optional[str] = None
    provider_timestamp: Optional[Any] = None
    error_info: Optional[dict[str, Any]] = None

    def to_log_dict(self) -> dict[str, Any]:
        data = asdict(self)
        raw_response = redact(self.raw_response or {})
        usage = self.usage or extract_usage(
            raw_response,
            self.prompt_tokens,
            self.completion_tokens,
        )
        timing = self.timing or {
            "wall_ms": self.latency_ms,
            "monotonic_ms": self.latency_ms,
            "time_to_first_token_ms": None,
            "reasoning_ms": None,
            "retry_durations_ms": [],
            "attempts_total_ms": self.latency_ms,
            "source": "runner",
        }
        cost = self.cost or {
            "currency": "USD",
            "input": None,
            "output": None,
            "cached_input": None,
            "reasoning": None,
            "total": self.cost_usd,
            "pricing_source": None,
            "pricing_version": None,
            "estimated": self.cost_usd not in {0, 0.0, None},
            "exchange_rate": None,
        }
        data.update(
            {
                "requested_model_id": self.requested_model_id or self.model,
                "resolved_model_id": self.resolved_model_id or raw_response.get("model") or self.model,
                "request": redact(self.request or {}),
                "usage": usage,
                "timing": timing,
                "cost": cost,
                "finish_reason": self.finish_reason or extract_finish_reason(raw_response),
                "provider_request_id": self.provider_request_id or extract_provider_request_id(raw_response),
                "response_id": self.response_id or extract_response_id(raw_response),
                "provider_timestamp": self.provider_timestamp or extract_provider_timestamp(raw_response),
                "raw_response": raw_response,
                "error_info": self.error_info or (structured_error(self.error) if self.error else None),
                "score": None,
                "scored_by": None,
                "scored_at": None,
                "score_comment": None,
            }
        )
        return data


class BaseModel(abc.ABC):
    @property
    @abc.abstractmethod
    def model_id(self) -> str:
        ...

    @abc.abstractmethod
    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        ...

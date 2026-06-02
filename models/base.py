from __future__ import annotations

import abc
from dataclasses import asdict, dataclass
from typing import Any, Optional


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

    def to_log_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
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
    def solve(self, problem: str) -> SolveResult:
        ...

"""Provider-agnostic LLM interface (T1.1, code half).

Every agent talks to a model through ``LLMClient``, so the provider chosen in
D-001 plugs in as one adapter class without touching the agents. ``UsageLog``
records tokens and cost per call into the job and enforces a hard budget cap
(risk R-12: API cost overruns). ``FakeLLM`` gives tests scripted replies.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    usage: Usage


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens, as published by the provider."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_per_mtok + usage.output_tokens * self.output_per_mtok
        ) / 1_000_000


class LLMClient(Protocol):
    """What every provider adapter implements."""

    model: str
    price: Price

    def complete(self, messages: list[Message], *, max_tokens: int = 2048) -> LLMResult: ...


class BudgetExceeded(Exception):
    """A call would push the job past its spending cap."""


@dataclass
class UsageLog:
    """Append-only per-job record of LLM calls (``logs/llm_usage.jsonl``) with a USD cap."""

    path: Path
    budget_usd: float
    spent_usd: float = field(default=0.0)

    @classmethod
    def for_job(cls, job_path: Path, budget_usd: float) -> UsageLog:
        path = Path(job_path) / "logs" / "llm_usage.jsonl"
        spent = 0.0
        if path.exists():  # resumed job: keep counting from what was already spent
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    spent += json.loads(line)["cost_usd"]
        return cls(path, budget_usd, spent)

    @property
    def remaining_usd(self) -> float:
        return self.budget_usd - self.spent_usd

    def record(self, agent: str, result: LLMResult, price: Price) -> float:
        cost = price.cost(result.usage)
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "agent": agent,
            "model": result.model,
            **asdict(result.usage),
            "cost_usd": round(cost, 6),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self.spent_usd += cost
        return cost


def call(
    client: LLMClient,
    messages: list[Message],
    *,
    agent: str,
    log: UsageLog,
    max_tokens: int = 2048,
) -> LLMResult:
    """The one way agents call a model: refuses once the budget is spent, logs every call."""
    if log.remaining_usd <= 0:
        raise BudgetExceeded(
            f"LLM budget of ${log.budget_usd:.2f} used up (spent ${log.spent_usd:.4f}); "
            f"{agent} not run"
        )
    result = client.complete(messages, max_tokens=max_tokens)
    log.record(agent, result, client.price)
    return result


class FakeLLM:
    """Scripted replies for tests: returns ``replies`` in order and remembers prompts."""

    def __init__(
        self,
        replies: Iterable[str],
        *,
        model: str = "fake-model",
        price: Price = Price(0.0, 0.0),  # noqa: B008 - frozen dataclass, safe default
        tokens_per_char: float = 0.25,
    ) -> None:
        self._replies = list(replies)
        self.model = model
        self.price = price
        self._tpc = tokens_per_char
        self.prompts: list[list[Message]] = []

    def complete(self, messages: list[Message], *, max_tokens: int = 2048) -> LLMResult:
        if not self._replies:
            raise RuntimeError("FakeLLM ran out of scripted replies")
        self.prompts.append(list(messages))
        text = self._replies.pop(0)
        usage = Usage(
            input_tokens=int(sum(len(m.content) for m in messages) * self._tpc),
            output_tokens=int(len(text) * self._tpc),
        )
        return LLMResult(text=text, model=self.model, usage=usage)

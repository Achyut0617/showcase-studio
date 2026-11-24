import json

import pytest

from showcase.llm import (
    BudgetExceeded,
    FakeLLM,
    LLMResult,
    Message,
    Price,
    Usage,
    UsageLog,
    call,
)

PROMPT = [Message("system", "You explain code."), Message("user", "x" * 400)]


def test_price_cost_per_million_tokens():
    price = Price(input_per_mtok=3.0, output_per_mtok=15.0)
    assert price.cost(Usage(1_000_000, 0)) == 3.0
    assert price.cost(Usage(200_000, 100_000)) == pytest.approx(0.6 + 1.5)


def test_fake_llm_returns_replies_in_order_and_records_prompts():
    llm = FakeLLM(["one", "two"])
    assert llm.complete(PROMPT).text == "one"
    assert llm.complete(PROMPT).text == "two"
    assert llm.prompts[0][1].content == "x" * 400
    with pytest.raises(RuntimeError):
        llm.complete(PROMPT)


def test_call_logs_usage_to_job(tmp_path):
    llm = FakeLLM(["ok"], model="m1", price=Price(1.0, 2.0))
    log = UsageLog.for_job(tmp_path, budget_usd=1.0)
    result = call(llm, PROMPT, agent="analyzer", log=log)
    assert isinstance(result, LLMResult)
    lines = (tmp_path / "logs" / "llm_usage.jsonl").read_text().splitlines()
    entry = json.loads(lines[0])
    assert entry["agent"] == "analyzer" and entry["model"] == "m1"
    assert entry["input_tokens"] > 0
    assert log.spent_usd == pytest.approx(entry["cost_usd"], abs=1e-6)


def test_budget_cap_blocks_further_calls(tmp_path):
    # 1M input tokens at $1/Mtok per call -> $1 per call; budget $1.50 allows two calls
    llm = FakeLLM(["a", "b", "c"], price=Price(1.0, 0.0), tokens_per_char=1.0)
    big = [Message("user", "x" * 1_000_000)]
    log = UsageLog.for_job(tmp_path, budget_usd=1.5)
    call(llm, big, agent="a", log=log)
    call(llm, big, agent="a", log=log)  # allowed: budget not yet used up before the call
    with pytest.raises(BudgetExceeded, match=r"\$1\.50"):
        call(llm, big, agent="a", log=log)
    assert len(llm.prompts) == 2  # the third call never reached the model


def test_resumed_job_keeps_what_was_spent(tmp_path):
    llm = FakeLLM(["a"], price=Price(1.0, 0.0), tokens_per_char=1.0)
    first = UsageLog.for_job(tmp_path, budget_usd=5.0)
    call(llm, [Message("user", "x" * 500_000)], agent="a", log=first)
    again = UsageLog.for_job(tmp_path, budget_usd=5.0)
    assert again.spent_usd == pytest.approx(0.5)
    assert again.remaining_usd == pytest.approx(4.5)

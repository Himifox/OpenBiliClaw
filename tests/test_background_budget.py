from __future__ import annotations

from typing import Any

import pytest

from openbiliclaw.llm.background_budget import (
    BackgroundTokenBudget,
    BackgroundTokenBudgetExceededError,
)
from openbiliclaw.llm.base import LLMResponse
from openbiliclaw.llm.service import LLMService
from openbiliclaw.runtime.maintenance_policy import MaintenancePolicy


class _UsageSink:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = list(rows or [])

    def query_llm_usage_today_by_caller(self) -> list[dict[str, Any]]:
        return list(self.rows)


class _Registry:
    default_provider = "test"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        del messages, kwargs
        self.calls += 1
        return LLMResponse(content="ok", usage={"prompt_tokens": 1})


def test_embedded_policy_supports_bounded_inventory_and_daily_budget() -> None:
    policy = MaintenancePolicy.embedded_proactive()

    assert policy.pool_capacity == 30
    assert policy.ready_soft_target == 10
    assert policy.ready_stop_threshold == 4
    assert policy.refill_batch_size == 10
    assert policy.daily_input_token_budget == 100_000
    assert policy.discovery_daily_input_budget == 50_000
    assert policy.recommendation_daily_input_budget == 20_000
    assert policy.soul_daily_input_budget == 30_000
    assert policy.daily_output_token_budget == 20_000
    assert policy.discovery_daily_output_budget is None
    assert policy.recommendation_daily_output_budget is None
    assert policy.soul_daily_output_budget is None
    assert policy.is_proactive_bounded is True


def test_policy_rejects_module_budgets_above_total() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        MaintenancePolicy(
            daily_input_token_budget=10,
            discovery_daily_input_budget=6,
            recommendation_daily_input_budget=5,
        )

    with pytest.raises(ValueError, match="cannot exceed"):
        MaintenancePolicy(
            daily_output_token_budget=10,
            discovery_daily_output_budget=6,
            recommendation_daily_output_budget=5,
        )


@pytest.mark.asyncio
async def test_budget_counts_persisted_usage_before_provider_admission() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=100,
        discovery_daily_input_budget=60,
        recommendation_daily_input_budget=20,
        soul_daily_input_budget=20,
    )
    sink = _UsageSink([{"caller": "discovery.evaluate_batch", "prompt_tokens": 55}])
    budget = BackgroundTokenBudget(sink, policy)

    with pytest.raises(BackgroundTokenBudgetExceededError, match="discovery"):
        await budget.reserve(
            caller="discovery.keyword_planner",
            messages=[{"role": "user", "content": "需要超过剩余五个 token"}],
        )


@pytest.mark.asyncio
async def test_budget_reservations_prevent_concurrent_oversubscription() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=80,
        discovery_daily_input_budget=40,
        recommendation_daily_input_budget=20,
        soul_daily_input_budget=20,
    )
    budget = BackgroundTokenBudget(_UsageSink(), policy)
    messages = [{"role": "user", "content": "a" * 30}]

    reservation = await budget.reserve(
        caller="discovery.evaluate_batch",
        messages=messages,
    )
    assert reservation is not None
    with pytest.raises(BackgroundTokenBudgetExceededError):
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=messages,
        )
    await budget.release(reservation)
    assert (
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=messages,
        )
        is not None
    )


@pytest.mark.asyncio
async def test_interactive_usage_does_not_reduce_background_total() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=50,
        discovery_daily_input_budget=50,
    )
    sink = _UsageSink([{"caller": "soul.dialogue.tools", "prompt_tokens": 10_000}])
    budget = BackgroundTokenBudget(sink, policy)

    assert (
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=[{"role": "user", "content": "short"}],
        )
        is not None
    )


@pytest.mark.asyncio
async def test_output_budget_blocks_on_persisted_completion_tokens() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=1_000,
        discovery_daily_input_budget=1_000,
        daily_output_token_budget=10,
        discovery_daily_output_budget=10,
    )
    sink = _UsageSink(
        [
            {
                "caller": "discovery.evaluate_batch",
                "prompt_tokens": 1,
                "completion_tokens": 10,
            }
        ]
    )
    budget = BackgroundTokenBudget(sink, policy)

    with pytest.raises(BackgroundTokenBudgetExceededError, match="output"):
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=[{"role": "user", "content": "short"}],
            max_output_tokens=1,
        )


@pytest.mark.asyncio
async def test_output_reservations_prevent_concurrent_oversubscription() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=1_000,
        discovery_daily_input_budget=1_000,
        daily_output_token_budget=10,
        discovery_daily_output_budget=10,
    )
    budget = BackgroundTokenBudget(_UsageSink(), policy)
    messages = [{"role": "user", "content": "short"}]

    reservation = await budget.reserve(
        caller="discovery.evaluate_batch",
        messages=messages,
        max_output_tokens=6,
    )
    with pytest.raises(BackgroundTokenBudgetExceededError, match="output"):
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=messages,
            max_output_tokens=6,
        )
    await budget.release(reservation)
    assert (
        await budget.reserve(
            caller="discovery.evaluate_batch",
            messages=messages,
            max_output_tokens=6,
        )
        is not None
    )


def test_user_facing_dialogue_is_not_charged_to_background_budget() -> None:
    assert BackgroundTokenBudget.caller_group("soul.dialogue.tools") is None
    assert BackgroundTokenBudget.caller_group("soul.awareness_confusions") == "soul"


@pytest.mark.asyncio
async def test_llm_service_blocks_before_calling_provider() -> None:
    policy = MaintenancePolicy(
        daily_input_token_budget=100,
        discovery_daily_input_budget=50,
        recommendation_daily_input_budget=20,
        soul_daily_input_budget=30,
    )
    sink = _UsageSink([{"caller": "discovery.evaluate_batch", "prompt_tokens": 50}])
    registry = _Registry()
    service = LLMService(
        registry=registry,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
        background_token_budget=BackgroundTokenBudget(sink, policy),
    )

    with pytest.raises(BackgroundTokenBudgetExceededError):
        await service.complete_with_core_memory(
            system_instruction="system",
            user_input="candidate",
            caller="discovery.evaluate_batch",
        )

    assert registry.calls == 0

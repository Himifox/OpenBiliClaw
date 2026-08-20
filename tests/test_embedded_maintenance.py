from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from openbiliclaw.runtime.refresh import ContinuousRefreshController


class _Database:
    def __init__(self, available: int) -> None:
        self.available = available

    def count_pool_candidates(self, *, xhs_self_nickname: str = "") -> int:
        return self.available


class _Memory:
    def __init__(self) -> None:
        self.state: dict[str, object] = {}

    def load_discovery_runtime_state(self) -> dict[str, object]:
        return dict(self.state)

    def save_discovery_runtime_state(self, state: dict[str, object]) -> None:
        self.state = dict(state)


def _controller(available: int) -> ContinuousRefreshController:
    return ContinuousRefreshController(
        memory_manager=_Memory(),  # type: ignore[arg-type]
        database=_Database(available),  # type: ignore[arg-type]
        soul_engine=SimpleNamespace(),  # type: ignore[arg-type]
        discovery_engine=SimpleNamespace(),  # type: ignore[arg-type]
        recommendation_engine=SimpleNamespace(),  # type: ignore[arg-type]
        pool_target_count=10,
        pool_capacity_count=30,
        refill_trigger_count=4,
        refill_batch_size=10,
        surface_copy_mode="lazy",
    )


def test_embedded_refill_stops_at_four_ready_candidates() -> None:
    assert _controller(3).background_refill_allowed() is True
    assert _controller(4).background_refill_allowed() is False
    assert _controller(10).background_refill_allowed() is False


def test_embedded_pool_maintenance_uses_capacity_not_soft_target() -> None:
    controller = _controller(3)

    kwargs: dict[str, Any] = controller._pool_maintenance_kwargs()  # noqa: SLF001

    assert kwargs["target"] == 30
    assert controller.pool_target_count == 10
    assert controller.refill_batch_size == 10


def test_embedded_refill_cooldown_survives_runtime_state_reload() -> None:
    memory = _Memory()
    database = _Database(3)
    controller = ContinuousRefreshController(
        memory_manager=memory,  # type: ignore[arg-type]
        database=database,  # type: ignore[arg-type]
        soul_engine=SimpleNamespace(),  # type: ignore[arg-type]
        discovery_engine=SimpleNamespace(),  # type: ignore[arg-type]
        recommendation_engine=SimpleNamespace(),  # type: ignore[arg-type]
        pool_target_count=10,
        pool_capacity_count=30,
        refill_trigger_count=4,
        refill_batch_size=10,
        refill_cooldown_seconds=900,
    )

    assert controller.background_refill_allowed() is True
    controller.record_background_refill_attempt({"evaluated": 10, "cached": 0})
    restarted = ContinuousRefreshController(
        memory_manager=memory,  # type: ignore[arg-type]
        database=database,  # type: ignore[arg-type]
        soul_engine=SimpleNamespace(),  # type: ignore[arg-type]
        discovery_engine=SimpleNamespace(),  # type: ignore[arg-type]
        recommendation_engine=SimpleNamespace(),  # type: ignore[arg-type]
        pool_target_count=10,
        pool_capacity_count=30,
        refill_trigger_count=4,
        refill_batch_size=10,
        refill_cooldown_seconds=900,
    )

    assert restarted.background_refill_allowed() is False


@pytest.mark.asyncio
async def test_lazy_embedded_precompute_only_classifies_bounded_batch() -> None:
    class _Soul:
        async def get_profile(self) -> object:
            return object()

    class _Recommendation:
        def __init__(self) -> None:
            self.classify_limits: list[int] = []
            self.precompute_calls = 0

        async def classify_pool_backlog(self, *, profile: object, limit: int) -> int:
            del profile
            self.classify_limits.append(limit)
            return 0

        async def precompute_pool_copy(self, *, profile: object, limit: int) -> int:
            del profile, limit
            self.precompute_calls += 1
            return 0

    recommendation = _Recommendation()
    controller = ContinuousRefreshController(
        memory_manager=_Memory(),  # type: ignore[arg-type]
        database=_Database(3),  # type: ignore[arg-type]
        soul_engine=_Soul(),  # type: ignore[arg-type]
        discovery_engine=SimpleNamespace(),  # type: ignore[arg-type]
        recommendation_engine=recommendation,  # type: ignore[arg-type]
        pool_target_count=10,
        pool_capacity_count=30,
        refill_trigger_count=4,
        refill_batch_size=10,
        surface_copy_mode="lazy",
    )
    controller._is_initialized = lambda: True  # type: ignore[method-assign]

    await controller._drain_pool_precompute_backlog()  # noqa: SLF001

    assert recommendation.classify_limits == [10]
    assert recommendation.precompute_calls == 0

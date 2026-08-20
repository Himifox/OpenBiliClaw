"""Host-owned limits for background recommendation maintenance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenancePolicy:
    """Bound an embedded runtime's inventory growth and background LLM spend.

    ``None`` budgets preserve the standalone runtime's existing unlimited
    behavior.  Embedded hosts can inject this object without adding host types
    or persisted credentials to OpenBiliClaw's public configuration.
    """

    pool_capacity: int = 300
    ready_soft_target: int = 300
    ready_stop_threshold: int = 300
    refill_batch_size: int = 30
    refill_cooldown_seconds: int = 0
    daily_input_token_budget: int | None = None
    discovery_daily_input_budget: int | None = None
    recommendation_daily_input_budget: int | None = None
    soul_daily_input_budget: int | None = None

    def __post_init__(self) -> None:
        if self.pool_capacity < 1:
            raise ValueError("pool_capacity must be positive")
        if not 1 <= self.ready_stop_threshold <= self.ready_soft_target:
            raise ValueError(
                "ready_stop_threshold must be between 1 and ready_soft_target"
            )
        if self.ready_soft_target > self.pool_capacity:
            raise ValueError("ready_soft_target cannot exceed pool_capacity")
        if not 1 <= self.refill_batch_size <= 30:
            raise ValueError("refill_batch_size must be between 1 and 30")
        if self.refill_cooldown_seconds < 0:
            raise ValueError("refill_cooldown_seconds cannot be negative")
        budgets = (
            self.daily_input_token_budget,
            self.discovery_daily_input_budget,
            self.recommendation_daily_input_budget,
            self.soul_daily_input_budget,
        )
        if any(value is not None and value < 1 for value in budgets):
            raise ValueError("token budgets must be positive when configured")
        module_total = sum(value or 0 for value in budgets[1:])
        if (
            self.daily_input_token_budget is not None
            and module_total > self.daily_input_token_budget
        ):
            raise ValueError("module token budgets cannot exceed the daily total")

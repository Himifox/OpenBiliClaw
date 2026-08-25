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
    daily_output_token_budget: int | None = None
    discovery_daily_output_budget: int | None = None
    recommendation_daily_output_budget: int | None = None
    soul_daily_output_budget: int | None = None

    @classmethod
    def embedded_proactive(cls) -> MaintenancePolicy:
        """Return the fail-closed preset for an embedded proactive surface."""
        # The 20k output ceiling is calibrated from the 2026-08-18 local
        # background high-water mark (13,840 reported completion tokens), with
        # ~45% headroom. Re-open this calibration after any provider/model swap.
        return cls(
            pool_capacity=30,
            ready_soft_target=10,
            ready_stop_threshold=4,
            refill_batch_size=10,
            refill_cooldown_seconds=15 * 60,
            daily_input_token_budget=100_000,
            discovery_daily_input_budget=50_000,
            recommendation_daily_input_budget=20_000,
            soul_daily_input_budget=30_000,
            daily_output_token_budget=20_000,
        )

    @property
    def is_proactive_bounded(self) -> bool:
        """Whether both sides of every proactive background budget are set."""
        return all(
            value is not None
            for value in (
                self.daily_input_token_budget,
                self.discovery_daily_input_budget,
                self.recommendation_daily_input_budget,
                self.soul_daily_input_budget,
                self.daily_output_token_budget,
            )
        )

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
        input_budgets = (
            self.daily_input_token_budget,
            self.discovery_daily_input_budget,
            self.recommendation_daily_input_budget,
            self.soul_daily_input_budget,
        )
        output_budgets = (
            self.daily_output_token_budget,
            self.discovery_daily_output_budget,
            self.recommendation_daily_output_budget,
            self.soul_daily_output_budget,
        )
        budgets = input_budgets + output_budgets
        if any(value is not None and value < 1 for value in budgets):
            raise ValueError("token budgets must be positive when configured")
        for budget_kind, configured in (
            ("input", input_budgets),
            ("output", output_budgets),
        ):
            module_total = sum(value or 0 for value in configured[1:])
            if configured[0] is not None and module_total > configured[0]:
                raise ValueError(
                    f"module {budget_kind} token budgets cannot exceed the daily total"
                )

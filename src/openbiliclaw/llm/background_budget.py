"""Persistent daily input-token admission for embedded background work."""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from openbiliclaw.runtime.maintenance_policy import MaintenancePolicy

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class BudgetUsageSink(Protocol):
    """Storage contract used by the budget gate."""

    def query_llm_usage_today_by_caller(self) -> list[dict[str, Any]]: ...


class BackgroundTokenBudgetExceededError(RuntimeError):
    """Raised before a background provider call would exceed its daily budget."""


@dataclass(frozen=True)
class TokenReservation:
    """One in-process reservation awaiting provider-reported settlement."""

    group: str
    estimated_input_tokens: int
    max_output_tokens: int


def estimate_input_tokens(messages: list[dict[str, Any]]) -> int:
    """Conservatively estimate chat input without a provider tokenizer.

    Chinese characters are charged one token each; remaining serialized text
    is charged at three characters per token.  The deliberate overestimate is
    a safety margin for a hard spending gate, not a billing substitute.
    """

    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cjk = len(_CJK_RE.findall(payload))
    other = max(0, len(payload) - cjk)
    return max(1, cjk + math.ceil(other / 3) + 16 * len(messages))


class BackgroundTokenBudget:
    """Admit embedded background calls against persisted same-day usage."""

    def __init__(self, sink: BudgetUsageSink, policy: MaintenancePolicy) -> None:
        self._sink = sink
        self._policy = policy
        self._lock = asyncio.Lock()
        self._reserved_input_total = 0
        self._reserved_input_by_group = {
            "discovery": 0,
            "recommendation": 0,
            "soul": 0,
        }
        self._reserved_output_total = 0
        self._reserved_output_by_group = {
            "discovery": 0,
            "recommendation": 0,
            "soul": 0,
        }

    @staticmethod
    def caller_group(caller: str) -> str | None:
        tag = str(caller).strip().lower()
        if tag.startswith(
            (
                "discovery.",
                "runtime.bilibili_extension_search",
                "sources.",
                "yt_search",
            )
        ):
            return "discovery"
        if tag.startswith("recommendation."):
            return "recommendation"
        if tag.startswith("soul.") and not tag.startswith("soul.dialogue.tools"):
            return "soul"
        return None

    def _limits(self, group: str) -> tuple[int | None, int | None, int | None, int | None]:
        input_group_limit = {
            "discovery": self._policy.discovery_daily_input_budget,
            "recommendation": self._policy.recommendation_daily_input_budget,
            "soul": self._policy.soul_daily_input_budget,
        }[group]
        output_group_limit = {
            "discovery": self._policy.discovery_daily_output_budget,
            "recommendation": self._policy.recommendation_daily_output_budget,
            "soul": self._policy.soul_daily_output_budget,
        }[group]
        return (
            self._policy.daily_input_token_budget,
            input_group_limit,
            self._policy.daily_output_token_budget,
            output_group_limit,
        )

    def _used(
        self,
    ) -> tuple[int, dict[str, int], int, dict[str, int]]:
        input_total = 0
        input_grouped = {"discovery": 0, "recommendation": 0, "soul": 0}
        output_total = 0
        output_grouped = {"discovery": 0, "recommendation": 0, "soul": 0}
        for row in self._sink.query_llm_usage_today_by_caller():
            group = self.caller_group(str(row.get("caller", "") or ""))
            if group is None:
                continue
            input_tokens = max(0, int(row.get("prompt_tokens", 0) or 0))
            output_tokens = max(0, int(row.get("completion_tokens", 0) or 0))
            input_total += input_tokens
            input_grouped[group] += input_tokens
            output_total += output_tokens
            output_grouped[group] += output_tokens
        return input_total, input_grouped, output_total, output_grouped

    async def reserve(
        self,
        *,
        caller: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int = 0,
    ) -> TokenReservation | None:
        """Reserve worst-case input/output or fail before the provider call."""

        group = self.caller_group(caller)
        if group is None:
            return None
        estimate = estimate_input_tokens(messages)
        output_reservation = max(0, int(max_output_tokens))
        async with self._lock:
            used_input, used_input_by_group, used_output, used_output_by_group = self._used()
            input_total_limit, input_group_limit, output_total_limit, output_group_limit = (
                self._limits(group)
            )
            projected_input_total = used_input + self._reserved_input_total + estimate
            projected_input_group = (
                used_input_by_group[group] + self._reserved_input_by_group[group] + estimate
            )
            if input_total_limit is not None and projected_input_total > input_total_limit:
                raise BackgroundTokenBudgetExceededError(
                    f"daily OBC background input budget exhausted: "
                    f"caller={caller} estimate={estimate} remaining="
                    f"{max(0, input_total_limit - used_input - self._reserved_input_total)}"
                )
            if input_group_limit is not None and projected_input_group > input_group_limit:
                input_group_remaining = max(
                    0,
                    input_group_limit
                    - used_input_by_group[group]
                    - self._reserved_input_by_group[group],
                )
                raise BackgroundTokenBudgetExceededError(
                    f"daily {group} input budget exhausted: caller={caller} "
                    f"estimate={estimate} remaining="
                    f"{input_group_remaining}"
                )
            projected_output_total = used_output + self._reserved_output_total + output_reservation
            projected_output_group = (
                used_output_by_group[group]
                + self._reserved_output_by_group[group]
                + output_reservation
            )
            if output_total_limit is not None and projected_output_total > output_total_limit:
                raise BackgroundTokenBudgetExceededError(
                    f"daily OBC background output budget exhausted: caller={caller} "
                    f"max_output={output_reservation} remaining="
                    f"{max(0, output_total_limit - used_output - self._reserved_output_total)}"
                )
            if output_group_limit is not None and projected_output_group > output_group_limit:
                output_group_remaining = max(
                    0,
                    output_group_limit
                    - used_output_by_group[group]
                    - self._reserved_output_by_group[group],
                )
                raise BackgroundTokenBudgetExceededError(
                    f"daily {group} output budget exhausted: caller={caller} "
                    f"max_output={output_reservation} remaining="
                    f"{output_group_remaining}"
                )
            self._reserved_input_total += estimate
            self._reserved_input_by_group[group] += estimate
            self._reserved_output_total += output_reservation
            self._reserved_output_by_group[group] += output_reservation
        return TokenReservation(
            group=group,
            estimated_input_tokens=estimate,
            max_output_tokens=output_reservation,
        )

    async def release(self, reservation: TokenReservation | None) -> None:
        """Release one reservation after success or failure."""

        if reservation is None:
            return
        async with self._lock:
            estimate = reservation.estimated_input_tokens
            self._reserved_input_total = max(0, self._reserved_input_total - estimate)
            self._reserved_input_by_group[reservation.group] = max(
                0,
                self._reserved_input_by_group[reservation.group] - estimate,
            )
            output = reservation.max_output_tokens
            self._reserved_output_total = max(0, self._reserved_output_total - output)
            self._reserved_output_by_group[reservation.group] = max(
                0,
                self._reserved_output_by_group[reservation.group] - output,
            )

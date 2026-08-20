from __future__ import annotations

import json
from typing import Any

import pytest

from openbiliclaw.llm.base import LLMResponse
from openbiliclaw.llm.prompts import build_bounded_awareness_with_confusions_prompt
from openbiliclaw.soul.activity_envelope import build_activity_envelopes
from openbiliclaw.soul.awareness_analyzer import (
    AwarenessAnalyzer,
    AwarenessGenerationError,
)


def _event(
    event_id: int,
    *,
    content_id: str,
    author_id: str,
    author_name: str,
    event_type: str = "view",
    title: str = "同名教程",
) -> dict[str, object]:
    return {
        "id": event_id,
        "event_type": event_type,
        "title": title,
        "context": f"观看《{title}》",
        "created_at": "2026-08-20T10:00:00Z",
        "metadata": json.dumps(
            {
                "source_platform": "bilibili",
                "bvid": content_id,
                "author_mid": author_id,
                "author_name": author_name,
                "description": f"{title} 的结构化内容摘要",
            },
            ensure_ascii=False,
        ),
    }


def _preference() -> dict[str, object]:
    interests = [
        {
            "name": f"兴趣{index}",
            "category": "科技",
            "weight": max(0.1, 1.0 - index / 200),
            "state": "trial",
            "evidence_count": 2,
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-08-20T00:00:00Z",
            "last_evidence_at": "2026-08-20T00:00:00Z",
            "source": "watch history",
        }
        for index in range(168)
    ]
    return {
        "interests": interests,
        "favorite_up_users": [f"UP-{index}" for index in range(721)],
    }


def test_envelopes_keep_same_title_different_authors_separate() -> None:
    events = [
        _event(1, content_id="BV1", author_id="11", author_name="作者甲"),
        _event(2, content_id="BV2", author_id="22", author_name="作者乙"),
    ]

    envelopes = build_activity_envelopes(events, {})

    assert len(envelopes) == 2
    assert envelopes[0].tracking.author_key == "bilibili:uid:11"
    assert envelopes[0].semantics.author_name == "作者甲"
    assert envelopes[0].tracking.event_ids == (1,)
    assert envelopes[1].tracking.author_key == "bilibili:uid:22"
    assert envelopes[1].semantics.author_name == "作者乙"
    assert envelopes[1].tracking.event_ids == (2,)


def test_envelope_aggregation_preserves_exact_event_partition() -> None:
    events = [
        _event(1, content_id="BV1", author_id="11", author_name="作者甲"),
        _event(
            2,
            content_id="BV1",
            author_id="11",
            author_name="作者甲",
            event_type="seek",
        ),
        _event(
            3,
            content_id="BV1",
            author_id="11",
            author_name="作者甲",
            event_type="pause",
        ),
        _event(4, content_id="BV2", author_id="22", author_name="作者乙"),
    ]

    envelopes = build_activity_envelopes(events, {})

    assert [item.tracking.event_ids for item in envelopes] == [(1, 2, 3), (4,)]
    assert dict(envelopes[0].semantics.activity_counts) == {
        "pause": 1,
        "seek": 1,
        "view": 1,
    }
    assert [event_id for item in envelopes for event_id in item.tracking.event_ids] == [
        1,
        2,
        3,
        4,
    ]


def test_bounded_prompt_omits_tracking_and_full_creator_inventory() -> None:
    events = [
        _event(
            index,
            content_id=f"BV{index}",
            author_id=str(index),
            author_name=f"作者{index}",
            title=f"兴趣{index % 10} 教程",
        )
        for index in range(1, 29)
    ]

    prompt = build_bounded_awareness_with_confusions_prompt(
        events=events,
        preference_summary=_preference(),
        soul_profile={"personality_portrait": "偏好结构化教程"},
        target_input_tokens=24_000,
    )
    user_input = prompt.messages[1]["content"]

    assert prompt.estimated_input_tokens <= 24_000
    assert len(prompt.consumed_events) == len(events)
    assert "favorite_up_users" not in user_input
    assert "UP-720" not in user_input
    assert "event_ids" not in user_input
    assert "content_key" not in user_input
    assert "author_key" not in user_input
    assert "E001" in user_input
    assert "作者1" in user_input


def test_budget_selection_stops_only_after_a_complete_envelope() -> None:
    events = [
        _event(1, content_id="BV1", author_id="11", author_name="作者甲"),
        _event(
            2,
            content_id="BV1",
            author_id="11",
            author_name="作者甲",
            event_type="scroll",
        ),
        *[
            _event(
                index,
                content_id=f"BV{index}",
                author_id=str(index),
                author_name=f"作者{index}",
                title="长标题" * 20,
            )
            for index in range(3, 80)
        ],
    ]

    prompt = build_bounded_awareness_with_confusions_prompt(
        events=events,
        preference_summary={},
        soul_profile={},
        target_input_tokens=4_000,
    )
    consumed_ids = [int(event["id"]) for event in prompt.consumed_events]

    assert consumed_ids[:2] == [1, 2]
    assert consumed_ids == list(range(1, max(consumed_ids) + 1))
    assert prompt.manifest.envelopes[0].tracking.event_ids == (1, 2)


class _StructuredService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def complete_structured_task(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(dict(kwargs))
        return LLMResponse(content=self.content, provider="test")


@pytest.mark.asyncio
async def test_bounded_output_refs_expand_to_exact_event_ids() -> None:
    service = _StructuredService(
        json.dumps(
            {
                "notes": [
                    {
                        "date": "2026-08-20",
                        "observation": "按需查看同一教程。",
                        "trend": "更偏向定位关键步骤。",
                        "emotion_guess": "专注",
                        "source_refs": ["E001"],
                    }
                ],
                "confusions": [
                    {
                        "topic": "教程",
                        "observation": "跳看较多。",
                        "interpretation": "可能在找具体步骤。",
                        "interpretation_confidence": 0.4,
                        "source_refs": ["E001"],
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    analyzer = AwarenessAnalyzer(service, confusions_prompt_view="bounded-v2")
    events = [
        _event(1, content_id="BV1", author_id="11", author_name="作者甲"),
        _event(
            2,
            content_id="BV1",
            author_id="11",
            author_name="作者甲",
            event_type="seek",
        ),
    ]

    notes, confusions = await analyzer.analyze_with_confusions(
        events=events,
        preference={},
        soul_profile={},
    )

    assert notes[0].source_event_ids == [1, 2]
    assert notes[0].source_event_ids_approximate is False
    assert confusions[0]["evidence_refs"] == ["1", "2"]
    assert "source_refs" not in confusions[0]


@pytest.mark.asyncio
async def test_bounded_output_rejects_unknown_envelope_refs() -> None:
    service = _StructuredService(
        json.dumps(
            {
                "notes": [
                    {
                        "observation": "无法对应的观察",
                        "source_refs": ["E999"],
                    }
                ],
                "confusions": [],
            },
            ensure_ascii=False,
        )
    )
    analyzer = AwarenessAnalyzer(service, confusions_prompt_view="bounded-v2")

    with pytest.raises(AwarenessGenerationError, match="no valid envelope references"):
        await analyzer.analyze_with_confusions(
            events=[_event(1, content_id="BV1", author_id="11", author_name="作者甲")],
            preference={},
            soul_profile={},
        )

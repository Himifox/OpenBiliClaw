"""Contract tests for privacy-bounded proactive recommendation handoff."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from openbiliclaw import OpenBiliClawCore
from openbiliclaw.discovery.engine import DiscoveredContent
from openbiliclaw.recommendation.engine import Recommendation
from openbiliclaw.recommendation.proactive_candidate import build_proactive_candidates
from openbiliclaw.saved_sync.models import SavedItemInput
from openbiliclaw.soul.profile import InterestTag, PreferenceLayer, SoulProfile
from openbiliclaw.storage.database import Database


class _EvidenceDatabase:
    def __init__(
        self,
        *,
        saved_topics: tuple[str, ...] = (),
        subscriptions: tuple[str, ...] = (),
    ) -> None:
        self.saved_topics = saved_topics
        self.subscriptions = subscriptions

    def get_saved_topic_signals(self) -> dict[str, str]:
        return {topic: "2026-08-18T00:00:00Z" for topic in self.saved_topics}

    def get_enabled_recipes(self) -> list[dict[str, object]]:
        return [
            {
                "name": topic,
                "created_by": "user",
                "config": {"query": topic},
            }
            for topic in self.subscriptions
        ]


def _profile(*, now: datetime) -> SoulProfile:
    return SoulProfile(
        preferences=PreferenceLayer(
            interests=[
                InterestTag(
                    name="Agent 架构",
                    category="AI 编程",
                    state="active",
                    evidence_count=8,
                    first_seen=now - timedelta(days=45),
                    last_seen=now - timedelta(days=1),
                    last_evidence_at=(now - timedelta(days=1)).isoformat(),
                )
            ],
            source_platform_mix={"bilibili": 0.8, "youtube": 0.2},
        )
    )


def _recommendation(
    *,
    content_id: str = "BV1TEST",
    title: str = "减少 Agent 上下文开销的方法",
    topic: str = "Agent 架构",
    description: str = "通过结构化状态替代长历史提示词。",
    temporal_valid_until: str = "",
) -> Recommendation:
    return Recommendation(
        content=DiscoveredContent(
            bvid=content_id,
            title=title,
            description=description,
            content_url=f"https://www.bilibili.com/video/{content_id}",
            source_platform="bilibili",
            author_name="测试作者",
            content_type="video",
            temporal_class="current",
            temporal_policy_version="v2",
            temporal_valid_until=temporal_valid_until,
            temporal_evaluated_at="2026-08-19T00:00:00Z",
            temporal_evidence_complete=True,
            topic_group=topic,
            relevance_score=1.0,
            quality_score=1.0,
            evaluation_contract_version="content-eval-v7",
        ),
        expression="你昨晚连续看了五个相关视频。",
        topic_label=topic,
        confidence=1.4,
    )


def test_candidate_contract_is_stable_bounded_and_aggregate_only() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    database = _EvidenceDatabase(saved_topics=("Agent 架构",))
    recommendation = _recommendation()

    first = build_proactive_candidates(
        [recommendation], profile=_profile(now=now), database=database, now=now
    )[0]
    second = build_proactive_candidates(
        [recommendation], profile=_profile(now=now), database=database, now=now
    )[0]

    assert first.tracking.candidate_id == second.tracking.candidate_id
    assert first.tracking.candidate_id.startswith("obc:")
    assert first.tracking.expires_at is None
    assert first.tracking.delivery_ref is recommendation
    assert first.semantics.reason_codes == (
        "related_to_saved",
        "recent_interest",
        "long_term_interest",
    )
    assert first.semantics.confidence == 1.0
    assert first.confidence_components.quality == 1.0
    assert first.policy.why_now_source == "aggregated_interest"
    assert "昨晚" not in repr(first)


def test_candidate_builder_caps_three_and_drops_expired_items() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    recommendations = [
        _recommendation(content_id=f"BV{index}") for index in range(5)
    ]
    recommendations.insert(
        0,
        _recommendation(
            content_id="BVEXPIRED",
            temporal_valid_until="2026-08-18T00:00:00Z",
        ),
    )

    candidates = build_proactive_candidates(
        recommendations,
        profile=_profile(now=now),
        database=_EvidenceDatabase(),
        now=now,
    )

    assert len(candidates) == 3
    assert all(candidate.tracking.item_key != "bilibili:BVEXPIRED" for candidate in candidates)


def test_sensitive_topic_requires_current_context_or_explicit_subscription() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    candidate = _recommendation(
        content_id="BVSLEEP",
        title="睡眠改善的新研究",
        topic="睡眠改善",
        description="一项公开研究更新。",
    )

    assert build_proactive_candidates(
        [candidate],
        profile=_profile(now=now),
        database=_EvidenceDatabase(),
        now=now,
    ) == []

    contextual = build_proactive_candidates(
        [candidate],
        profile=_profile(now=now),
        database=_EvidenceDatabase(),
        explicit_context_texts=("我们继续聊聊睡眠改善",),
        now=now,
    )[0]
    assert contextual.policy.sensitivity == "health"
    assert contextual.policy.why_now_source == "current_conversation"
    assert contextual.semantics.reason_codes == ("topic_continuation",)

    subscribed = build_proactive_candidates(
        [candidate],
        profile=_profile(now=now),
        database=_EvidenceDatabase(subscriptions=("睡眠改善",)),
        now=now,
    )[0]
    assert subscribed.policy.why_now_source == "explicit_subscription"


def test_sensitive_advice_is_denied_even_with_current_context() -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    candidate = _recommendation(
        content_id="BVSTOCK",
        title="股票买入建议",
        topic="股票投资",
        description="告诉你现在应该买入什么。",
    )

    assert build_proactive_candidates(
        [candidate],
        profile=_profile(now=now),
        database=_EvidenceDatabase(subscriptions=("股票投资",)),
        explicit_context_texts=("聊聊股票投资",),
        now=now,
    ) == []


@pytest.mark.parametrize(
    ("quality", "relevance", "description", "topic", "version", "expected"),
    [
        (0.7499, 1.0, "可靠摘要", "Agent 架构", "content-eval-v7", 0),
        (0.75, 1.0, "可靠摘要", "Agent 架构", "content-eval-v7", 1),
        (1.0, 1.0, "可靠摘要", "Agent 架构", "content-eval-v7", 1),
        (None, 1.0, "可靠摘要", "Agent 架构", "content-eval-v7", 0),
        (1.0, 1.0, "", "Agent 架构", "content-eval-v7", 0),
        (1.0, 1.0, "可靠摘要", "", "content-eval-v7", 0),
        (1.0, 1.0, "可靠摘要", "Agent 架构", "", 0),
    ],
)
def test_candidate_confidence_gate_fails_closed(
    quality: float | None,
    relevance: float,
    description: str,
    topic: str,
    version: str,
    expected: int,
) -> None:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    recommendation = _recommendation(description=description, topic=topic)
    recommendation.content.quality_score = quality
    recommendation.content.relevance_score = relevance
    recommendation.content.evaluation_contract_version = version

    candidates = build_proactive_candidates(
        [recommendation], profile=_profile(now=now), database=_EvidenceDatabase(), now=now
    )

    assert len(candidates) == expected


def test_database_saved_topic_signal_is_aggregate_only(tmp_path) -> None:
    database = Database(tmp_path / "saved-topic.db")
    database.initialize()
    database.cache_content(
        "BV1SAVED",
        title="保存内容",
        source="search",
        source_platform="bilibili",
        content_id="BV1SAVED",
        content_url="https://www.bilibili.com/video/BV1SAVED",
        topic_group="Agent 架构",
    )
    database.upsert_saved_membership(
        "favorite",
        SavedItemInput(
            source_platform="bilibili",
            content_id="BV1SAVED",
            content_url="https://www.bilibili.com/video/BV1SAVED",
            content_type="video",
            title="保存内容",
            author_name="作者",
        ),
    )

    signals = database.get_saved_topic_signals()

    assert set(signals) == {"Agent 架构"}
    assert all(not isinstance(value, dict) for value in signals.values())
    database.close()


def test_builder_ignores_non_user_source_recipes() -> None:
    database = SimpleNamespace(
        get_saved_topic_signals=lambda: {},
        get_enabled_recipes=lambda: [
            {"name": "睡眠改善", "created_by": "system", "config": {}}
        ],
    )
    now = datetime(2026, 8, 19, tzinfo=UTC)
    candidate = _recommendation(
        content_id="BVSYSTEM",
        title="睡眠改善的新研究",
        topic="睡眠改善",
    )

    assert build_proactive_candidates(
        [candidate], profile=_profile(now=now), database=database, now=now
    ) == []


@pytest.mark.asyncio
async def test_core_exposes_bounded_proactive_preview_without_http() -> None:
    now = datetime.now(UTC)
    profile = _profile(now=now)
    recommendation = _recommendation()
    preview_calls: list[dict[str, object]] = []

    class _Soul:
        async def get_profile(self) -> SoulProfile:
            return profile

    class _Engine:
        async def preview_semantic(
            self, _profile: object, **kwargs: object
        ) -> list[Recommendation]:
            preview_calls.append(kwargs)
            return [recommendation]

    context = SimpleNamespace(
        soul_engine=_Soul(),
        recommendation_engine=_Engine(),
        database=_EvidenceDatabase(),
        degraded=False,
    )
    core = OpenBiliClawCore.from_context(context)  # type: ignore[arg-type]

    candidates = await core.preview_proactive_candidates(
        limit=99,
        source_platform="bilibili",
        explicit_context_texts=("old", "older", "recent", "current"),
    )

    assert len(candidates) == 1
    assert preview_calls == [
        {
            "limit": 3,
            "source_platform": "bilibili",
            "excluded_bvids": frozenset(),
        }
    ]

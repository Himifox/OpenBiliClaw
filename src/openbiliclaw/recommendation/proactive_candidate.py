"""Privacy-bounded recommendation handoff for embedded proactive hosts."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from openbiliclaw.sources.platforms import normalize_source_platform

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from openbiliclaw.recommendation.engine import Recommendation
    from openbiliclaw.soul.profile import InterestTag, OnionProfile, SoulProfile

    ProactiveProfile = SoulProfile | OnionProfile

Sensitivity = Literal["none", "health", "finance", "politics", "religion"]
ProactivePolicy = Literal[
    "allow",
    "explicit_context_only",
    "explicit_context_or_subscription",
    "deny",
]
WhyNowSource = Literal[
    "aggregated_interest",
    "current_conversation",
    "explicit_subscription",
    "public_timing",
    "none",
]
Freshness = Literal["recent", "evergreen", "unknown"]

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_RECENT_WINDOW = timedelta(days=7)
_LONG_TERM_WINDOW = timedelta(days=30)
_STABLE_EVIDENCE_COUNT = 5

# These policy lexicons intentionally prefer false negatives to inferred
# sensitive interests. They are code-owned and never expanded by an LLM.
_SENSITIVE_TERMS: dict[Sensitivity, tuple[str, ...]] = {
    "none": (),
    "health": (
        "健康",
        "疾病",
        "治疗",
        "症状",
        "药物",
        "焦虑",
        "抑郁",
        "睡眠",
        "health",
        "disease",
        "treatment",
        "symptom",
        "medical",
    ),
    "finance": (
        "股票",
        "基金",
        "金融",
        "投资",
        "贷款",
        "加密货币",
        "比特币",
        "黄金",
        "证券",
        "股市",
        "stock",
        "fund",
        "finance",
        "investment",
        "crypto",
        "loan",
    ),
    "politics": (
        "政治",
        "政党",
        "选举",
        "政府",
        "政策",
        "总统",
        "议会",
        "阵营",
        "politic",
        "election",
        "government",
        "policy",
    ),
    "religion": (
        "宗教",
        "信仰",
        "教派",
        "宗派",
        "基督教",
        "佛教",
        "伊斯兰",
        "天主教",
        "religion",
        "faith",
        "church",
    ),
}
_DENY_TERMS: dict[Sensitivity, tuple[str, ...]] = {
    "none": (),
    "health": ("诊断", "治疗方案", "处方", "用药", "剂量", "diagnose", "dosage"),
    "finance": (
        "买入",
        "卖出",
        "加仓",
        "抄底",
        "收益保证",
        "投资建议",
        "buy now",
        "sell now",
        "guaranteed return",
    ),
    "politics": ("投票给", "支持阵营", "反对阵营", "政治立场", "vote for"),
    "religion": ("入教", "皈依", "信仰判断", "宗教倾向", "convert to"),
}


@dataclass(frozen=True, slots=True)
class CandidateTracking:
    """Host-only identity and delivery state; never a prompt payload."""

    candidate_id: str
    item_key: str
    url: str
    expires_at: str | None
    delivery_ref: Recommendation = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class CandidateSemantics:
    """Bounded content facts and aggregate-only recommendation evidence."""

    title: str
    topic: str
    summary: str
    reason_codes: tuple[str, ...]
    source_platform: str
    author_name: str
    content_type: str
    confidence: float
    freshness: Freshness


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    """Deterministic proactive privacy decision."""

    sensitivity: Sensitivity
    proactive_policy: ProactivePolicy
    why_now_source: WhyNowSource


@dataclass(frozen=True, slots=True)
class ProactiveRecommendationCandidate:
    """Same-process handoff consumed by an embedded proactive host."""

    tracking: CandidateTracking
    semantics: CandidateSemantics
    policy: CandidatePolicy


def _bounded_text(value: object, limit: int, *, strip_markup: bool = False) -> str:
    text = html.unescape(str(value or ""))
    if strip_markup:
        text = _TAG_RE.sub(" ", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.category(character).startswith("C")
        or character in "\n\t"
    )
    return _SPACE_RE.sub(" ", text).strip()[:limit]


def _normalized_match_text(value: object) -> str:
    return "".join(
        character.casefold()
        for character in _bounded_text(value, 512)
        if character.isalnum()
    )


def _parse_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _matches_topic(topic: str, candidate: object) -> bool:
    left = _normalized_match_text(topic)
    right = _normalized_match_text(candidate)
    return bool(left and right and (left in right or right in left))


def _matching_interests(profile: ProactiveProfile, topic: str) -> list[InterestTag]:
    matches: list[InterestTag] = []
    for interest in profile.preferences.interests:
        if _matches_topic(topic, interest.name) or _matches_topic(topic, interest.category):
            matches.append(interest)
    return matches


def _saved_topics(database: object) -> frozenset[str]:
    load = getattr(database, "get_saved_topic_signals", None)
    if not callable(load):
        return frozenset()
    return frozenset(
        str(topic).strip()
        for topic in load()
        if str(topic).strip()
    )


def _explicit_subscription_topics(database: object) -> tuple[str, ...]:
    load = getattr(database, "get_enabled_recipes", None)
    if not callable(load):
        return ()
    topics: list[str] = []
    for recipe in load():
        if not isinstance(recipe, dict) or str(recipe.get("created_by", "")) not in {
            "agent",
            "user",
        }:
            continue
        topics.append(str(recipe.get("name", "")))
        config = recipe.get("config")
        if not isinstance(config, dict):
            continue
        for key in ("query", "topic"):
            topics.append(str(config.get(key, "")))
        keywords = config.get("keywords")
        if isinstance(keywords, list):
            topics.extend(str(item) for item in keywords)
    return tuple(topic.strip() for topic in topics if topic.strip())


def _has_explicit_context(
    *,
    topic: str,
    sensitivity: Sensitivity,
    context_texts: Sequence[str],
) -> bool:
    topic_key = _normalized_match_text(topic)
    terms = _SENSITIVE_TERMS[sensitivity]
    for raw_text in context_texts[-3:]:
        text = _normalized_match_text(raw_text)
        if topic_key and topic_key in text:
            return True
        if any(
            _normalized_match_text(term) in text
            and _normalized_match_text(term) in topic_key
            for term in terms
        ):
            return True
    return False


def _sensitivity(text: str) -> Sensitivity:
    normalized = _normalized_match_text(text)
    for sensitivity in ("health", "finance", "politics", "religion"):
        if any(
            _normalized_match_text(term) in normalized
            for term in _SENSITIVE_TERMS[sensitivity]
        ):
            return sensitivity
    return "none"


def _is_denied_sensitive_text(text: str, sensitivity: Sensitivity) -> bool:
    normalized = _normalized_match_text(text)
    return any(_normalized_match_text(term) in normalized for term in _DENY_TERMS[sensitivity])


def _is_explicit_subscription(topic: str, subscription_topics: Iterable[str]) -> bool:
    return any(_matches_topic(topic, subscribed) for subscribed in subscription_topics)


def _reason_codes(
    *,
    profile: ProactiveProfile,
    topic: str,
    source_platform: str,
    saved_topics: Iterable[str],
    explicit_context: bool,
    explicit_subscription: bool,
    now: datetime,
) -> tuple[str, ...]:
    codes: list[str] = []
    matches = _matching_interests(profile, topic)
    if explicit_context:
        codes.append("topic_continuation")
    if any(_matches_topic(topic, saved) for saved in saved_topics):
        codes.append("related_to_saved")
    if explicit_subscription and "source_affinity" not in codes:
        codes.append("source_affinity")

    for interest in matches:
        last_evidence = _parse_datetime(interest.last_evidence_at) or interest.last_seen
        if last_evidence is not None and last_evidence.tzinfo is None:
            last_evidence = last_evidence.replace(tzinfo=UTC)
        recent = bool(last_evidence and now - last_evidence.astimezone(UTC) <= _RECENT_WINDOW)
        if interest.state == "trial" and recent:
            codes.append("emerging_interest")
        elif recent:
            codes.append("recent_interest")
        first_seen = interest.first_seen
        if first_seen is not None and first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=UTC)
        if interest.state == "active" and (
            (first_seen is not None and now - first_seen.astimezone(UTC) >= _LONG_TERM_WINDOW)
            or interest.evidence_count >= _STABLE_EVIDENCE_COUNT
        ):
            codes.append("long_term_interest")
    if matches and not any(
        code in codes
        for code in ("recent_interest", "emerging_interest", "long_term_interest")
    ):
        codes.append("topic_continuation")

    mix = profile.preferences.source_platform_mix
    if mix:
        dominant = max(mix, key=lambda key: float(mix.get(key, 0.0) or 0.0))
        if normalize_source_platform(dominant) == normalize_source_platform(source_platform):
            codes.append("source_affinity")

    priority = (
        "topic_continuation" if explicit_context else "",
        "related_to_saved",
        "recent_interest",
        "emerging_interest",
        "long_term_interest",
        "topic_continuation",
        "source_affinity",
    )
    return tuple(code for code in dict.fromkeys(priority) if code and code in codes)[:3]


def _freshness(content: object, now: datetime) -> Freshness:
    temporal_class = str(getattr(content, "temporal_class", "") or "").strip().lower()
    if temporal_class in {"evergreen", "historical"}:
        return "evergreen"
    published_at = _parse_datetime(getattr(content, "published_at", ""))
    if temporal_class in {"breaking", "current"} or (
        published_at is not None and now - published_at <= _RECENT_WINDOW
    ):
        return "recent"
    return "unknown"


def build_proactive_candidates(
    recommendations: Sequence[Recommendation],
    *,
    profile: ProactiveProfile,
    database: object,
    explicit_context_texts: Sequence[str] = (),
    now: datetime | None = None,
) -> list[ProactiveRecommendationCandidate]:
    """Build bounded, non-consuming candidates for one embedded host call."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    saved_topics = _saved_topics(database)
    subscription_topics = _explicit_subscription_topics(database)
    candidates: list[ProactiveRecommendationCandidate] = []
    seen_ids: set[str] = set()
    for recommendation in recommendations:
        if len(candidates) >= 3:
            break
        content = recommendation.content
        item_key = str(content.item_key or "").strip()
        url = str(content.content_url or "").strip()
        title = _bounded_text(content.title, 60)
        topic = _bounded_text(
            recommendation.topic_label or content.topic_group or content.topic_key,
            16,
        )
        if not item_key or not url or not title or not topic:
            continue
        expires = _parse_datetime(content.temporal_valid_until)
        if expires is not None and expires <= current:
            continue
        summary = _bounded_text(
            content.description or content.body_text or title,
            80,
            strip_markup=True,
        )
        combined = " ".join((title, topic, summary))
        sensitivity = _sensitivity(combined)
        if _is_denied_sensitive_text(combined, sensitivity):
            continue
        explicit_context = _has_explicit_context(
            topic=topic,
            sensitivity=sensitivity,
            context_texts=explicit_context_texts,
        )
        explicit_subscription = _is_explicit_subscription(topic, subscription_topics)
        if sensitivity == "none":
            policy: ProactivePolicy = "allow"
            why_now_source: WhyNowSource = "aggregated_interest"
        elif explicit_context:
            policy = "explicit_context_only"
            why_now_source = "current_conversation"
        elif explicit_subscription:
            policy = "explicit_context_or_subscription"
            why_now_source = "explicit_subscription"
        else:
            continue

        codes = _reason_codes(
            profile=profile,
            topic=topic,
            source_platform=content.source_platform,
            saved_topics=saved_topics,
            explicit_context=explicit_context,
            explicit_subscription=explicit_subscription,
            now=current,
        )
        if sensitivity != "none" and why_now_source == "current_conversation":
            codes = ("topic_continuation",)
        elif sensitivity != "none" and why_now_source == "explicit_subscription":
            codes = ("source_affinity",)
        if not codes and why_now_source == "aggregated_interest":
            why_now_source = "public_timing"

        candidate_id = "obc:" + hashlib.blake2s(
            item_key.encode("utf-8"), digest_size=8
        ).hexdigest()
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        candidates.append(
            ProactiveRecommendationCandidate(
                tracking=CandidateTracking(
                    candidate_id=candidate_id,
                    item_key=item_key,
                    url=url,
                    expires_at=(
                        expires.isoformat().replace("+00:00", "Z") if expires is not None else None
                    ),
                    delivery_ref=recommendation,
                ),
                semantics=CandidateSemantics(
                    title=title,
                    topic=topic,
                    summary=summary,
                    reason_codes=codes,
                    source_platform=normalize_source_platform(content.source_platform),
                    author_name=_bounded_text(content.author_name or content.up_name, 60),
                    content_type=_bounded_text(content.content_type or "video", 20),
                    confidence=min(1.0, max(0.0, float(recommendation.confidence or 0.0))),
                    freshness=_freshness(content, current),
                ),
                policy=CandidatePolicy(
                    sensitivity=sensitivity,
                    proactive_policy=policy,
                    why_now_source=why_now_source,
                ),
            )
        )
    return candidates

"""Identity-safe bounded activity views for Awareness prompts.

The durable event ledger remains unchanged.  This module groups only
consecutive rows into indivisible envelopes, keeps identity/tracking data out
of model text, and derives author and interest context from the same envelope.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

_CONTRACT_VERSION = "awareness-envelope-v1"
_SESSION_SECONDS = 30 * 60
_TITLE_MAX_CHARS = 60
_SUMMARY_MAX_CHARS = 100
_AUTHOR_MAX_CHARS = 40
_BASELINE_INTEREST_CAP = 8
_INTERESTS_PER_ENVELOPE = 2
_RELATED_INTEREST_CAP = 24

_CONTENT_ID_KEYS = (
    "bvid",
    "video_id",
    "content_id",
    "item_id",
    "article_id",
    "note_id",
    "post_id",
)
_AUTHOR_ID_KEYS = (
    "author_id",
    "author_mid",
    "owner_mid",
    "up_mid",
    "user_id",
    "uid",
    "mid",
)
_AUTHOR_NAME_KEYS = (
    "author_name",
    "owner_name",
    "up_name",
    "uname",
    "author",
)
_PLATFORM_KEYS = ("source_platform", "platform")
_URL_KEYS = ("canonical_url", "content_url", "page_url", "url")
_SEMANTIC_METADATA_KEYS = (
    "description",
    "body_text",
    "content_type",
    "duration",
    "progress",
    "signal_strength",
    "tags",
)
_NORMALIZE_RE = re.compile(r"[\W_]+", re.UNICODE)


def _text(value: object, *, limit: int = 0) -> str:
    rendered = " ".join(str(value or "").split())
    return rendered[:limit] if limit > 0 else rendered


def _metadata(event: Mapping[str, object]) -> dict[str, object]:
    raw = event.get("metadata")
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
    return {}


def _first_text(*sources: Mapping[str, object], keys: Sequence[str]) -> str:
    for source in sources:
        for key in keys:
            value = _text(source.get(key))
            if value:
                return value
    return ""


def _normalize(value: object) -> str:
    return _NORMALIZE_RE.sub("", _text(value).lower())


def _event_id(event: Mapping[str, object]) -> int:
    raw = event.get("id", 0)
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _event_time(event: Mapping[str, object]) -> datetime | None:
    raw = event.get("created_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    text = _text(raw)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _session_bucket(event: Mapping[str, object]) -> int:
    occurred_at = _event_time(event)
    if occurred_at is None:
        return _event_id(event)
    return int(occurred_at.timestamp()) // _SESSION_SECONDS


def _platform(event: Mapping[str, object], metadata: Mapping[str, object]) -> str:
    return _first_text(metadata, event, keys=_PLATFORM_KEYS).lower() or "unknown"


def _content_key(event: Mapping[str, object], metadata: Mapping[str, object]) -> str:
    platform = _platform(event, metadata)
    content_id = _first_text(metadata, event, keys=_CONTENT_ID_KEYS)
    if content_id:
        return f"{platform}:id:{content_id}"
    url = _first_text(metadata, event, keys=_URL_KEYS)
    if url:
        digest = hashlib.blake2s(url.encode("utf-8"), digest_size=8).hexdigest()
        return f"{platform}:url:{digest}"
    return f"{platform}:event:{_event_id(event)}"


def _author_identity(
    event: Mapping[str, object], metadata: Mapping[str, object], content_key: str
) -> tuple[str | None, str | None]:
    platform = _platform(event, metadata)
    author_id = _first_text(metadata, event, keys=_AUTHOR_ID_KEYS)
    author_name = _first_text(metadata, event, keys=_AUTHOR_NAME_KEYS)
    if author_id:
        return f"{platform}:uid:{author_id}", _text(author_name, limit=_AUTHOR_MAX_CHARS) or None
    if author_name:
        normalized = _normalize(author_name)
        digest = hashlib.blake2s(f"{content_key}\0{normalized}".encode(), digest_size=8).hexdigest()
        return f"{platform}:name:{digest}", _text(author_name, limit=_AUTHOR_MAX_CHARS)
    return None, None


def _interest_ref(name: str, category: str) -> str:
    digest = hashlib.blake2s(
        f"{_normalize(category)}\0{_normalize(name)}".encode(), digest_size=8
    ).hexdigest()
    return f"interest:{digest}"


def _finite_unit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _evidence_level(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return "unknown"
    try:
        count = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if count >= 5:
        return "strong"
    if count >= 2:
        return "medium"
    return "low" if count == 1 else "unknown"


def _recency(value: object, *, now: datetime) -> str:
    text = _text(value)
    if not text:
        return "unknown"
    try:
        seen = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    age_days = max(0, (now.astimezone(UTC) - seen.astimezone(UTC)).days)
    if age_days <= 7:
        return "recent"
    if age_days <= 30:
        return "established"
    return "long_term"


@dataclass(frozen=True)
class MatchedInterest:
    """One bounded preference projection tied to one activity envelope."""

    interest_ref: str
    name: str
    category: str
    weight: float
    state: str
    evidence_level: str
    recency: str
    match_score: float

    def prompt_view(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category,
            "weight": round(self.weight, 4),
            "state": self.state,
            "evidence_level": self.evidence_level,
            "recency": self.recency,
        }


@dataclass(frozen=True)
class ActivityEnvelopeTracking:
    envelope_id: str
    content_key: str
    event_ids: tuple[int, ...]
    first_event_id: int
    last_event_id: int
    source_platform: str
    author_key: str | None


@dataclass(frozen=True)
class ActivityEnvelopeSemantics:
    title: str
    summary: str
    author_name: str | None
    activity_counts: tuple[tuple[str, int], ...]
    engagement: str
    matched_interests: tuple[MatchedInterest, ...]


@dataclass(frozen=True)
class ActivityEnvelope:
    tracking: ActivityEnvelopeTracking
    semantics: ActivityEnvelopeSemantics
    raw_events: tuple[dict[str, object], ...]

    def prompt_view(self, ref: str) -> dict[str, object]:
        result: dict[str, object] = {
            "ref": ref,
            "title": self.semantics.title,
            "activity": dict(self.semantics.activity_counts),
            "engagement": self.semantics.engagement,
            "source_platform": self.tracking.source_platform,
        }
        if self.semantics.summary:
            result["summary"] = self.semantics.summary
        if self.semantics.author_name:
            result["author"] = self.semantics.author_name
        if self.semantics.matched_interests:
            result["matched_interests"] = [
                item.prompt_view() for item in self.semantics.matched_interests
            ]
        return result


@dataclass(frozen=True)
class ActivityEnvelopeManifest:
    """Private ref → durable identity mapping for one prompt call."""

    envelopes: tuple[ActivityEnvelope, ...]

    def by_ref(self) -> dict[str, ActivityEnvelope]:
        return {f"E{index:03d}": item for index, item in enumerate(self.envelopes, start=1)}

    def digest(self) -> str:
        payload = [
            {
                "envelope_id": item.tracking.envelope_id,
                "event_ids": list(item.tracking.event_ids),
            }
            for item in self.envelopes
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.blake2s(encoded, digest_size=16).hexdigest()

    def event_ids_for_refs(self, refs: Sequence[str]) -> list[int] | None:
        mapping = self.by_ref()
        if not refs:
            return None
        selected: list[int] = []
        seen: set[int] = set()
        for raw_ref in refs:
            ref = _text(raw_ref).upper()
            envelope = mapping.get(ref)
            if envelope is None:
                return None
            for event_id in envelope.tracking.event_ids:
                if event_id not in seen:
                    selected.append(event_id)
                    seen.add(event_id)
        return sorted(selected)


def _interest_candidates(
    preference: Mapping[str, object], *, now: datetime
) -> list[MatchedInterest]:
    raw = preference.get("interests")
    if not isinstance(raw, list):
        return []
    deduplicated: dict[str, MatchedInterest] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _text(item.get("name") or item.get("topic"), limit=40)
        if not name:
            continue
        category = _text(item.get("category"), limit=24)
        ref = _interest_ref(name, category)
        candidate = MatchedInterest(
            interest_ref=ref,
            name=name,
            category=category,
            weight=_finite_unit(item.get("weight")),
            state=_text(item.get("state"), limit=16) or "unknown",
            evidence_level=_evidence_level(item.get("evidence_count")),
            recency=_recency(item.get("last_evidence_at") or item.get("last_seen"), now=now),
            match_score=0.0,
        )
        previous = deduplicated.get(ref)
        if previous is None or candidate.weight > previous.weight:
            deduplicated[ref] = candidate
    return sorted(
        deduplicated.values(),
        key=lambda item: (-item.weight, item.category, item.name, item.interest_ref),
    )


def baseline_interests(
    preference: Mapping[str, object], *, now: datetime | None = None
) -> list[dict[str, object]]:
    current = now or datetime.now(UTC)
    return [
        item.prompt_view()
        for item in _interest_candidates(preference, now=current)[:_BASELINE_INTEREST_CAP]
    ]


def _match_interests(
    *,
    title: str,
    summary: str,
    metadata: Sequence[Mapping[str, object]],
    candidates: Sequence[MatchedInterest],
) -> list[MatchedInterest]:
    semantic_parts = [title, summary]
    for item in metadata:
        for key in ("tags", "topic", "category", "description"):
            semantic_parts.append(_text(item.get(key)))
    haystack = _normalize(" ".join(semantic_parts))
    if not haystack:
        return []
    matched: list[MatchedInterest] = []
    for candidate in candidates:
        needle = _normalize(candidate.name)
        if len(needle) < 2 or needle not in haystack:
            continue
        matched.append(
            MatchedInterest(
                **{
                    **candidate.__dict__,
                    "match_score": min(1.0, 0.7 + candidate.weight * 0.3),
                }
            )
        )
    return sorted(
        matched,
        key=lambda item: (-item.match_score, -item.weight, item.name, item.interest_ref),
    )[:_INTERESTS_PER_ENVELOPE]


def _engagement(counts: Counter[str]) -> str:
    if counts["favorite"] or counts["follow"] or counts["comment"]:
        return "explicit_intent"
    if counts["search"] or counts["seek"] or counts["pause"]:
        return "targeted_lookup"
    if counts["view"]:
        return "viewed"
    if counts["click"]:
        return "clicked"
    return "light_browse"


def _group_key(event: Mapping[str, object]) -> tuple[str, int, str | None]:
    metadata = _metadata(event)
    content_key = _content_key(event, metadata)
    author_key, _ = _author_identity(event, metadata, content_key)
    return content_key, _session_bucket(event), author_key


def _build_one(
    events: Sequence[Mapping[str, object]],
    *,
    interests: Sequence[MatchedInterest],
    related_refs: set[str],
) -> ActivityEnvelope:
    detached = tuple(dict(event) for event in events)
    first = detached[0]
    first_metadata = _metadata(first)
    content_key = _content_key(first, first_metadata)
    platform = _platform(first, first_metadata)
    author_key, author_name = _author_identity(first, first_metadata, content_key)
    event_ids = tuple(_event_id(event) for event in detached if _event_id(event) > 0)
    title = _text(
        next((event.get("title") for event in detached if _text(event.get("title"))), ""),
        limit=_TITLE_MAX_CHARS,
    )
    metadata_rows = [_metadata(event) for event in detached]
    summary = _text(
        next(
            (
                value
                for metadata in metadata_rows
                for key in ("description", "body_text")
                if (value := metadata.get(key)) and _text(value)
            ),
            next(
                (event.get("context") for event in detached if _text(event.get("context"))),
                "",
            ),
        ),
        limit=_SUMMARY_MAX_CHARS,
    )
    matched = _match_interests(
        title=title,
        summary=summary,
        metadata=metadata_rows,
        candidates=interests,
    )
    admitted: list[MatchedInterest] = []
    for item in matched:
        if item.interest_ref in related_refs or len(related_refs) < _RELATED_INTEREST_CAP:
            related_refs.add(item.interest_ref)
            admitted.append(item)
    counts = Counter(_text(event.get("event_type") or event.get("type")) for event in detached)
    counts.pop("", None)
    first_id = min(event_ids) if event_ids else 0
    last_id = max(event_ids) if event_ids else 0
    digest_input = (
        f"{_CONTRACT_VERSION}\0{content_key}\0{_session_bucket(first)}\0{first_id}\0{last_id}"
    )
    envelope_id = hashlib.blake2s(digest_input.encode("utf-8"), digest_size=16).hexdigest()
    return ActivityEnvelope(
        tracking=ActivityEnvelopeTracking(
            envelope_id=envelope_id,
            content_key=content_key,
            event_ids=event_ids,
            first_event_id=first_id,
            last_event_id=last_id,
            source_platform=platform,
            author_key=author_key,
        ),
        semantics=ActivityEnvelopeSemantics(
            title=title or "（无标题内容）",
            summary=summary,
            author_name=author_name,
            activity_counts=tuple(sorted(counts.items())),
            engagement=_engagement(counts),
            matched_interests=tuple(admitted),
        ),
        raw_events=detached,
    )


def build_activity_envelopes(
    events: Sequence[Mapping[str, object]],
    preference: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> tuple[ActivityEnvelope, ...]:
    """Group consecutive events without losing or duplicating any event row."""

    if not events:
        return ()
    current = now or datetime.now(UTC)
    interests = _interest_candidates(preference, now=current)
    groups: list[list[Mapping[str, object]]] = []
    for event in events:
        if not groups or _group_key(groups[-1][-1]) != _group_key(event):
            groups.append([event])
        else:
            groups[-1].append(event)
    related_refs: set[str] = set()
    envelopes = tuple(
        _build_one(group, interests=interests, related_refs=related_refs) for group in groups
    )
    input_ids = [_event_id(event) for event in events if _event_id(event) > 0]
    output_ids = [event_id for item in envelopes for event_id in item.tracking.event_ids]
    if input_ids != output_ids or len(output_ids) != len(set(output_ids)):
        raise ValueError("activity envelope projection must preserve each event id exactly once")
    return envelopes


def bounded_event_metadata(event: Mapping[str, object]) -> dict[str, object]:
    """Return the small semantic metadata subset used only by diagnostics/tests."""

    metadata = _metadata(event)
    return {
        key: metadata[key]
        for key in _SEMANTIC_METADATA_KEYS
        if key in metadata and metadata[key] not in (None, "", [], {})
    }


__all__ = [
    "ActivityEnvelope",
    "ActivityEnvelopeManifest",
    "ActivityEnvelopeSemantics",
    "ActivityEnvelopeTracking",
    "MatchedInterest",
    "baseline_interests",
    "bounded_event_metadata",
    "build_activity_envelopes",
]

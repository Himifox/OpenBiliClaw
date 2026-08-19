"""Token-balanced embedded runtime boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openbiliclaw import OpenBiliClawCore
from openbiliclaw.storage.database import Database


def _cache_semantic_candidate(database: Database, bvid: str = "BVSEMANTIC") -> None:
    database.cache_content(
        bvid,
        title="结构化状态减少上下文开销",
        description="通过结构化状态替代冗长历史提示词。",
        source="search",
        source_platform="bilibili",
        content_id=bvid,
        content_url=f"https://www.bilibili.com/video/{bvid}",
        style_key="deep_focus",
        topic_group="Agent 架构",
        relevance_score=0.91,
        relevance_reason="与长期兴趣相关",
        quality_score=0.88,
        evaluation_contract_version="content-eval-v7",
        temporal_class="evergreen",
        temporal_confidence=0.95,
        temporal_reason="核心价值不依赖当前时间",
        temporal_policy_version="v2",
        temporal_validity_mode="none",
        temporal_valid_until="",
        temporal_scope="none",
        temporal_state="unknown",
        temporal_evidence="",
        temporal_evaluated_at=datetime.now(UTC).isoformat(),
        temporal_evidence_complete=True,
    )


def test_semantic_pool_does_not_relax_public_copy_gate(tmp_path) -> None:
    database = Database(tmp_path / "semantic.db")
    database.initialize()
    _cache_semantic_candidate(database)

    assert database.get_pool_candidates(limit=3) == []
    semantic = database.get_semantic_pool_candidates(limit=3)

    assert [row["bvid"] for row in semantic] == ["BVSEMANTIC"]
    assert semantic[0]["pool_expression"] == ""
    database.close()


def test_exact_evaluation_cache_survives_database_restart(tmp_path) -> None:
    path = tmp_path / "evaluation-cache.db"
    first = Database(path)
    first.initialize()
    result: list[object] = [
        0.9,
        "可靠且相关",
        "Agent 架构",
        "deep_focus",
        "",
        "evergreen",
        0.9,
        "核心价值不依赖当前时间",
        "v2",
        "none",
        "",
        "none",
        "",
        "unknown",
        "",
        "2026-08-19T00:00:00Z",
        True,
        0.85,
        "content-eval-v7",
    ]
    first.put_evaluation_result_cache("digest", result)
    first.close()

    second = Database(path)
    second.initialize()
    assert second.get_evaluation_result_cache("digest") == result
    second.close()


def test_core_rejects_unknown_surface_copy_mode() -> None:
    with pytest.raises(ValueError, match="surface_copy_mode"):
        OpenBiliClawCore.create(surface_copy_mode="eager")  # type: ignore[arg-type]

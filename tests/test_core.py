from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from openbiliclaw import OpenBiliClawCore

if TYPE_CHECKING:
    from pathlib import Path


class _Registry:
    def __init__(self) -> None:
        self.cancelled = 0

    async def cancel_all(self) -> int:
        self.cancelled += 1
        return 0


class _Queue:
    def __init__(self) -> None:
        self.closed = False

    async def shutdown(self, *, timeout: float) -> None:
        assert timeout == 30
        self.closed = True


class _Client:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _Database:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Soul:
    async def get_profile(self) -> str:
        return "profile"


class _Recommendations:
    async def serve(self, profile: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"profile": profile, **kwargs}]


class _Dialogue:
    async def respond(self, message: str, *, session: str) -> str:
        return f"{session}:{message}"


class _Events:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

    async def publish(self, event: dict[str, object]) -> None:
        self.items.append(event)


class _Context:
    def __init__(self) -> None:
        self.config = SimpleNamespace(name="initial")
        self.degraded = False
        self.degraded_reason = ""
        self.degraded_issues: list[Any] = []
        self.task_registry = _Registry()
        self.dialogue_settlement_queue = _Queue()
        self.bangumi_client = _Client()
        self.v2ex_client = _Client()
        self.weibo_client = _Client()
        self.database = _Database()
        self.soul_engine = _Soul()
        self.recommendation_engine = _Recommendations()
        self.dialogue = _Dialogue()
        self.event_hub = _Events()
        self.restart_calls = 0
        self.rebuild_calls: list[Any] = []

    async def restart_background_tasks(
        self,
        owner: Any,
        *,
        run_post_reload_llm_work: bool = True,
    ) -> None:
        self.restart_calls += 1
        owner.state.refresh_task = asyncio.create_task(asyncio.sleep(3600))
        owner.state.account_sync_task = None
        owner.state.auto_update_task = None

    async def rebuild_from_config(self, config: Any) -> None:
        self.rebuild_calls.append(config)
        self.config = config


@pytest.mark.asyncio
async def test_core_runs_without_fastapi_and_owns_lifecycle() -> None:
    context = _Context()
    core = OpenBiliClawCore.from_context(context, owns_database=True)  # type: ignore[arg-type]

    await core.start()

    assert core.started is True
    assert context.restart_calls == 1
    assert core.state.refresh_task is not None

    await core.stop()

    assert core.started is False
    assert context.task_registry.cancelled == 1
    assert context.dialogue_settlement_queue.closed is True
    assert context.bangumi_client.closed is True
    assert context.v2ex_client.closed is True
    assert context.weibo_client.closed is True
    assert context.database.closed is True

    await core.stop()

    assert context.task_registry.cancelled == 1


@pytest.mark.asyncio
async def test_core_reload_rebuilds_and_restarts_running_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _Context()
    core = OpenBiliClawCore.from_context(context)  # type: ignore[arg-type]
    monkeypatch.setattr(core, "_configure_process_runtime", lambda config: None)
    await core.start()
    old_task = core.state.refresh_task
    assert old_task is not None
    old_task.cancel()
    await asyncio.gather(old_task, return_exceptions=True)
    new_config = SimpleNamespace(name="next")

    await core.reload(new_config)  # type: ignore[arg-type]

    assert context.rebuild_calls == [new_config]
    assert core.config is new_config
    assert context.restart_calls == 2
    await core.stop()


@pytest.mark.asyncio
async def test_core_reload_rejects_live_data_directory_move(tmp_path: Path) -> None:
    context = _Context()
    context.config = SimpleNamespace(data_path=tmp_path / "current")
    core = OpenBiliClawCore.from_context(context)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="data_dir"):
        await core.reload(  # type: ignore[arg-type]
            SimpleNamespace(data_path=tmp_path / "next")
        )

    assert context.rebuild_calls == []


def test_core_rejects_restart_after_close() -> None:
    async def _exercise() -> None:
        core = OpenBiliClawCore.from_context(_Context())  # type: ignore[arg-type]
        await core.stop()
        with pytest.raises(RuntimeError, match="closed Core"):
            await core.start()

    asyncio.run(_exercise())


def test_fastapi_can_wrap_an_existing_core() -> None:
    from openbiliclaw.api.app import create_app
    from openbiliclaw.api.runtime_context import RuntimeContext
    from openbiliclaw.config import Config

    context = RuntimeContext(
        database=object(),
        memory_manager=object(),
        soul_engine=object(),
        config=Config(),
    )
    core = OpenBiliClawCore.from_context(context)

    app = create_app(core=core, project_stats_service=object())

    assert app.state.core is core
    assert app.state.runtime_context is context
    with pytest.raises(ValueError, match="either core or individual"):
        create_app(core=core, database=object())


@pytest.mark.asyncio
async def test_degraded_core_still_wraps_http_without_starting_background_work() -> None:
    from openbiliclaw.api.app import create_app
    from openbiliclaw.api.runtime_context import RuntimeContext
    from openbiliclaw.config import Config

    context = RuntimeContext(
        database=object(),
        memory_manager=object(),
        soul_engine=object(),
        config=Config(),
    )
    context.degraded = True
    context.degraded_reason = "host model is not configured"
    core = OpenBiliClawCore.from_context(context)

    await core.start()
    app = create_app(core=core, project_stats_service=object())

    assert core.degraded is True
    assert core.started is False
    assert app.state.core is core
    assert app.state.runtime_context is context
    await core.stop()


@pytest.mark.asyncio
async def test_core_exposes_host_facing_operations_without_http() -> None:
    context = _Context()
    core = OpenBiliClawCore.from_context(context)  # type: ignore[arg-type]

    assert await core.get_profile() == "profile"
    assert await core.chat(" hello ", session="neko") == "neko:hello"
    assert await core.recommend(limit=2, source_platform="bilibili") == [
        {
            "profile": "profile",
            "limit": 2,
            "source_platform": "bilibili",
            "excluded_bvids": frozenset(),
        }
    ]
    await core.publish_event({"type": "host.ready"})
    assert context.event_hub.items == [{"type": "host.ready"}]

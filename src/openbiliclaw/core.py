"""Embeddable OpenBiliClaw runtime without an HTTP server dependency."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from openbiliclaw.api.runtime_context import RuntimeContext
    from openbiliclaw.config import Config
    from openbiliclaw.recommendation.engine import Recommendation
    from openbiliclaw.soul.profile import OnionProfile


class OpenBiliClawCore:
    """Own the business runtime and its process-local lifecycle.

    Hosts such as NEKO can embed this class directly. FastAPI and the CLI are
    adapters around the same object; neither is required to build or run it.
    """

    def __init__(
        self,
        context: RuntimeContext,
        *,
        config: Config | None = None,
        owns_database: bool = False,
    ) -> None:
        self.context = context
        self._config = config
        self._owns_database = owns_database
        configured_data_path = getattr(config, "data_path", None)
        self._active_data_path = (
            Path(configured_data_path).expanduser().resolve()
            if configured_data_path is not None
            else None
        )
        self._started = False
        self._closed = False
        # ``RuntimeContext.restart_background_tasks`` historically accepted a
        # FastAPI object and stored task handles on ``app.state``. Keeping the
        # same narrow shape here lets Core own those tasks without coupling the
        # runtime to FastAPI or breaking injected test runtimes.
        self.state = SimpleNamespace(
            refresh_task=None,
            account_sync_task=None,
            auto_update_task=None,
        )

    @classmethod
    def create(
        cls,
        config: Config | None = None,
        *,
        memory_manager: Any | None = None,
        database: Any | None = None,
        event_hub: Any | None = None,
        allow_degraded: bool = True,
    ) -> Self:
        """Build a fully wired Core from configuration and optional adapters."""
        from openbiliclaw.api.runtime_context import (
            build_degraded_runtime_context,
            build_runtime_context,
        )
        from openbiliclaw.config import load_config
        from openbiliclaw.llm.registry import RegistryBuildError

        runtime_config = config or load_config()
        cls._configure_process_runtime(runtime_config)
        owns_database = database is None
        try:
            context = build_runtime_context(
                runtime_config,
                memory_manager=memory_manager,
                database=database,
                event_hub=event_hub,
            )
        except RegistryBuildError as exc:
            if not allow_degraded:
                raise
            context = build_degraded_runtime_context(
                runtime_config,
                memory_manager=memory_manager,
                database=database,
                event_hub=event_hub,
                exc=exc,
            )
        return cls(
            context,
            config=runtime_config,
            owns_database=owns_database,
        )

    @classmethod
    def from_context(
        cls,
        context: RuntimeContext,
        *,
        config: Config | None = None,
        owns_database: bool = False,
    ) -> Self:
        """Wrap an injected runtime context in the standard lifecycle."""
        return cls(
            context,
            config=config or getattr(context, "config", None),
            owns_database=owns_database,
        )

    @staticmethod
    def _configure_process_runtime(config: Config) -> None:
        """Apply the small process-wide switches required by runtime clients."""
        from openbiliclaw.discovery.strategies._utils import (
            set_topic_lifecycle_serialization,
        )
        from openbiliclaw.network import set_outbound_proxy

        network = getattr(config, "network", None)
        set_outbound_proxy(
            getattr(network, "proxy", "") or "",
            mode=getattr(network, "mode", "system") or "system",
        )
        soul = getattr(config, "soul", None)
        set_topic_lifecycle_serialization(
            str(getattr(soul, "topic_lifecycle_serialization", "off")).strip().lower()
            == "on"
        )

    @property
    def config(self) -> Config:
        """Return the currently active runtime configuration."""
        current = getattr(self.context, "config", None) or self._config
        if current is None:
            raise RuntimeError("Core has no active configuration")
        return current

    @property
    def started(self) -> bool:
        """Whether this Core has admitted its background runtime loops."""
        return self._started

    @property
    def degraded(self) -> bool:
        """Whether Core only exposes recovery-capable components."""
        return bool(getattr(self.context, "degraded", False))

    def _require_service(self, name: str) -> Any:
        service = getattr(self.context, name, None)
        if service is None:
            raise RuntimeError(f"Core service is unavailable: {name}")
        return service

    async def get_profile(self) -> OnionProfile:
        """Return the current effective preference profile."""
        return cast(
            "OnionProfile",
            await self._require_service("soul_engine").get_profile(),
        )

    async def recommend(
        self,
        *,
        limit: int = 5,
        source_platform: str = "",
        excluded_content_ids: frozenset[str] = frozenset(),
    ) -> list[Recommendation]:
        """Serve recommendations without routing through HTTP."""
        profile = await self.get_profile()
        return cast(
            "list[Recommendation]",
            await self._require_service("recommendation_engine").serve(
                profile,
                limit=limit,
                source_platform=source_platform,
                excluded_bvids=excluded_content_ids,
            ),
        )

    async def chat(self, message: str, *, session: str = "embedded") -> str:
        """Send a direct conversational turn through the current dialogue service."""
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("message must not be empty")
        return str(
            await self._require_service("dialogue").respond(
                clean_message,
                session=session,
            )
        )

    async def publish_event(self, event: dict[str, object]) -> None:
        """Publish an integration event to the runtime event hub."""
        publish = getattr(self._require_service("event_hub"), "publish", None)
        if not callable(publish):
            raise RuntimeError("Core event hub does not support publishing")
        await publish(event)

    async def start(self, *, run_background: bool = True) -> None:
        """Start runtime-owned background work once."""
        if self._closed:
            raise RuntimeError("A closed Core cannot be restarted")
        if self._started or self.degraded:
            return
        await self.restart_background_tasks(
            run_post_reload_llm_work=run_background,
        )
        self._started = True

    async def restart_background_tasks(
        self,
        *,
        run_post_reload_llm_work: bool = True,
    ) -> None:
        """Replace runtime-owned periodic tasks after a configuration rebuild."""
        restart = getattr(self.context, "restart_background_tasks", None)
        if not callable(restart):
            return
        try:
            parameters = inspect.signature(restart).parameters
            supports_flag = "run_post_reload_llm_work" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        except (TypeError, ValueError):
            supports_flag = True
        if supports_flag:
            await restart(
                self,
                run_post_reload_llm_work=run_post_reload_llm_work,
            )
        else:
            await restart(self)
        self._started = True

    async def reload(
        self,
        config: Config,
        *,
        run_background: bool = True,
    ) -> None:
        """Atomically rebuild swappable services and resume Core-owned loops."""
        candidate_data_path = getattr(config, "data_path", None)
        if candidate_data_path is not None and self._active_data_path is not None:
            resolved_candidate = Path(candidate_data_path).expanduser().resolve()
            if resolved_candidate != self._active_data_path:
                raise RuntimeError("Changing data_dir requires constructing a new Core")
        self._configure_process_runtime(config)
        await self.context.rebuild_from_config(config)
        self._config = config
        self.context.degraded = False
        self.context.degraded_reason = ""
        self.context.degraded_issues = []
        if self._started:
            await self.restart_background_tasks(
                run_post_reload_llm_work=run_background,
            )

    async def stop(self) -> None:
        """Stop tasks and close resources owned by this Core instance."""
        if self._closed:
            return
        self._closed = True

        current_loop = asyncio.get_running_loop()
        for attr in ("refresh_task", "account_sync_task", "auto_update_task"):
            task = getattr(self.state, attr, None)
            setattr(self.state, attr, None)
            if task is None or task.done() or task.get_loop() is not current_loop:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        cancel_all = getattr(getattr(self.context, "task_registry", None), "cancel_all", None)
        if callable(cancel_all):
            with suppress(Exception):
                await cancel_all()

        settlement_queue = getattr(self.context, "dialogue_settlement_queue", None)
        shutdown = getattr(settlement_queue, "shutdown", None)
        if callable(shutdown):
            with suppress(Exception):
                await shutdown(timeout=30)

        for name in ("bangumi_client", "v2ex_client", "weibo_client"):
            close = getattr(getattr(self.context, name, None), "aclose", None)
            if callable(close):
                with suppress(Exception):
                    await close()

        if self._owns_database:
            close_database = getattr(self.context.database, "close", None)
            if callable(close_database):
                with suppress(Exception):
                    close_database()
        self._started = False

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()


__all__ = ["OpenBiliClawCore"]

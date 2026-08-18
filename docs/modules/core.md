# Embeddable Core

`openbiliclaw.core.OpenBiliClawCore` is the host-neutral entry point for the
OpenBiliClaw backend. It builds the existing `RuntimeContext`, owns the three
long-running runtime tasks, supports atomic configuration rebuilds, and closes
runtime-owned queues and clients. It does not create a FastAPI app or start a
network listener.

## Public contract

```python
from openbiliclaw import OpenBiliClawCore

async with OpenBiliClawCore.create() as core:
    profile = await core.get_profile()
    recommendations = await core.recommend(limit=5)
    reply = await core.chat("最近想看点新的", session="neko")
```

The stable host-facing surface is:

- `create()` / `from_context()` for construction and dependency injection;
- `start()` / `stop()` and `async with` for lifecycle ownership;
- `reload()` for an atomic swappable-service rebuild;
- `get_profile()`, `recommend()`, `chat()`, and `publish_event()` for the first
  direct integration operations;
- `context` as an explicit compatibility escape hatch for capabilities not yet
  promoted to the public Core API.

`create()` accepts an existing database, memory manager, or event hub. Injected
objects remain owned by the host; a database created by Core is closed by Core.
If the LLM registry cannot be built, the default `allow_degraded=True` creates a
recovery-capable Core. Set it to `False` when an embedding host prefers startup
to fail immediately. `reload()` never moves a live database: changing
`data_dir` requires stopping the old Core and constructing a new one.

## Adapter boundary

FastAPI is now an adapter: `create_app(core=core)` attaches routes, auth,
WebSocket streams, and API-specific durable schedulers to an existing Core.
The default `create_app()` path constructs that same Core internally. The CLI's
server command still starts uvicorn around the FastAPI adapter, so existing
commands and HTTP clients keep their behavior.

API-owned coordination such as HTTP auth, config-apply queuing, durable chat
reply scheduling, and image proxy fetching stays outside Core. Business runtime
construction, periodic refresh/account-sync/update tasks, dialogue settlement,
profile, recommendation, and dialogue services stay inside Core.

## NEKO integration sequence

1. Construct one Core per local OpenBiliClaw data directory.
2. Enter its async lifecycle from NEKO's process supervisor.
3. Call the direct operations above; use `core.context` only for an operation
   that has not yet received a stable façade.
4. Call `reload()` after NEKO persists a validated configuration.
5. Stop Core before NEKO closes its event loop.

NEKO does not need to enable its plugin system or MCP for this path. The browser
extension remains OpenBiliClaw's capture and browser-session layer and keeps
posting to the unchanged loopback HTTP adapter at `127.0.0.1:8420`. If NEKO is
closed, the extension retains eligible behavior events locally; once NEKO hosts
and starts Core again, the extension resumes delivery automatically.

## Compatibility guarantees

- `create()`, `start()`, `stop()`, `reload()`, `get_profile()`, `recommend()`,
  `chat()`, and `publish_event()` remain the stable public surface.
- Direct host calls do not loop back through HTTP; FastAPI wraps the same Core.
- Core owns runtime background tasks, while repeated `start()` / `stop()` and
  shutdown paths are lifecycle-safe and do not duplicate task ownership.
- Degraded construction keeps the HTTP recovery/configuration adapter available
  without starting business background work.
- A live Core never silently changes its data directory. Persisting a new
  `data_dir` requires a full stop and a newly constructed Core.
- The package introduces no NEKO-specific types or dependencies; translating
  NEKO events and response shapes remains the NEKO-side adapter's responsibility.

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
- `preview_recommendations()` plus `record_recommendation_delivery()` for the
  compatibility handoff;
- `preview_proactive_candidates(limit<=3, explicit_context_texts=...)` for a
  privacy-bounded, non-consuming proactive handoff with separate tracking,
  semantic, and policy layers;
- `record_proactive_llm_usage(phase="phase1"|"phase2", ...)` for appending
  provider-reported host usage to the same local `llm_usage` ledger under
  `embedded.proactive.phase1` / `embedded.proactive.phase2`;
- `context` as an explicit compatibility escape hatch for capabilities not yet
  promoted to the public Core API.

`create()` accepts an existing database, memory manager, event hub, a mapping
of `llm_provider_overrides`, or a host-owned `host_config_transform`. Provider
overrides implement OpenBiliClaw's existing `LLMProvider` protocol. The
transform is applied both during construction and before every `reload()`
rebuild, so a persisted standalone route cannot silently replace the host route
after a settings save. Together they let an embedding host resolve its current
model route and credentials at call time without writing those credentials into
OpenBiliClaw configuration. Injected
objects remain owned by the host; a database created by Core is closed by Core.
`surface_copy_mode` defaults to `"background"` for standalone/API compatibility.
An embedded host may select `"lazy"`: expression-copy coordination is not
created or restarted, while `preview_proactive_candidates()` reads the separate
semantic-ready pool. The runtime controller also carries this policy explicitly:
periodic pool maintenance, candidate admission, and refresh completion may still
classify semantic candidates, but cannot fall back to background expression-copy
generation. An explicit `recommend()` call still generates and caches copy before
recording delivery. Hot reload preserves this host-owned mode.
`maintenance_policy` is another reload-stable host control. A lazy Core now
installs `MaintenancePolicy.embedded_proactive()` when the host omits a policy,
and rejects an explicitly unbounded lazy policy. The preset keeps active
capacity 30, soft target 10, refill only below 4 ready candidates, one worker
and at most 10 candidates per batch. It enforces a persistent 100,000-token
daily OBC background input ceiling split 50k/20k/30k across
Discovery/Recommendation/Soul plus a 20,000-token background output ceiling.
The output ceiling was calibrated from the 2026-08-18 local background high
water mark (13,840 completion tokens) and must be revisited after a provider or
model swap. Capacity is never treated as a startup fill target. Proactive
preview checks this bounded lazy contract again and fails before reading a
candidate if an injected context bypassed `create()`.
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

1. Construct one Core per local OpenBiliClaw data directory and inject the
   NEKO-managed provider under the configured OpenBiliClaw instance ID.
   Select `surface_copy_mode="lazy"`. Core installs the canonical bounded
   proactive policy automatically; a host may inject a stricter fully bounded
   policy.
2. Enter its async lifecycle from NEKO's process supervisor.
3. Read `preview_proactive_candidates()` before NEKO Phase 1. Preview only reads
   semantic-ready canonical pool rows: it does not refresh sources, call an LLM,
   write presentation history, or consume a candidate. The optional last three
   user messages are used in memory only for deterministic sensitive-topic
   matching and are not persisted or sent to a model.
   Candidates require current `content-eval-v8` quality, relevance, and independent
   summary-quality components; a non-empty but weak summary still fails closed.
4. Let NEKO's existing Phase 1 choose a candidate and Phase 2 generate the only
   user-visible character line. Do not call `core.chat()` from NEKO's normal or
   proactive conversation path. After each provider response, pass its actual
   input/output/cache counters to `record_proactive_llm_usage()`; these rows are
   visible through the existing `cost --by caller` report but do not consume the
   OBC background allowance.
5. Only after successful delivery, pass the selected object to
   `record_recommendation_delivery()`. `[PASS]`, interruption, rejection, and
   delivery failure must not record it as shown.
6. Call `reload()` after OpenBiliClaw configuration changes; the injected
   provider mapping and host configuration transform remain installed.
7. Stop Core before NEKO closes its event loop.

This is single ownership of model configuration and final speech, not a promise
of one model request for the whole system. OpenBiliClaw may still use the
NEKO-managed provider for background profile analysis, candidate evaluation,
and recommendation copy. NEKO alone turns the selected structured candidate
into user-visible character dialogue.

NEKO does not need to enable its plugin system or MCP for this path. The browser
extension remains OpenBiliClaw's capture and browser-session layer and keeps
posting to the unchanged loopback HTTP adapter at `127.0.0.1:8420`. If NEKO is
closed, the extension retains eligible behavior events locally; once NEKO hosts
and starts Core again, the extension resumes delivery automatically.

## Compatibility guarantees

- `create()`, `start()`, `stop()`, `reload()`, `get_profile()`, `recommend()`,
  `preview_recommendations()`, `preview_proactive_candidates()`,
  `record_proactive_llm_usage()`, `record_recommendation_delivery()`, `chat()`,
  and `publish_event()` remain the stable public surface.
- Direct host calls do not loop back through HTTP; FastAPI wraps the same Core.
- Core owns runtime background tasks, while repeated `start()` / `stop()` and
  shutdown paths are lifecycle-safe and do not duplicate task ownership.
- Degraded construction keeps the HTTP recovery/configuration adapter available
  without starting business background work.
- A live Core never silently changes its data directory. Persisting a new
  `data_dir` requires a full stop and a newly constructed Core.
- The package introduces no NEKO-specific types or dependencies; translating
  NEKO events and response shapes remains the NEKO-side adapter's responsibility.

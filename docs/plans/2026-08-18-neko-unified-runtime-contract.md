# NEKO unified runtime capability contract

## Scope

- Integration level: `capability-increment`
- Baseline: `codex/embeddable-core@78986d00f120615afe606f583365aaf0191c53a4`
- Delivery branch: `codex/neko-unified-runtime`
- Host contract: a first-party Python host such as NEKO embeds `OpenBiliClawCore`; the browser extension continues to use the loopback HTTP/WebSocket adapter.
- Backend endpoint: `http://127.0.0.1:8420`
- External platform mutations: none

## Required capabilities

| Capability | Requirement |
| --- | --- |
| Durable behavior ingress | Persist live, inflight, and pre-init parked behavior events in `chrome.storage.local` across MV3 recycling and browser restart. |
| Capacity | Keep at most 1,000 total live/inflight/parked events and evict the oldest eligible event when capacity is exhausted. |
| Batch delivery | Deliver at most 100 events per request and continue with later batches after each successful acknowledgement. |
| Retention | Drop persisted events older than 30 days; preserve legacy rows without a valid timestamp. |
| Identity | Assign one stable `event_id` before persistence and preserve it across every retry/storage transition. |
| Failure semantics | A non-2xx response or transport failure retains the durable inflight owner. A persistence failure returns a negative acknowledgement to the sender. |
| Pre-init semantics | A successful `not_initialized` response moves behavior events to parked storage and drains them after initialization. |
| Popup status | The simplified popup reports backend state, the combined durable queue count, and the last successful sync time without restoring the removed profile/editor/chat surfaces. |
| Embedded Core | Preserve the public `OpenBiliClawCore` API and prove direct host operation, FastAPI wrapping, degraded wrapping, idempotent stop, and fixed live data root. |
| Build targets | Typecheck/test/build/asset verification for Chrome and Firefox. Safari is release-only and excluded here. |

## Internal storage contract

| Key | Value |
| --- | --- |
| `obc_event_buffer` | Live `BehaviorEvent[]` |
| `obc_event_inflight` | Currently claimed `BehaviorEvent[]` |
| `obc_parked_events` | `{ parkedAt, event }[]` awaiting backend initialization |
| `obc_last_sync_at` | ISO-8601 timestamp written after a backend batch acknowledgement |

Priority is `inflight -> parked -> live`. Storage keys are internal extension state and do not change the backend HTTP API.

## Intentional exclusions

- New platform slug, canonical registry, auth, credential, bootstrap, incremental, discover, recommendation card, native-save, image, mobile, or setup changes: N/A because this capability is platform-agnostic behavior ingress.
- Cached profile UI and the pre-simplification popup: N/A by product decision; `popup-shell` contract tests keep removed surfaces absent.
- NEKO repository changes: N/A for this repository-side delivery.
- Version bump, tag, release, marketplace upload, PR, and merge to `main`: N/A by explicit user scope.
- State-changing real-site E2E: N/A; no upstream like/favorite/follow/save action is needed to prove local buffering.

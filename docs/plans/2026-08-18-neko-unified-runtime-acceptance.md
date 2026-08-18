# NEKO unified runtime acceptance ledger

## Provenance

- Integration level: `capability-increment`
- Contract: `docs/plans/2026-08-18-neko-unified-runtime-contract.md`
- Worktree: `C:/Users/NEKO-PC-03/Documents/GitHub/OpenBiliClaw/.worktrees/neko-unified-runtime`
- Baseline: `78986d00f120615afe606f583365aaf0191c53a4`
- Primary transport: browser extension to loopback FastAPI adapter
- Embedded transport: direct `OpenBiliClawCore` Python calls
- Existing user changes preserved: yes; root `.pnpm-store/` is outside this worktree and untouched

## Gate ledger

| Gate | Applicability | Status | Evidence / remaining work |
| --- | --- | --- | --- |
| Scope/worktree provenance | required | PASS | Dedicated worktree and branch created from the frozen baseline. |
| Frozen capability contract | required | PASS | Contract above records queue, popup, Core, build, and exclusion boundaries. |
| Historical precedent + repair review | required | PASS | Reviewed `d4a8441a` simplified shell, `ad8887f8` offline repair, and `78986d00` Core extraction. |
| Canonical registry/auth/discover/bootstrap | N/A | PASS | No source capability changes; exclusion is locked by unchanged platform rosters and the full suite. |
| Browser behavior ingress / MV3 recovery | required | PASS | 31 focused Node tests cover durable ACK/NACK, stable IDs, 1000 total capacity, 100-event claims, 30-day pruning, inflight restart, parked recovery, successive batches, and last-sync writes. |
| Extension popup surface | required | PASS | 9 popup/shell tests cover the four states, three-queue dedupe/count, last-sync display, relevant storage changes, and removed-surface boundary. Rendered at 390 and 1024 CSS px with zero horizontal overflow; independent fresh-eyes review found no blocker/major. |
| Embedded Core contract | required | PASS | `tests/test_core.py`: 7 passed under Python 3.11.9, including host-direct calls, FastAPI wrapping, degraded wrapping, idempotent stop, background ownership, and data-root restart requirement. |
| Chrome + Firefox tests/build/assets | required | PASS | `pnpm typecheck`, Chrome build/assets, and Firefox Windows-equivalent build/assets passed. Service-worker SHA-256: Chrome `F9D47D14417D0C50177B21CAF426106C75095DD38D98430BDEBC00F89C024CE1`; Firefox `495B527CC181F5A69049B7699D01B07D08153409FB8F075959F5BB8F9A504C8B`. The repository's POSIX `TARGET=firefox` wrapper is not Windows-compatible, so the same clean/typecheck/build bundle ran with PowerShell `$env:TARGET='firefox'`. |
| Safe local E2E | required | NOT_RUN | Core/FastAPI and extension storage semantics were exercised separately with real production classes, but the newly built unpacked extension was not installed into Chrome/Firefox against a live isolated Core in this run. No account mutation was attempted. |
| State-changing upstream E2E | N/A | PASS | No upstream mutation is required or authorized by this capability. |
| Documentation / release-readiness | required | PASS | Updated extension/Core modules, changelog, architecture, spec, CN/EN README, privacy, frozen contract, and this ledger. No version/tag/release changes by scope. |
| Commit and fork push | required | PASS | Four scoped commits, including this documentation record, are committed and pushed to the Himifox fork branch `origin/codex/neko-unified-runtime`. |
| Version/tag/PR/main/marketplace | N/A | PASS | Explicitly excluded by user scope. |

## Verification record

- Import proof: `C:/Users/NEKO-PC-03/Documents/GitHub/OpenBiliClaw/.worktrees/neko-unified-runtime/src/openbiliclaw/__init__.py` under Python 3.11.9.
- Focused extension result: 31 passed; focused popup subset: 9 passed.
- Full extension result: 1025 passed / 2 Windows-baseline failures. One test launches bare `npm` with `spawnSync` although the bundled runtime exposes pnpm only; the other regex expects LF while the checked-out workflow is CRLF. Neither touches this change. Chrome/Firefox typecheck/build/asset gates passed independently.
- Full Python attempt: pytest reached 56% before its Windows failure formatter aborted with `NotImplementedError: cannot instantiate 'PosixPath' on your system`; at that point it reported 4,834 passed, 36 failed, and 13 skipped. This is not recorded as a complete or green full-suite run. The scoped Core/docs contract selection completed separately with 30 passed, including all 7 focused Core tests.
- Ruff: PASS. MyPy on Windows reports 15 existing POSIX typing errors (`fcntl` locks, `os.getuid/fchmod/killpg/getpgid`) in five untouched files.
- `source_contract_metrics.py --check`: 5/6 both here and at the untouched `embeddable-core` baseline; the existing frontend-template metric is below its historical target and is unrelated to this platform-neutral increment.
- Commits pushed so far: `14e4b32a`, `21bcf04b`, `d5df0de9`.
- Final verdict remains `incremental only` until the installed-extension/live-Core E2E row is run; implementation and automated/build gates are otherwise complete.

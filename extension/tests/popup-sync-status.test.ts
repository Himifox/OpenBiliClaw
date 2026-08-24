import assert from "node:assert/strict";
import test from "node:test";

import {
  EVENT_BUFFER_KEY,
  INFLIGHT_KEY,
  LAST_SYNC_KEY,
  PARKED_KEY,
  countQueuedEvents,
  formatLastSyncAt,
  loadSyncSnapshot,
  presentSyncStatus,
  subscribeSyncStorage,
} from "../popup/popup-sync-status.js";

test("queue count deduplicates identities across live, inflight, and parked", () => {
  assert.equal(countQueuedEvents({
    [EVENT_BUFFER_KEY]: [{ event_id: "a" }, { event_id: "b" }],
    [INFLIGHT_KEY]: [{ event_id: "a" }],
    [PARKED_KEY]: [{ parkedAt: 1, event: { event_id: "c" } }],
  }), 3);
});

test("sync presentation covers online, pending, cached, and waiting states", () => {
  const now = Date.parse("2026-08-18T08:10:00.000Z");
  const lastSyncAt = "2026-08-18T08:00:00.000Z";
  assert.equal(presentSyncStatus({ online: true, queueCount: 0, lastSyncAt, now }).label, "已同步");
  assert.equal(presentSyncStatus({ online: true, queueCount: 7, lastSyncAt, now }).label, "正在补传 · 7 条");
  assert.equal(presentSyncStatus({ online: false, queueCount: 7, lastSyncAt, now }).label, "已离线缓存 · 7 条");
  assert.equal(presentSyncStatus({ online: false, queueCount: 0, lastSyncAt: "", now }).label, "等待 NEKO 启动");
  assert.equal(formatLastSyncAt(lastSyncAt, now), "10 分钟前同步");
  assert.equal(formatLastSyncAt("", now), "尚未同步");
});

test("loadSyncSnapshot reads all durable queues and last sync time", async () => {
  const stored = {
    [EVENT_BUFFER_KEY]: [{ event_id: "live" }],
    [INFLIGHT_KEY]: [{ event_id: "flight" }],
    [PARKED_KEY]: [{ parkedAt: 1, event: { event_id: "parked" } }],
    [LAST_SYNC_KEY]: "2026-08-18T08:00:00.000Z",
  };
  const storage = {
    get(_keys: string[], callback: (items: typeof stored) => void) {
      callback(stored);
    },
  };
  assert.deepEqual(await loadSyncSnapshot(storage), {
    queueCount: 3,
    lastSyncAt: "2026-08-18T08:00:00.000Z",
  });
});

test("storage subscription reacts only to relevant local changes", () => {
  let registered: ((changes: Record<string, unknown>, areaName: string) => void) | undefined;
  let calls = 0;
  const events = {
    addListener(listener: typeof registered) { registered = listener; },
    removeListener() {},
  };
  subscribeSyncStorage(() => { calls += 1; }, events);
  registered?.({ unrelated: {} }, "local");
  registered?.({ [EVENT_BUFFER_KEY]: {} }, "sync");
  registered?.({ [LAST_SYNC_KEY]: {} }, "local");
  assert.equal(calls, 1);
});

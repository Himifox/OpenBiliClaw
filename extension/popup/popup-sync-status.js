export const EVENT_BUFFER_KEY = "obc_event_buffer";
export const INFLIGHT_KEY = "obc_event_inflight";
export const PARKED_KEY = "obc_parked_events";
export const LAST_SYNC_KEY = "obc_last_sync_at";

export const SYNC_STORAGE_KEYS = new Set([
  EVENT_BUFFER_KEY,
  INFLIGHT_KEY,
  PARKED_KEY,
  LAST_SYNC_KEY,
]);

function rows(value) {
  return Array.isArray(value) ? value : [];
}

function eventFromRow(row) {
  return row?.event && typeof row.event === "object" ? row.event : row;
}

/** Count distinct durable event identities across live, inflight, and parked storage. */
export function countQueuedEvents(snapshot = {}) {
  const seen = new Set();
  let anonymous = 0;
  for (const key of [EVENT_BUFFER_KEY, INFLIGHT_KEY, PARKED_KEY]) {
    for (const row of rows(snapshot[key])) {
      const event = eventFromRow(row);
      const eventId = typeof event?.event_id === "string" ? event.event_id.trim() : "";
      if (eventId) seen.add(eventId);
      else anonymous += 1;
    }
  }
  return seen.size + anonymous;
}

export function formatLastSyncAt(value, now = Date.now()) {
  const timestamp = Date.parse(String(value || ""));
  if (!Number.isFinite(timestamp)) return "尚未同步";
  const elapsed = Math.max(0, now - timestamp);
  if (elapsed < 60_000) return "刚刚同步";
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 60) return `${minutes} 分钟前同步`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前同步`;
  const days = Math.floor(hours / 24);
  return `${days} 天前同步`;
}

export function presentSyncStatus({ online, queueCount, lastSyncAt, now = Date.now() }) {
  let label = "等待 NEKO 启动";
  let tone = "offline";
  if (online && queueCount > 0) {
    label = `正在补传 · ${queueCount} 条`;
    tone = "pending";
  } else if (online) {
    label = "已同步";
    tone = "synced";
  } else if (queueCount > 0) {
    label = `已离线缓存 · ${queueCount} 条`;
    tone = "cached";
  }
  return {
    label,
    detail: formatLastSyncAt(lastSyncAt, now),
    tone,
  };
}

function storageGet(storage, keys) {
  if (!storage?.get) return Promise.resolve({});
  return new Promise((resolve) => {
    try {
      storage.get(keys, (items) => resolve(items || {}));
    } catch {
      resolve({});
    }
  });
}

export async function loadSyncSnapshot(storage = globalThis.chrome?.storage?.local) {
  const snapshot = await storageGet(storage, [...SYNC_STORAGE_KEYS]);
  return {
    queueCount: countQueuedEvents(snapshot),
    lastSyncAt: snapshot[LAST_SYNC_KEY] || "",
  };
}

export function subscribeSyncStorage(
  listener,
  storageEvents = globalThis.chrome?.storage?.onChanged,
) {
  if (!storageEvents?.addListener) return () => {};
  const handleChange = (changes, areaName) => {
    if (areaName !== "local") return;
    if (!Object.keys(changes || {}).some((key) => SYNC_STORAGE_KEYS.has(key))) return;
    listener();
  };
  storageEvents.addListener(handleChange);
  return () => storageEvents.removeListener?.(handleChange);
}

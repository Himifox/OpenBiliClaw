import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  PROFILE_SNAPSHOT_KEY,
  PROFILE_SNAPSHOT_TTL_MS,
  clearCachedProfileSnapshot,
  createProfileSnapshot,
  readCachedProfileSnapshot,
  validateProfileSnapshot,
  writeCachedProfileSnapshot,
} from "../popup/popup-profile-cache.js";

function installStorageStub(): { store: Map<string, unknown>; restore: () => void } {
  const store = new Map<string, unknown>();
  const original = (globalThis as { chrome?: unknown }).chrome;
  (globalThis as { chrome?: unknown }).chrome = {
    runtime: {},
    storage: {
      local: {
        get(key: string, callback: (items: Record<string, unknown>) => void) {
          callback({ [key]: store.get(key) });
        },
        set(items: Record<string, unknown>, callback?: () => void) {
          for (const [key, value] of Object.entries(items)) store.set(key, value);
          callback?.();
        },
        remove(key: string, callback?: () => void) {
          store.delete(key);
          callback?.();
        },
      },
    },
  };
  return {
    store,
    restore() {
      (globalThis as { chrome?: unknown }).chrome = original;
    },
  };
}

test("profile snapshot accepts only an initialized backend profile", () => {
  assert.equal(createProfileSnapshot({ initialized: false }, "http://127.0.0.1:8420"), null);
  const snapshot = createProfileSnapshot(
    { initialized: true, core_traits: ["curious"] },
    "http://127.0.0.1:8420",
    123,
  );
  assert.deepEqual(snapshot, {
    schema_version: 1,
    cached_at: 123,
    backend_origin: "http://127.0.0.1:8420",
    profile: { initialized: true, core_traits: ["curious"] },
  });
});

test("profile snapshot expires after 30 days and rejects schema drift", () => {
  const now = 1_000_000_000_000;
  const valid = createProfileSnapshot({ initialized: true }, "http://127.0.0.1:8420", now);
  assert.ok(valid);
  assert.equal(
    validateProfileSnapshot(valid, "http://127.0.0.1:8420", now + PROFILE_SNAPSHOT_TTL_MS),
    valid,
  );
  assert.equal(
    validateProfileSnapshot(valid, "http://127.0.0.1:8420", now + PROFILE_SNAPSHOT_TTL_MS + 1),
    null,
  );
  assert.equal(
    validateProfileSnapshot({ ...valid, schema_version: 2 }, "http://127.0.0.1:8420", now),
    null,
  );
  assert.equal(validateProfileSnapshot(valid, "http://127.0.0.1:9999", now), null);
});

test("successful profiles round-trip through storage and stale snapshots are removed", async () => {
  const stub = installStorageStub();
  try {
    const now = Date.now();
    assert.equal(
      await writeCachedProfileSnapshot(
        { initialized: true, values: ["clarity"] },
        "http://127.0.0.1:8420",
        now,
      ),
      true,
    );
    const restored = await readCachedProfileSnapshot("http://127.0.0.1:8420", now + 1);
    assert.deepEqual(restored?.profile, { initialized: true, values: ["clarity"] });

    await readCachedProfileSnapshot(
      "http://127.0.0.1:8420",
      now + PROFILE_SNAPSHOT_TTL_MS + 1,
    );
    assert.equal(stub.store.has(PROFILE_SNAPSHOT_KEY), false);

    await writeCachedProfileSnapshot(
      { initialized: true },
      "http://127.0.0.1:8420",
      now,
    );
    await clearCachedProfileSnapshot();
    assert.equal(stub.store.has(PROFILE_SNAPSHOT_KEY), false);
  } finally {
    stub.restore();
  }
});

test("popup renders a cached profile as read-only with a visible offline notice", () => {
  const popupJs = readFileSync(resolve("popup/popup.js"), "utf8");
  const popupHtml = readFileSync(resolve("popup/popup.html"), "utf8");

  assert.match(popupJs, /readCachedProfileSnapshot/);
  assert.match(popupJs, /writeCachedProfileSnapshot/);
  assert.match(popupJs, /syncProfileEditChrome\(!state\.profileFromCache\)/);
  assert.match(popupHtml, /id="profileCacheNotice"/);
});

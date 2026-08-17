export const PROFILE_SNAPSHOT_KEY = "obc_profile_snapshot_v1";
export const PROFILE_SNAPSHOT_SCHEMA_VERSION = 1;
export const PROFILE_SNAPSHOT_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function storageLocal() {
  return globalThis.chrome?.storage?.local ?? null;
}

function lastStorageError() {
  return globalThis.chrome?.runtime?.lastError;
}

function storageGet(key) {
  const storage = storageLocal();
  if (!storage?.get) return Promise.resolve(undefined);
  return new Promise((resolve, reject) => {
    storage.get(key, (items) => {
      const error = lastStorageError();
      if (error) {
        reject(new Error(error.message || "storage.get failed"));
        return;
      }
      resolve(items?.[key]);
    });
  });
}

function storageSet(items) {
  const storage = storageLocal();
  if (!storage?.set) return Promise.resolve();
  return new Promise((resolve, reject) => {
    storage.set(items, () => {
      const error = lastStorageError();
      if (error) {
        reject(new Error(error.message || "storage.set failed"));
        return;
      }
      resolve();
    });
  });
}

function storageRemove(key) {
  const storage = storageLocal();
  if (!storage?.remove) return Promise.resolve();
  return new Promise((resolve, reject) => {
    storage.remove(key, () => {
      const error = lastStorageError();
      if (error) {
        reject(new Error(error.message || "storage.remove failed"));
        return;
      }
      resolve();
    });
  });
}

export function createProfileSnapshot(profile, backendOrigin, now = Date.now()) {
  if (!profile || typeof profile !== "object" || profile.initialized !== true) {
    return null;
  }
  if (typeof backendOrigin !== "string" || backendOrigin.trim() === "") return null;
  return {
    schema_version: PROFILE_SNAPSHOT_SCHEMA_VERSION,
    cached_at: now,
    backend_origin: backendOrigin,
    profile,
  };
}

export function validateProfileSnapshot(snapshot, backendOrigin, now = Date.now()) {
  if (!snapshot || typeof snapshot !== "object") return null;
  if (snapshot.schema_version !== PROFILE_SNAPSHOT_SCHEMA_VERSION) return null;
  if (snapshot.backend_origin !== backendOrigin) return null;
  if (!Number.isFinite(snapshot.cached_at) || snapshot.cached_at <= 0) return null;
  if (now - snapshot.cached_at > PROFILE_SNAPSHOT_TTL_MS) return null;
  if (!snapshot.profile || snapshot.profile.initialized !== true) return null;
  return snapshot;
}

export async function writeCachedProfileSnapshot(profile, backendOrigin, now = Date.now()) {
  const snapshot = createProfileSnapshot(profile, backendOrigin, now);
  if (!snapshot) return false;
  await storageSet({ [PROFILE_SNAPSHOT_KEY]: snapshot });
  return true;
}

export async function readCachedProfileSnapshot(backendOrigin, now = Date.now()) {
  const stored = await storageGet(PROFILE_SNAPSHOT_KEY);
  const snapshot = validateProfileSnapshot(stored, backendOrigin, now);
  if (snapshot) return snapshot;
  if (stored !== undefined) await storageRemove(PROFILE_SNAPSHOT_KEY);
  return null;
}

export async function clearCachedProfileSnapshot() {
  await storageRemove(PROFILE_SNAPSHOT_KEY);
}

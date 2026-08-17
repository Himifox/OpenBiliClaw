import { getBackendBaseUrl, getBackendOrigin } from "./popup-backend-config.js";
import {
  ensurePopupSession,
  popupAuthenticatedFetch,
} from "./popup-device-auth.js";

export const POPUP_REQUEST_TIMEOUT_MS = 12_000;
const PING_TIMEOUT_MS = 3_000;

function timeoutSignal(timeoutMs = POPUP_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  return {
    signal: controller.signal,
    clear: () => globalThis.clearTimeout(timer),
  };
}

export async function requestJson(path, options = {}) {
  const { timeoutMs = POPUP_REQUEST_TIMEOUT_MS, ...fetchOptions } = options;
  const timeout = timeoutSignal(timeoutMs);
  try {
    const fetchImpl = globalThis.fetch.bind(globalThis);
    const baseUrl = await getBackendBaseUrl();
    const sessionToken = await ensurePopupSession({ fetchImpl, signal: timeout.signal });
    const response = await popupAuthenticatedFetch(
      `${baseUrl}${path}`,
      { ...fetchOptions, signal: timeout.signal },
      fetchImpl,
      { sessionToken, signal: timeout.signal },
    );
    if (!response.ok) {
      const error = new Error(`${path} request failed: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    timeout.clear();
  }
}

export async function checkBackendStatus() {
  const timeout = timeoutSignal(PING_TIMEOUT_MS);
  try {
    const baseUrl = await getBackendBaseUrl();
    const response = await fetch(`${baseUrl}/ping`, {
      method: "GET",
      signal: timeout.signal,
    });
    if (response.status !== 404) return response.ok;
  } catch {
    return false;
  } finally {
    timeout.clear();
  }

  try {
    return Boolean(await fetchHealth());
  } catch {
    return false;
  }
}

export async function fetchHealth() {
  return requestJson("/health", { method: "GET" });
}

export async function fetchSourcesStatus() {
  return requestJson("/sources/status", { method: "GET" });
}

export async function getMainAppUrl() {
  return `${await getBackendOrigin()}/web`;
}

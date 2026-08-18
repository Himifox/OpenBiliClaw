import {
  getBackendBaseUrl,
  getBackendEndpointConfig,
  updateBackendEndpoint,
} from "./popup-backend-config.js";
import { clearPopupSession } from "./popup-device-auth.js";
import { initExtLogin } from "./popup-ext-login.js";
import {
  checkBackendStatus,
  fetchHealth,
  fetchSourcesStatus,
  getMainAppUrl,
} from "./popup-api.js";
import {
  SOURCE_LABELS,
  SOURCE_ORDER,
  sourceFromUrl,
  sourcePresentation,
} from "./popup-state.js";
import {
  loadSyncSnapshot,
  presentSyncStatus,
  subscribeSyncStorage,
} from "./popup-sync-status.js";

const elements = {
  backendBadge: document.getElementById("backendBadge"),
  backendBadgeText: document.getElementById("backendBadgeText"),
  connectionCard: document.getElementById("connectionCard"),
  connectionTitle: document.getElementById("connectionTitle"),
  connectionDetail: document.getElementById("connectionDetail"),
  syncHealth: document.getElementById("syncHealth"),
  syncStatusText: document.getElementById("syncStatusText"),
  lastSyncText: document.getElementById("lastSyncText"),
  openAppButton: document.getElementById("openAppButton"),
  refreshButton: document.getElementById("refreshButton"),
  currentSourceTitle: document.getElementById("currentSourceTitle"),
  currentSourceState: document.getElementById("currentSourceState"),
  currentSourceDetail: document.getElementById("currentSourceDetail"),
  sourceSummary: document.getElementById("sourceSummary"),
  sourceCount: document.getElementById("sourceCount"),
  sourceList: document.getElementById("sourceList"),
  sourcesDetails: document.getElementById("sourcesDetails"),
  settingsDetails: document.getElementById("settingsDetails"),
  syncButton: document.getElementById("syncButton"),
  actionStatus: document.getElementById("actionStatus"),
  endpointForm: document.getElementById("endpointForm"),
  backendScheme: document.getElementById("backendScheme"),
  backendHost: document.getElementById("backendHost"),
  backendPort: document.getElementById("backendPort"),
  saveEndpointButton: document.getElementById("saveEndpointButton"),
  endpointStatus: document.getElementById("endpointStatus"),
  extensionVersion: document.getElementById("extensionVersion"),
};

const state = {
  online: false,
  currentSource: null,
  statuses: null,
  refreshInFlight: false,
  queueCount: 0,
  lastSyncAt: "",
};

function renderSyncStatus() {
  const presentation = presentSyncStatus({
    online: state.online,
    queueCount: state.queueCount,
    lastSyncAt: state.lastSyncAt,
  });
  elements.syncHealth.className = `sync-health is-${presentation.tone}`;
  elements.syncStatusText.textContent = presentation.label;
  elements.lastSyncText.textContent = presentation.detail;
}

async function refreshSyncStatus() {
  const snapshot = await loadSyncSnapshot();
  state.queueCount = snapshot.queueCount;
  state.lastSyncAt = snapshot.lastSyncAt;
  renderSyncStatus();
}

function setStatusText(element, message, tone = "") {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", tone === "error");
  element.classList.toggle("is-success", tone === "success");
}

function renderBackendStatus(mode, health = null) {
  state.online = mode === "online";
  renderSyncStatus();
  elements.backendBadge.className = `status-badge is-${mode}`;
  elements.connectionCard.className = `connection-card is-${mode}`;
  elements.openAppButton.disabled = !state.online;
  elements.syncButton.disabled = !state.online;

  if (mode === "online") {
    elements.backendBadgeText.textContent = "已连接";
    elements.connectionTitle.textContent = "浏览器桥已连接";
    elements.connectionDetail.textContent = health?.profile_ready === false
      ? "后端已经在线，画像尚未准备好；请在主应用完成初始化。"
      : "登录态、浏览行为和来源任务会通过这个连接交给本机服务。";
    return;
  }
  if (mode === "checking") {
    elements.backendBadgeText.textContent = "连接中";
    elements.connectionTitle.textContent = "正在查找本机服务";
    elements.connectionDetail.textContent = "确认 NEKO 中的 OpenBiliClaw Core 是否已经启动。";
    return;
  }
  elements.backendBadgeText.textContent = "未连接";
  elements.connectionTitle.textContent = "本机服务还没启动";
  elements.connectionDetail.textContent = "先启动 OpenBiliClaw，再回来重新检查；已采集事件会在浏览器里暂存。";
}

function makeSourceState(presentation) {
  const status = document.createElement("span");
  status.className = `source-state is-${presentation.tone}`;
  status.textContent = presentation.label;
  return status;
}

function renderSources(statuses) {
  state.statuses = statuses;
  elements.sourceList.replaceChildren();
  const enabledSources = SOURCE_ORDER.filter(
    (slug) => statuses?.[slug] && statuses[slug].enabled !== false,
  );
  const readyCount = enabledSources.filter((slug) => sourcePresentation(statuses?.[slug]).ready).length;

  elements.sourceCount.textContent = `${enabledSources.length} 个已启用 · 共 ${SOURCE_ORDER.length} 个`;
  elements.sourceSummary.textContent = enabledSources.length > 0
    ? `${readyCount} 个已启用来源可以使用；登录态变化会自动同步。`
    : "尚未启用来源，请在主应用中选择内容来源。";

  for (const slug of SOURCE_ORDER) {
    const item = statuses?.[slug];
    if (!item) continue;
    const presentation = sourcePresentation(item);
    const row = document.createElement("div");
    row.className = "source-row";

    const copy = document.createElement("div");
    copy.className = "source-row-copy";
    const name = document.createElement("span");
    name.className = "source-row-name";
    name.textContent = SOURCE_LABELS[slug];
    const detail = document.createElement("span");
    detail.className = "source-row-detail";
    detail.textContent = item.detail || (item.enabled === false ? "未在主应用中启用" : "等待后端状态");
    copy.append(name, detail);
    row.append(copy, makeSourceState(presentation));
    elements.sourceList.append(row);
  }
  renderCurrentSource();
}

function renderCurrentSource() {
  const slug = state.currentSource;
  elements.currentSourceState.className = "source-state is-neutral";
  if (!slug) {
    elements.currentSourceTitle.textContent = "当前网站暂不支持";
    elements.currentSourceState.textContent = "待机";
    elements.currentSourceDetail.textContent = "打开支持的网站后，插件会自动识别并采集必要信号。";
    return;
  }

  elements.currentSourceTitle.textContent = SOURCE_LABELS[slug];
  if (!state.online || !state.statuses?.[slug]) {
    elements.currentSourceState.textContent = state.online ? "读取中" : "后端离线";
    elements.currentSourceDetail.textContent = state.online
      ? "正在读取这个来源的连接状态。"
      : "页面已识别；启动后端后才能确认登录态是否同步。";
    return;
  }

  const item = state.statuses[slug];
  const presentation = sourcePresentation(item);
  elements.currentSourceState.className = `source-state is-${presentation.tone}`;
  elements.currentSourceState.textContent = presentation.label;
  elements.currentSourceDetail.textContent = item.detail || (
    presentation.ready ? "当前来源已经可以使用。" : "请在当前网站登录后再次同步。"
  );
}

function queryActiveTab() {
  if (!globalThis.chrome?.tabs?.query) return Promise.resolve([]);
  return new Promise((resolve) => {
    try {
      const maybePromise = chrome.tabs.query({ active: true, currentWindow: true }, resolve);
      if (maybePromise?.then) maybePromise.then(resolve).catch(() => resolve([]));
    } catch {
      resolve([]);
    }
  });
}

async function detectCurrentSource() {
  const [tab] = await queryActiveTab();
  state.currentSource = sourceFromUrl(tab?.url || "");
  renderCurrentSource();
}

export async function refreshConnectorStatus() {
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  elements.refreshButton.disabled = true;
  renderBackendStatus("checking");
  try {
    const online = await checkBackendStatus();
    if (!online) {
      state.statuses = null;
      renderBackendStatus("offline");
      renderCurrentSource();
      elements.sourceSummary.textContent = "连接后读取来源状态。";
      elements.sourceCount.textContent = `0 个已启用 · 共 ${SOURCE_ORDER.length} 个`;
      elements.sourceList.replaceChildren();
      return;
    }
    const [health, statuses] = await Promise.all([
      fetchHealth().catch(() => null),
      fetchSourcesStatus(),
    ]);
    renderBackendStatus("online", health);
    renderSources(statuses);
  } catch {
    state.statuses = null;
    renderBackendStatus("offline");
    renderCurrentSource();
  } finally {
    state.refreshInFlight = false;
    elements.refreshButton.disabled = false;
  }
}

function sendRuntimeMessage(message) {
  if (!globalThis.chrome?.runtime?.sendMessage) return Promise.reject(new Error("runtime_unavailable"));
  return new Promise((resolve, reject) => {
    try {
      const maybePromise = chrome.runtime.sendMessage(message, (response) => {
        const error = chrome.runtime.lastError;
        if (error) reject(new Error(error.message));
        else resolve(response);
      });
      if (maybePromise?.then) maybePromise.then(resolve).catch(reject);
    } catch (error) {
      reject(error);
    }
  });
}

async function syncIdentities() {
  elements.syncButton.disabled = true;
  setStatusText(elements.actionStatus, "正在请求浏览器重新同步登录态…");
  try {
    const response = await sendRuntimeMessage({ action: "OBC_SYNC_IDENTITIES" });
    if (!response?.ok) throw new Error("sync_rejected");
    setStatusText(elements.actionStatus, "同步请求已发送，状态会自动刷新。", "success");
    globalThis.setTimeout(() => void refreshConnectorStatus(), 1800);
  } catch {
    setStatusText(elements.actionStatus, "同步请求没有送达，请重新加载插件后再试。", "error");
  } finally {
    elements.syncButton.disabled = !state.online;
  }
}

async function openMainApp() {
  const url = await getMainAppUrl();
  if (globalThis.chrome?.tabs?.create) {
    await chrome.tabs.create({ url });
    return;
  }
  globalThis.open?.(url, "_blank", "noopener");
}

async function loadEndpointForm() {
  const endpoint = await getBackendEndpointConfig();
  elements.backendScheme.value = endpoint.scheme;
  elements.backendHost.value = endpoint.host;
  elements.backendPort.value = String(endpoint.port);
}

async function saveEndpoint(event) {
  event.preventDefault();
  elements.saveEndpointButton.disabled = true;
  setStatusText(elements.endpointStatus, "正在保存并检查…");
  try {
    await updateBackendEndpoint(
      elements.backendScheme.value,
      elements.backendHost.value,
      elements.backendPort.value,
    );
    await clearPopupSession();
    setStatusText(elements.endpointStatus, "连接地址已保存。", "success");
    await refreshConnectorStatus();
  } catch (error) {
    const message = error?.message === "https_required"
      ? "公网地址必须使用 HTTPS。"
      : error?.message === "backend_permission_denied"
        ? "浏览器没有授予这个地址的访问权限。"
        : String(error?.message || "保存失败");
    setStatusText(elements.endpointStatus, message, "error");
  } finally {
    elements.saveEndpointButton.disabled = false;
  }
}

function renderVersion() {
  try {
    const version = chrome.runtime.getManifest()?.version;
    elements.extensionVersion.textContent = version ? `v${version}` : "";
  } catch {
    elements.extensionVersion.textContent = "";
  }
}

elements.openAppButton.addEventListener("click", () => void openMainApp());
elements.refreshButton.addEventListener("click", () => void refreshConnectorStatus());
elements.syncButton.addEventListener("click", () => void syncIdentities());
elements.endpointForm.addEventListener("submit", saveEndpoint);
[elements.sourcesDetails, elements.settingsDetails].forEach((details) => {
  details.addEventListener("toggle", () => {
    if (!details.open) return;
    const other = details === elements.sourcesDetails
      ? elements.settingsDetails
      : elements.sourcesDetails;
    other.open = false;
  });
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    void detectCurrentSource();
    void refreshConnectorStatus();
  }
});

subscribeSyncStorage(() => void refreshSyncStatus());

initExtLogin(
  {
    deviceKey: document.getElementById("extDeviceKey"),
    btn: document.getElementById("extLoginButton"),
    status: document.getElementById("extLoginStatus"),
  },
  {
    getBaseUrl: getBackendBaseUrl,
    onPaired: () => void refreshConnectorStatus(),
  },
);

renderVersion();
void loadEndpointForm();
void detectCurrentSource();
void refreshSyncStatus();
void refreshConnectorStatus();
globalThis.setInterval(() => void refreshConnectorStatus(), 10_000);

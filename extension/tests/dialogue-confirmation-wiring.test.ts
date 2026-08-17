import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const extensionFile = (path: string) => readFileSync(resolve(path), "utf8");
const projectFile = (path: string) => readFileSync(resolve("..", path), "utf8");

test("toolbar badge stays limited to backend health", () => {
  const serviceWorker = extensionFile("src/background/service-worker.ts");
  const badge = extensionFile("src/background/badge.ts");

  assert.equal((serviceWorker.match(/chrome\.alarms\.create\(/g) ?? []).length, 1);
  assert.match(serviceWorker, /BUFFER_FLUSH_INTERVAL\s*=\s*30_000/);
  assert.doesNotMatch(serviceWorker, /pending-confirmations|pendingConfirmationCount/);
  assert.doesNotMatch(badge, /BADGE_TITLE_PENDING|BADGE_COLOR_PENDING/);
  assert.match(badge, /computeActionBadge\([\s\S]*reachable[\s\S]*uninitialized/);
});

test("desktop and mobile retain durable pending-confirmation surfaces", () => {
  const desktop = projectFile("src/openbiliclaw/web/desktop/assets/js/app.js");
  const desktopHtml = projectFile("src/openbiliclaw/web/desktop/index.html");
  const mobileApp = projectFile("src/openbiliclaw/web/js/app.js");
  const mobileChat = projectFile("src/openbiliclaw/web/js/views/chat.js");
  const mobileState = projectFile("src/openbiliclaw/web/js/state.js");

  assert.match(desktop, /pendingConfirmations:\s*"\/chat\/pending-confirmations"/);
  assert.match(desktop, /SHARED_CHAT_SESSION\s*=\s*"popup"/);
  assert.match(desktop, /executeCardAction/);
  assert.match(desktopHtml, /id="chatPendingCountBadge"/);
  assert.match(desktopHtml, /id="desktopPendingConfirmations"/);

  assert.match(mobileState, /pendingConfirmationCount:\s*0/);
  assert.match(mobileApp, /class="tab-count-badge"/);
  assert.match(mobileChat, /export async function refreshPendingConfirmations/);
  assert.match(mobileChat, /patchState\(\{ pendingConfirmationCount:/);
});

test("mobile and desktop cognition insight sections remain read-only", () => {
  const mobileProfile = projectFile("src/openbiliclaw/web/js/views/profile.js");
  const desktop = projectFile("src/openbiliclaw/web/desktop/assets/js/app.js");
  const desktopCss = projectFile("src/openbiliclaw/web/desktop/assets/css/app.css");
  const backend = projectFile("src/openbiliclaw/api/app.py");

  assert.doesNotMatch(mobileProfile, /submitInsightFeedback|bindInsightActions|data-insight-idx/);
  assert.match(mobileProfile, /insight-readonly/);
  assert.match(mobileProfile, /请在「聊聊口味」的待聊确认入口处理/);

  assert.doesNotMatch(desktop, /data-insight-action|bindInsightActions|respondInsightFeedback/);
  assert.doesNotMatch(desktopCss, /\.insight-actions/);
  assert.match(desktop, /洞察区只读；请在对话的待聊确认入口继续/);
  assert.match(backend, /@app\.post\("\/api\/insights\/feedback"/);
});

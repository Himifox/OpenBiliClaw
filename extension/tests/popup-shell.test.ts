import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  SOURCE_ORDER,
  sourceFromUrl,
  sourcePresentation,
} from "../popup/popup-state.js";

const popupDir = resolve("popup");
const html = readFileSync(resolve(popupDir, "popup.html"), "utf8");
const js = readFileSync(resolve(popupDir, "popup.js"), "utf8");

test("popup is a compact browser connector, not a duplicate client", () => {
  for (const id of [
    "backendBadge",
    "syncHealth",
    "syncStatusText",
    "lastSyncText",
    "openAppButton",
    "currentSourceTitle",
    "syncButton",
    "sourceList",
    "endpointForm",
    "extDeviceKey",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }

  for (const removedId of [
    "recommendationList",
    "viewLibrary",
    "viewProfile",
    "viewChat",
    "initPanel",
    "settingsTabs",
  ]) {
    assert.doesNotMatch(html, new RegExp(`id="${removedId}"`));
  }

  assert.match(js, /action: "OBC_SYNC_IDENTITIES"/);
  assert.match(js, /getMainAppUrl\(\)/);
  assert.match(js, /个已启用 · 共 \$\{SOURCE_ORDER\.length\} 个/);
  assert.match(js, /other\.open = false/);
  assert.match(html, />同步身份<\/button>/);
  assert.doesNotMatch(js, /fetchRecommendations|fetchChatTurns|fetchProfileSummary/);
});

test("shipped popup source contains only connector dependencies", () => {
  const sourceFiles = readdirSync(popupDir)
    .filter((name) => name.endsWith(".js") || name.endsWith(".css") || name.endsWith(".html"))
    .sort();
  assert.deepEqual(sourceFiles, [
    "popup-api.js",
    "popup-backend-config.js",
    "popup-device-auth.js",
    "popup-ext-login.js",
    "popup-state.js",
    "popup-sync-status.js",
    "popup.css",
    "popup.html",
    "popup.js",
  ]);
});

test("supported page URLs resolve to the canonical source", () => {
  const cases = [
    ["https://www.bilibili.com/video/BV1xx", "bilibili"],
    ["https://www.xiaohongshu.com/explore/abc", "xiaohongshu"],
    ["https://www.douyin.com/", "douyin"],
    ["https://www.youtube.com/watch?v=x", "youtube"],
    ["https://x.com/openai/status/1", "twitter"],
    ["https://www.zhihu.com/question/1", "zhihu"],
    ["https://old.reddit.com/r/test", "reddit"],
    ["https://bgm.tv/subject/1", "bangumi"],
    ["https://linux.do/t/topic/1", "linuxdo"],
    ["https://www.v2ex.com/t/1", "v2ex"],
    ["https://weibo.com/u/1", "weibo"],
  ];
  assert.equal(cases.length, SOURCE_ORDER.length);
  for (const [url, expected] of cases) {
    assert.equal(sourceFromUrl(url), expected);
  }
  assert.equal(sourceFromUrl("https://example.com"), null);
  assert.equal(sourceFromUrl("not a url"), null);
});

test("source presentation keeps ready, warning, error, and disabled distinct", () => {
  assert.deepEqual(sourcePresentation({ state: "ready", enabled: true }), {
    label: "已就绪",
    tone: "ready",
    ready: true,
  });
  assert.equal(sourcePresentation({ state: "no_auth", enabled: true }).label, "无需登录");
  assert.equal(sourcePresentation({ state: "unverified", enabled: true }).tone, "warning");
  assert.equal(sourcePresentation({ state: "expired", enabled: true }).tone, "error");
  assert.equal(sourcePresentation({ state: "ready", enabled: false }).tone, "neutral");
  assert.equal(sourcePresentation({ state: "disabled", enabled: false }).tone, "neutral");
});

test("manual identity sync fans out through the service worker without upstream actions", () => {
  const cookieSync = readFileSync(resolve("src/background/cookie-sync.ts"), "utf8");
  const worker = readFileSync(resolve("src/background/service-worker.ts"), "utf8");
  const helper = cookieSync.slice(
    cookieSync.indexOf("export function requestIdentitySync"),
    cookieSync.indexOf("export function handleCookieSyncRuntimeEvent"),
  );

  for (const functionName of [
    "syncBilibiliCookieToBackend",
    "syncDouyinCookieToBackend",
    "syncXCookieToBackend",
    "syncRedditCookieToBackend",
    "syncXhsLoginStateToBackend",
    "syncZhihuLoginStateToBackend",
    "syncLinuxdoLoginStateToBackend",
    "syncV2EXLoginStateToBackend",
    "syncWeiboLoginStateToBackend",
  ]) {
    assert.match(helper, new RegExp(`${functionName}\\(source\\)`));
  }
  assert.doesNotMatch(helper, /favorite|follow|like|save/);
  assert.match(worker, /message\.action === "OBC_SYNC_IDENTITIES"/);
  assert.match(worker, /requestIdentitySync\("popup-manual"\)/);
});

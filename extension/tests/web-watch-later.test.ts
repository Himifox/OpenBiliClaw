import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("mobile web exposes watch-later API and tab entry", async () => {
  globalThis.location = { protocol: "http:", host: "127.0.0.1:8420" };
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() {
        return { items: [{ bvid: "BV1MOBILE" }], total: 1 };
      },
    };
  };

  const api = await import("../../src/openbiliclaw/web/js/api.js?watch-later-api");

  assert.equal(typeof api.fetchWatchLater, "function");
  assert.deepEqual(await api.fetchWatchLater(20, 40), {
    items: [{ bvid: "BV1MOBILE" }],
    total: 1,
  });
  assert.equal(calls[0].url, "http://127.0.0.1:8420/api/watch-later?limit=20&offset=40");

  const appJs = readFileSync(resolve("../src/openbiliclaw/web/js/app.js"), "utf8");
  const libraryJs = readFileSync(resolve("../src/openbiliclaw/web/js/views/library.js"), "utf8");
  assert.match(appJs, /id:\s*"library"/);
  assert.match(appJs, /label:\s*"内容库"/);
  assert.match(appJs, /\["watchLater", "favorites", "history"\]\.includes\(id\)/);
  assert.match(libraryJs, /initWatchLaterView/);
  assert.match(libraryJs, /id:\s*"watchLater"/);
  assert.match(libraryJs, /label:\s*"稍后再看"/);
  assert.match(libraryJs, /role="tablist"/);
});

test("mobile recommend delight tray has a watch-later star action", () => {
  const recommendJs = readFileSync(resolve("../src/openbiliclaw/web/js/views/recommend.js"), "utf8");

  assert.match(recommendJs, /action:\s*"watch-later"/);
  assert.match(recommendJs, /toggleSavedLocally\("watch_later", savedItem\)/);
  assert.match(recommendJs, /hydrateSavedLocally\("watch_later", savedItem/);
});

test("desktop web exposes watch-later page, badge, and delight star", () => {
  const desktopHtml = readFileSync(resolve("../src/openbiliclaw/web/desktop/index.html"), "utf8");
  const desktopJs = readFileSync(
    resolve("../src/openbiliclaw/web/desktop/assets/js/app.js"),
    "utf8",
  );

  assert.match(desktopHtml, /id="contentLibraryBtn"/);
  assert.match(desktopHtml, /id="contentLibraryWatchLaterTab"/);
  assert.match(desktopHtml, /id="watchLaterCountBadge"/);
  assert.match(desktopHtml, /id="watchLaterPage"/);
  assert.match(desktopHtml, /data-delight="watch-later"/);
  assert.match(desktopJs, /watchLaterPage/);
  assert.match(desktopJs, /refreshWatchLater/);
  assert.match(desktopJs, /watchLaterStatus/);
  assert.match(desktopJs, /syncWatchLaterButtons/);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildExtensionUiUrl,
  openExtensionUi,
} from "../src/background/extension-ui.ts";

test("connector fallback URL has no removed client deep link", () => {
  assert.equal(
    buildExtensionUiUrl(),
    "chrome-extension://__EXTENSION_ID__/popup/popup.html",
  );
});

test("connector opens the Chrome side panel when available", async () => {
  const calls: Array<{ windowId: number }> = [];
  const result = await openExtensionUi(
    {
      sidePanel: {
        open(options) {
          calls.push(options);
        },
      },
    },
    { windowId: 42 },
  );

  assert.equal(result, "sidePanel");
  assert.deepEqual(calls, [{ windowId: 42 }]);
});

test("connector fallback opens only the compact popup page", async () => {
  const calls: Array<{ url: string }> = [];
  const result = await openExtensionUi({
    tabs: {
      create(options) {
        calls.push(options);
      },
    },
  });

  assert.equal(result, "tab");
  assert.deepEqual(calls, [
    { url: "chrome-extension://__EXTENSION_ID__/popup/popup.html" },
  ]);
});

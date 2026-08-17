import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function readProjectFile(path: string): string {
  return readFileSync(resolve("..", path), "utf8");
}

test("desktop and mobile runtime handlers coalesce expensive reloads", () => {
  const desktop = readProjectFile("src/openbiliclaw/web/desktop/assets/js/app.js");
  const mobileRecommend = readProjectFile("src/openbiliclaw/web/js/views/recommend.js");
  const mobileProfile = readProjectFile("src/openbiliclaw/web/js/views/profile.js");

  assert.match(desktop, /function scheduleBackendHydration/);
  assert.match(desktop, /function scheduleActivityPageRefresh/);
  assert.match(desktop, /backendHydrationInFlight/);
  assert.match(desktop, /activityPageRefreshInFlight/);
  assert.doesNotMatch(desktop, /includes\(event\.type\)\) void hydrateFromBackend\(\);/);

  const desktopRuntimeHandler = desktop.match(
    /function handleRuntimeEvent\(event\) \{[\s\S]*?\r?\n    \}\r?\n\r?\n    function connectRuntimeStream/,
  )?.[0] ?? "";
  assert.notEqual(desktopRuntimeHandler, "");
  assert.match(desktopRuntimeHandler, /scheduleDesktopRecommendationRecovery\(\);/);
  assert.match(desktopRuntimeHandler, /desktopRuntimeGeneration \+= 1;/);
  assert.doesNotMatch(desktopRuntimeHandler, /state\.videos\s*=\s*normalizeRecommendationList/);

  const poolUpdatedBlock = mobileRecommend.match(
    /if \(type === "refresh\.pool_updated"\) \{[\s\S]*?\} else if/,
  )?.[0] ?? "";
  assert.notEqual(poolUpdatedBlock, "");
  assert.match(poolUpdatedBlock, /mergeRuntimeStatusEvent/);
  assert.match(poolUpdatedBlock, /scheduleRecommendationRecovery\(\);/);
  assert.doesNotMatch(poolUpdatedBlock, /scheduleRecommendationItemsRefresh|fetchRecommendations/);

  assert.match(mobileProfile, /function scheduleProfileRefresh/);
  assert.match(mobileProfile, /profileRefreshInFlight/);
  assert.doesNotMatch(mobileProfile, /if \(type === "profile_updated"\) \{\s*loadData\(\);\s*\}/);
});

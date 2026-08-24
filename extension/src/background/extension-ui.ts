type ExtensionUiChrome = {
  runtime?: { getURL(path: string): string };
  sidePanel?: { open(options: { windowId: number }): Promise<unknown> | unknown };
  tabs?: { create(options: { url: string }): Promise<unknown> | unknown };
};

type FirefoxSidebarAction = {
  open(): Promise<void>;
};

export function buildExtensionUiUrl(): string {
  const path = "popup/popup.html";
  if (
    typeof chrome !== "undefined" &&
    chrome.runtime &&
    typeof chrome.runtime.getURL === "function"
  ) {
    return chrome.runtime.getURL(path);
  }
  return `chrome-extension://__EXTENSION_ID__/${path}`;
}

export async function openExtensionUi(
  chromeApi: ExtensionUiChrome,
  { windowId }: { windowId?: number } = {},
): Promise<"sidePanel" | "sidebarPanel" | "tab"> {
  if (typeof windowId === "number" && chromeApi.sidePanel?.open) {
    await chromeApi.sidePanel.open({ windowId });
    return "sidePanel";
  }

  try {
    const browserApi = (globalThis as Record<string, unknown>).browser as
      | { sidebarAction?: FirefoxSidebarAction }
      | undefined;
    if (browserApi?.sidebarAction?.open) {
      await browserApi.sidebarAction.open();
      return "sidebarPanel";
    }
  } catch {
    // Firefox sidebar API unavailable; fall back to a connector tab.
  }

  await chromeApi.tabs?.create({ url: buildExtensionUiUrl() });
  return "tab";
}

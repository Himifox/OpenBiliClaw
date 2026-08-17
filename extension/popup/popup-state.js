export const SOURCE_ORDER = [
  "bilibili",
  "xiaohongshu",
  "douyin",
  "youtube",
  "twitter",
  "zhihu",
  "reddit",
  "bangumi",
  "linuxdo",
  "v2ex",
  "weibo",
];

export const SOURCE_LABELS = Object.freeze({
  bilibili: "B 站",
  xiaohongshu: "小红书",
  douyin: "抖音",
  youtube: "YouTube",
  twitter: "X (Twitter)",
  zhihu: "知乎",
  reddit: "Reddit",
  bangumi: "Bangumi",
  linuxdo: "Linux.do",
  v2ex: "V2EX",
  weibo: "微博",
});

const HOST_SOURCE_RULES = [
  [/(^|\.)bilibili\.com$/i, "bilibili"],
  [/(^|\.)xiaohongshu\.com$/i, "xiaohongshu"],
  [/(^|\.)douyin\.com$/i, "douyin"],
  [/(^|\.)youtube\.com$/i, "youtube"],
  [/(^|\.)(x|twitter)\.com$/i, "twitter"],
  [/(^|\.)zhihu\.com$/i, "zhihu"],
  [/(^|\.)(reddit\.com|redd\.it)$/i, "reddit"],
  [/(^|\.)(bgm|bangumi)\.tv$/i, "bangumi"],
  [/^linux\.do$/i, "linuxdo"],
  [/(^|\.)v2ex\.com$/i, "v2ex"],
  [/(^|\.)(weibo\.com|weibo\.cn)$/i, "weibo"],
];

export function sourceFromUrl(value) {
  try {
    const host = new URL(value).hostname;
    return HOST_SOURCE_RULES.find(([pattern]) => pattern.test(host))?.[1] ?? null;
  } catch {
    return null;
  }
}

export function sourcePresentation(item) {
  if (!item || typeof item !== "object") {
    return { label: "未知", tone: "neutral", ready: false };
  }
  const sourceState = String(item.state || "missing").toLowerCase();
  if (sourceState === "disabled" || item.enabled === false) {
    return { label: "未启用", tone: "neutral", ready: false };
  }
  if (["ok", "ready", "no_auth"].includes(sourceState) || item.logged_in === true) {
    return {
      label: sourceState === "no_auth" ? "无需登录" : "已就绪",
      tone: "ready",
      ready: true,
    };
  }
  if (["partial", "stale", "unverified", "missing", "login_required"].includes(sourceState)) {
    return {
      label: sourceState === "unverified" ? "待验证" : "需要处理",
      tone: "warning",
      ready: false,
    };
  }
  if (["expired", "blocked", "rate_limited", "error"].includes(sourceState)) {
    return { label: "连接异常", tone: "error", ready: false };
  }
  return { label: "未知", tone: "neutral", ready: false };
}

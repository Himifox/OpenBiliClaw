# 浏览器插件壳简化契约

日期：2026-08-17
接入等级：`capability-increment`
目标：把浏览器插件收缩为 OpenBiliClaw/未来 NEKO 的浏览器连接器，而不是第二套完整客户端。

## 冻结边界

| 能力 | 适用性 | 执行 | 本次约束 |
|---|---|---|---|
| 支持站点行为采集 | required | PASS | 保留 content kernel、平台 adapter、MV3 durable buffer 与 `/api/events` 上报；全量扩展回归未出现该链路新增失败 |
| 浏览器来源任务 | required | PASS | 保留各平台 dispatcher、task tab 隔离、mutex、lease 与 task-result 协议；dispatcher/mutex 与构建资产测试通过 |
| Cookie / 登录态同步 | required | PASS | 保留自动同步；新增显式“同步身份”入口，只向已配置后端写入既有凭据/布尔登录态；cookie-sync 与 fan-out 契约测试通过 |
| 后端连接状态 | required | PASS | side panel 首屏只显示可达性、当前站点与来源就绪摘要；实际在线渲染与 390px 检查通过 |
| 后端地址 | required | PASS | 保留协议、主机、端口编辑及 optional host permission 门禁；endpoint 测试通过 |
| 扩展设备配对 | required | PASS | 保留远程后端短会话和设备密钥交换，不回退到明文密码；device-auth/ext-login 测试通过 |
| 打开主应用 | required | PASS | side panel 只提供 `/web` 主入口；静态契约与实际渲染通过 |
| 推荐流 | N/A | PASS | 产品边界排除：主应用已有完整推荐 surface；popup-shell 测试证明插件不再携带对应入口或 API 调用 |
| 内容库 / 收藏 / 稍后看 / 历史 | N/A | PASS | 产品边界排除：主应用保留；popup 业务模块/测试已移除，后台 native-save task runner 未删除 |
| 画像与画像编辑 | N/A | PASS | 产品边界排除：主应用保留；popup-shell 测试证明无画像入口/API |
| 对话与确认卡 | N/A | PASS | 产品边界排除：主应用保留；桌面/移动共享对话测试仍在，popup 依赖已移除 |
| Guided init | N/A | PASS | 产品边界排除：主应用与 setup surface 保留；popup init 模块/入口已移除 |
| 全量后端配置编辑 | N/A | PASS | 产品边界排除：主应用负责；插件产物只保留连接 endpoint 与设备配对模块 |
| 上游账号写操作 | N/A | PASS | 未授权且不属于简化范围；fan-out 契约测试禁止 favorite/follow/like/save，真实账号 mutation 为 none |
| 发布 / 商店上传 | N/A | NOT_RUN | 用户未要求发布；不改版本、不打 tag、不上传商店 |

`N/A` 仅描述 side panel 产品面，不表示后端或主应用删除对应能力。构建产物不得继续携带已移除的 popup 业务模块。

## 设计方向

- 目的：让第一次打开插件的人在几秒内回答三个问题——后端连上了吗、当前网站身份可用吗、下一步去哪里。
- 语气：克制、工具化、可信；不再模拟完整内容客户端。
- 任务顺序：确认连接 → 查看当前来源 → 必要时同步 → 打开主应用。
- 色彩世界：B 站珊瑚粉、纸白、墨黑、状态绿、提醒琥珀；颜色只表达品牌和状态。
- 专属元素：把插件明确标成“浏览器连接器”，用三段桥接职责（身份、行为、任务）解释它为何存在。

## 验收证据

| 门 | 要求 |
|---|---|
| 单元测试 | 新 popup API、来源状态投影、身份同步消息、既有 endpoint/device-auth/cookie/task 测试通过 |
| 类型检查 | `tsc -p tsconfig.json --noEmit` 通过 |
| 构建 | Chrome 与 Firefox 构建、manifest asset preflight 通过；Safari 只做可在 Windows 执行的构建/资产检查 |
| 产物 | popup 包只包含精简 shell 及连接/配对依赖，不包含已移除的业务模块 |
| UI | 实际渲染宽屏与 390px；横向 overflow 均为 0；独立 fresh-eyes 审核无 blocker/major |
| 安全 | 无真实上游写操作；手动同步只复用既有 credential/login-state endpoint |
| 文档 | `docs/modules/extension.md`、README 中的插件定位与 `docs/changelog.md` 同步 |

## 验收结果

- TypeScript：`tsc -p tsconfig.json --noEmit`，PASS。
- 定向回归：84 / 84 PASS，覆盖 popup shell、endpoint、device auth、ext login、cookie sync、service-worker buffer、dispatcher mutex、manifest/build assets 与桌面/移动 runtime 合并刷新。
- 全量扩展回归：1016 / 1018 PASS；两个失败均为基线环境/跨平台测试（本机无 `npm` 可执行文件、AMO workflow 的 CRLF 正则），不命中本次 popup / background 改动。
- 构建：Chrome 19、Firefox 19、Safari 20 个 manifest script/WAR 资产预检全部 PASS；Firefox / Safari popup 目录均精确包含 8 个连接器文件。
- UI：1024 与 390px 横向 overflow 为 0，主控件至少 44px；fresh-eyes 首轮发现的数量语义、长列表与状态截断问题已修复，复核无 blocker / major。
- 状态变更：真实上游账号 mutation 为 none；未改版本、未打 tag、未上传商店。

# 浏览器插件模块

> 2026-08-17 起，浏览器插件是 OpenBiliClaw / NEKO 的轻量浏览器连接器，不是第二套完整客户端。推荐、内容库、画像、对话、guided init 与完整后端配置由 NEKO、桌面 Web `/web` 或移动 Web `/m` 承载。

## 产品边界

插件保留浏览器上下文独有的能力：

- 识别当前网页来源和浏览器内登录态。
- 在支持站点采集必要行为事件。
- 执行依赖真实浏览器会话的有界只读来源任务。
- 通过 durable outbox 把事件可靠地交给用户配置的 Core。
- 展示 Core/NEKO 连接、离线缓存、最近同步、当前来源和身份状态。
- 提供手动身份同步、后端 endpoint、远程设备配对和“打开主应用”。

插件明确不承载：

- 推荐流、惊喜推荐、内容库、画像和对话。
- 兴趣/避雷探针的展示与处理。
- guided init、移动端二维码、调度开关、模型配置和完整来源配置。
- 未经精确授权的点赞、收藏、关注、订阅等上游账号写操作。

这些排除项由 `extension/tests/popup-shell.test.ts` 锁定：构建中的 popup 不得重新出现旧业务入口，也不得请求推荐、画像或聊天 API。

## 运行架构

```text
支持站点页面
  -> content kernel + platform adapter
  -> BehaviorEvent
  -> background durable outbox
  -> POST /api/events
  -> OpenBiliClaw Core / NEKO

Core runtime-stream
  -> 身份同步请求 / task_available / reload / E2E
  -> background dispatcher
  -> 隔离的真实站点任务 tab
  -> source task-result endpoint

Core runtime-stream
  -> delight.candidate / interest.probe / avoidance.probe
  -> background 仅维持传输，不展示、不确认
  -> NEKO 或其它真实可见宿主展示成功后记录交付
```

popup 和 background 是两个不同产品面：popup 只显示连接器状态；background 即使 popup 没有打开，也会继续承担 outbox、登录态同步、任务调度和 runtime presence。

## 当前能力

| 子模块 | 状态 | 当前职责 |
|---|---|---|
| 连接器 popup | ✅ | 显示 Core/NEKO 连接、离线缓存、最近同步、当前来源、来源状态和身份同步；打开 `/web` 主应用 |
| Endpoint 与设备配对 | ✅ | 保存 HTTP(S)、主机和端口；远程 endpoint 请求精确 host permission，并用设备密钥换取短会话 |
| 行为采集 | ✅ | `content/kernel.ts` 与平台 adapter 归一化点击、停留、滚动、播放和显式反馈等行为 |
| Durable outbox | ✅ | live / inflight / parked 三段持久化，最多 1000 条、30 天 TTL、每批最多 100 条；失败和 Core 未初始化时不丢事件 |
| 身份同步 | ✅ | 自动或手动同步已有 Cookie/登录布尔状态；手动同步不触发上游写操作 |
| 浏览器来源任务 | ✅ | 保留各来源 dispatcher、任务 tab 隔离、mutex、lease、恢复和 task-result 协议 |
| Runtime stream | ✅ | 提供 extension presence、任务唤醒、身份同步、热重载和 E2E 控制；主动内容由宿主展示 |
| 主动交付所有权 | ✅ | 连接器不调用 `/api/delight/sent`、`/api/notifications/sent` 或 `/api/cognition-updates/seen`，也不轮询对应 pending 队列 |
| Chrome / Firefox / Safari | ✅ | 三目标独立构建和资产校验；Firefox 使用 sidebar，Safari 使用 action popup |
| OS 通知 | N/A | 产品边界已移除；Chrome/Firefox/Safari manifest 均不请求 `notifications` 权限 |

## popup 结构

`extension/popup/` 只包含九个运行文件：

- `popup.html` / `popup.css`：紧凑连接器页面。
- `popup.js`：页面编排、active-tab 识别、手动身份同步和 endpoint 保存。
- `popup-state.js`：来源顺序、URL 识别和状态投影纯函数。
- `popup-api.js`：`/api/ping`、`/api/health`、`/api/sources/status` 与主应用 URL。
- `popup-sync-status.js`：离线队列数量和最近成功同步时间。
- `popup-backend-config.js`：endpoint 与 optional host permission。
- `popup-device-auth.js`：远程后端短会话。
- `popup-ext-login.js`：设备配对 UI。

popup 不复制 `web/shared/` 的推荐、保存、画像或对话客户端模块。Firefox 与 Safari staging 直接复制这九个文件。

## background 结构

核心文件：

- `service-worker.ts`：outbox flush、runtime stream、生命周期和消息总线。
- `buffer.ts`：live / inflight / parked durable outbox 与稳定 `event_id`。
- `badge.ts`：后端离线、未初始化和已就绪三态工具栏徽标。
- `cookie-sync.ts`：Cookie 或登录态同步；只上传各来源契约允许的最小字段。
- `extension-ui.ts`：打开 Chrome side panel、Firefox sidebar 或紧凑 connector tab。
- `e2e-runner.ts`：后端驱动的白名单真实页面捕捉自检。
- `task-tab.ts` / `task-mutex.ts`：自动任务页和跨来源互斥。
- `*-task-dispatcher.ts`：各来源任务领取、执行、恢复和结果回传。
- `native-save-task-runner.ts`：受精确授权的 durable native-save 任务；它不是 popup 产品功能。

当前任务 dispatcher 覆盖 B 站、小红书、抖音、YouTube、X、知乎、Reddit、Linux.do、V2EX 与微博。Bangumi 的公开发现由后端完成，插件只参与网页来源/身份识别，不读取 Bangumi Cookie 或采集普通浏览行为。

Native save broker 的 6/6 executor 已接入并有既有真实账号验证：YouTube、小红书、抖音、X、知乎和 Reddit；这属于 background 任务能力，不会恢复 popup 的保存列表或推荐卡。
Reddit / X / YouTube / 小红书 / 抖音 / 知乎六个 executor 均已接入并完成 fixture、失败恢复与既有真实账号验证。

## 主动事件交付

连接器没有推荐或探针的可见 surface，因此“WebSocket 收到”不等于“用户看到”。

- `delight.candidate`
- `interest.probe`
- `avoidance.probe`

background 收到这些事件后只结束本地分派，不写送达状态。普通推荐通知和认知更新也不再由 background 轮询并静默确认。只有 NEKO 或其它真实可见宿主成功渲染内容后，才能调用对应交付/已读接口；跳过、打断、拒绝和展示失败都不能消费候选。

旧的 `?tab=recommend`、`?tab=profile`、`?tab=chat` 与 `?delight=...` 插件深链已经移除。点击扩展图标只打开连接器；完整体验通过“打开主应用”进入 `/web`。

## 后端接口边界

连接器直接使用：

- `GET /api/ping`：轻量可达性探测；旧后端 404 时回退 `/api/health`。
- `GET /api/health`：画像与 embedding 就绪摘要。
- `GET /api/sources/status`：来源启用、凭据和验证状态。
- `POST /api/events`：批量行为事件。
- `GET /api/runtime-stream?client=background`：presence、任务和同步控制流。
- `POST /api/auth/extension-token`：远程设备短会话。
- `/api/sources/<slug>/next-task` 与 `/task-result`：来源任务协议。
- 各来源 Cookie / login-state endpoint：只按来源契约同步允许字段。

连接器禁止把以下接口当成后台队列清理器：

- `/api/delight/sent`
- `/api/notifications/pending` / `/api/notifications/sent`
- `/api/cognition-updates/pending` / `/api/cognition-updates/seen`

这些接口可以继续服务真正可见的宿主，但 background 不得仅因收到或轮询到对象就确认。

## 离线与恢复

- `obc_event_buffer`：等待发送的新事件。
- `obc_event_inflight`：已领取但尚未得到后端成功确认的批次。
- `obc_parked_events`：Core 明确返回 `not_initialized` 后暂存的事件。
- `obc_last_sync_at`：最近成功同步时间，只用于连接器状态展示。

三段合计最多 1000 条，保留 30 天。成功确认后按 `inflight -> parked -> live` 顺序继续发送；进程、浏览器或 MV3 service worker 重启后复用原 `event_id`，不会把重试伪装成新事件。

## 权限与隐私

- 固定 host permission 只覆盖支持站点和本机 `127.0.0.1` / `localhost`。
- 局域网或远程后端只在用户保存 endpoint 时请求对应 optional host permission。
- Chrome/Firefox 不请求 `tabs` 或 `notifications` 权限；现有任务 API 在当前 MV3 能力范围内工作。
- Cookie 同步仅面向用户配置的 OpenBiliClaw 后端；登录布尔来源不上传 Cookie 值。
- content/task executor 不向后端上传原始 HTML、响应正文、header 或 token。
- 默认 E2E 只执行不会改变上游账号状态的白名单动作。native save 必须具备 exact platform/action/content ID/target 授权。

## 构建与测试

在 `extension/` 目录运行：

```bash
npm test
npm run typecheck
npm run build
npm run verify:assets
npm run build:firefox
npm run verify:assets:firefox
npm run build:safari
npm run verify:assets:safari
```

关键契约测试：

- `popup-shell.test.ts`：popup 只含连接器依赖和控件。
- `extension-ui.test.ts`：打开 side panel/sidebar/tab 时不携带旧业务深链。
- `service-worker-stream.test.ts`：background 不确认任何未展示主动内容。
- `manifest-assets.test.ts`：三目标权限与构建资产一致。
- `service-worker-buffer.test.ts` / `buffer.test.ts`：outbox、重试和恢复。
- 各来源 adapter、executor 和 dispatcher 测试：任务输入、隔离、终态与回传。

## 手动验收

1. 从当前 worktree 构建目标浏览器产物，并记录绝对路径、版本和 service worker hash。
2. 在浏览器扩展管理页加载该产物，而不是只 reload 旧安装包。
3. 打开支持站点，确认连接器能识别当前来源、读取状态和手动触发身份同步。
4. 停止 Core 后产生允许的行为事件，确认离线数量增加；恢复 Core 后确认数量归零、最近同步时间更新且 `event_id` 不变。
5. 投递主动事件，确认连接器不展示、不确认；由 NEKO/可见宿主展示后再验证送达状态。
6. 对任务型来源分别验证任务 tab 隔离、普通行为事件增量为 0、结果关联当前 extension ID 和安装产物。

本次连接器清理没有执行真实已登录账号或上游状态变更 E2E；自动化测试和构建不能替代安装版真机验收。

## 当前限制

- 行为按钮识别依赖 DOM、类名和 `aria-label`，不等于平台服务端最终状态。
- 部分来源任务需要前台渲染，dispatcher 会尽量恢复用户原标签页；每个来源的真实限制以对应模块文档和验收记录为准。
- 账号周期回拉默认关闭；只有显式启用、画像就绪、guided init 空闲且 background presence 在线时才会入队。
- popup 不提供推荐、画像、聊天、初始化或完整设置的离线替代页；Core 离线时只显示连接状态和缓存事实。
- Chrome/Firefox/Safari 构建通过不等于三浏览器真实登录任务均已验收，发布说明必须分别报告安装版证据。

## Release 分发

- Chromium：`openbiliclaw-extension-vX.Y.Z.zip`
- Firefox：临时包 `*-firefox.zip`；AMO 凭据可用时生成 signed `*-firefox.xpi`
- Safari：`*-safari.dmg`；签名/公证依赖 Apple 凭据

发布前必须重新构建并验证对应目标资产，记录 archive hash 与来源 commit。版本、tag、GitHub Release、Chrome Web Store、Firefox AMO 和 Safari 分发均是独立发布动作，不因本地构建通过而自动完成。

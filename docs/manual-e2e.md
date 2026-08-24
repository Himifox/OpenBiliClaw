# 手动端到端联调

> 用于验证 CLI 首跑、插件连接/采集、持续补货，以及 NEKO 或其它可见宿主的主动消息交付边界。

## 前置条件

1. 本地已配置有效的 LLM Provider 和 B 站 Cookie
2. 已在项目根目录创建本地 `config.toml`
3. Chrome 已允许加载 unpacked extension

## CLI 首跑

```bash
PYTHONPATH=src .venv/bin/openbiliclaw auth status
PYTHONPATH=src .venv/bin/openbiliclaw init
PYTHONPATH=src .venv/bin/openbiliclaw recommend
```

验收：

- `init` 输出历史条数、画像状态和发现内容数
- `recommend` 能输出朋友式推荐文案

## 启动本地后端

```bash
PYTHONPATH=src .venv/bin/openbiliclaw start
```

校验接口：

```bash
curl http://127.0.0.1:8420/api/health
curl http://127.0.0.1:8420/api/runtime-status
curl http://127.0.0.1:8420/api/recommendations
```

## 加载插件

```bash
cd extension && npm install && npm run build
```

1. 进入 Chrome 扩展管理页
2. 打开”开发者模式”
3. 加载 `extension/` 目录
4. 固定侧边栏图标

## 插件采集与持续补货

1. 打开 B 站首页、搜索页、视频页
2. 执行搜索、点击、播放、暂停、滚动等行为
3. 等待 1 到 2 个 flush 周期

校验：

```bash
sqlite3 data/openbiliclaw.db "select count(*) from events;"
sqlite3 data/openbiliclaw.db "select event_type, count(*) from events group by event_type order by event_type;"
curl http://127.0.0.1:8420/api/runtime-status
```

重点看：

- `events` 数量增长
- `runtime-status.pending_signal_events` 会先升高，再在自动刷新后归零
- `runtime-status.last_refresh_at` 发生变化

## 连接器侧边栏验证

- 能显示连接状态、后端地址和当前来源
- 能显示身份同步与离线 outbox 摘要
- 能手动触发同步并打开主应用
- 不出现推荐、画像、聊天、初始化或完整配置入口

## 推荐反馈

在桌面 Web、移动 Web 或 NEKO 中分别测试：

- `喜欢`
- `不喜欢`
- `写一句`

校验：

```bash
sqlite3 data/openbiliclaw.db "select id,bvid,feedback_type,feedback_note,feedback_at from recommendations order by id desc limit 10;"
sqlite3 data/openbiliclaw.db "select id,event_type,title,metadata from events where event_type='feedback' order by id desc limit 10;"
```

## 主动消息交付

1. 让系统产生一条尚未展示的 delight / probe 候选。
2. 只保持插件 background 在线，确认不会出现浏览器系统通知，也不会写 sent/seen/delivered。
3. 打开 NEKO 或其它支持主动消息的真实可见宿主，确认候选成功渲染后才记录交付。
4. 中断、拒绝或渲染失败时，候选必须保持可重试，不能静默消费。

## 期望结果

- CLI 能完成首跑初始化
- 插件能持续上报行为
- 后端能自动补货候选池
- 侧边栏只显示连接器状态，不承载推荐或聊天
- 插件 background 不会把未展示候选确认成已送达
- 可见宿主中的反馈和聊天继续推动系统理解用户

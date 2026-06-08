# bili-ying

## 插件描述

Bilibili 直播订阅提醒与视频信息解析插件。群管理员或 bot 管理员可以为当前群添加直播间订阅，插件会定时检查直播间状态，并在开播或下播时向群聊发送提醒。群内发送 Bilibili 视频链接或 BV 号时，插件会自动回复视频名称、BV 号、UP 主与视频封面小图。

提醒表头格式为：

```text
主播名称 开播啦！
主播名称 下播啦！
```

## 指令说明

@bot bili add 直播间号：添加当前群直播订阅
@bot bili remove 直播间号：删除当前群直播订阅
@bot bili delete 直播间号：删除当前群直播订阅
@bot bili list：展示当前群所有直播订阅
Bilibili 视频链接或 BV号：自动解析视频名称、BV号、UP主与封面小图

## 其他内容

- 仅群聊可用。
- 直播订阅管理指令仅群管理员或 bot 管理员可触发。
- 视频信息解析不需要 @bot，也不要求管理员权限；无效 BV 号或无法获取信息时不会回复。
- 视频封面使用远程缩略图 URL 发送，插件本地不会保存图片缓存。
- 所有群订阅数据存储在 `bili_ying_subscriptions.json`。
- 插件配置存储在 `bili_ying_config.json`。
- API 访问频率由 `bili_ying_config.json` 的 `check_interval_seconds` 控制，当前默认每 120 秒检查一次，代码会限制最小间隔为 60 秒。
- 插件会按直播间去重后分批查询，单批数量由 `bili_ying_config.json` 的 `check_batch_size` 控制，当前默认每批 10 个直播间；当前查询位置记录在 `check_cursor`。
- 若 API 访问出现 403、412、429 或连接被重置，插件会按 `notify_admin_on_api_reset` 配置向 bot 管理员发送私聊提醒；同类提醒默认至少间隔 1 小时。
- 当前使用公开接口 `https://api.live.bilibili.com/room/v1/Room/get_info`。
- 视频信息解析使用公开接口 `https://api.bilibili.com/x/web-interface/view`。
- 接口返回 `live_status`，其中 `0` 为未开播，`1` 为直播中，`2` 为轮播中。
- 如果 Bilibili 接口出现风控、403、412 或需要登录的问题，请在 `bili_ying_config.json` 的 `cookie` 中填入可用登录 Cookie。
- 插件目录下提供本地 Cookie 获取入口 `login_bilibili_cookie.py`，不会从 QQ 消息触发。请在项目根目录运行：`python yingice/plugins/bili_ying/login_bilibili_cookie.py`。脚本会在本机启动可见浏览器，登录成功并检测到 `SESSDATA` 后自动写入 `bili_ying_config.json`。
- 如果 Playwright 无法启动浏览器，请先安装依赖：`pip install playwright`；若本机没有可用 Edge/Chromium，请再执行：`python -m playwright install chromium`。
- Cookie 获取方式：在浏览器登录 Bilibili 后打开开发者工具，进入 Network/网络面板，刷新任意 Bilibili 页面或直播间页面，选中对 `bilibili.com` 或 `live.bilibili.com` 的请求，在 Headers/标头中复制 Request Headers 里的 `Cookie` 内容，填入 `bili_ying_config.json` 的 `cookie` 字段。
- Cookie 中常见关键字段包括 `SESSDATA`、`bili_jct`、`DedeUserID` 等；Cookie 属于登录凭证，请不要公开发送或提交到公共仓库。

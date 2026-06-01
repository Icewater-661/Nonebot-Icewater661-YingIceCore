# todo

## 插件描述

todo 提醒插件。支持在群聊或私聊中创建任务、查看任务、删除任务，并在指定日期提醒。

## 指令说明

.todo：输出本插件帮助
.todo open/close：在群聊中开启或关闭 todo 提醒
.todo add todo内容 [date+日期 / afterday 天数 / every 天数]：添加 todo，可选择提醒日期或循环周期
.todo list：展示当前用户的 todo 列表
.todo remove 编号：删除编号对应的 todo

## 其他内容

- 指令前缀支持 `.todo`、`。todo`、`!todo`、`！todo`。
- `date+日期` 支持年月日格式，也支持月日格式；月日会按最近的未来年份处理。
- 提醒日期必须晚于今天，不能创建今天或过去日期的提醒。
- `afterday 日期数` 会在若干天后提醒，提醒后删除当前 todo。
- `every 日期数` 会在若干天后首次提醒，之后自动按周期创建下一次提醒。
- 非 bot 管理员每人最多创建一个循环 todo。
- 每个人最多包含 5 条 todo。
- 群聊提醒默认开启，群管理员或 bot 管理员可用 `.todo open/close` 切换。
- 数据文件为 `todo_data.json`。
- 群聊开关文件为 `todo_group_config.json`。
- 提醒依赖 bot 正在运行；如果 bot 在提醒时间离线，重新上线后会补发已到期提醒。

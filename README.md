# Nonebot-Icewater661-YingIceCore

基于 NoneBot2 与 OneBot V11 的 QQ 机器人项目。

## 项目结构

```text
Nonebot-Icewater661-YingIceCore/
├─ .env
├─ .env.dev
├─ .env.prod
├─ .gitattributes
├─ .gitignore
├─ LICENSE
├─ README.md
├─ pyproject.toml
├─ ying_point.csv
└─ yingice/
   └─ plugins/
      ├─ jrcp/
      │  └─ __init__.py
      ├─ pat_head/
      │  └─ __init__.py
      ├─ ying_permission/
      │  ├─ __init__.py
      │  ├─ README.md
      │  └─ permission_config.json
      └─ ying_point_system/
         ├─ __init__.py
         └─ ying_point_feedback.json
```

说明：

- `pyproject.toml`：项目依赖、NoneBot 插件目录与适配器配置。
- `ying_point.csv`：好感度数据文件，列为 `QQ号, 好感度, 最后修改时间戳`。
- `yingice/plugins/`：本项目所有本地插件目录。

## 启动方式

```bash
nb run --reload
```

项目插件目录由 `pyproject.toml` 中的配置加载：

```toml
[tool.nonebot]
plugin_dirs = ["yingice/plugins"]
```

## 插件与指令

### jrcp

群聊今日 CP 插件。

指令：

```text
。jrcp
.jrcp
!jrcp
```

功能：

- 仅在群聊中触发。
- 自动查询当前群成员列表。
- 以当前日期和群号为随机种子生成当日配对。
- 群成员数为偶数时，bot 自己也参与配对。
- 群成员数为单数时，bot 自己不计入配对池。
- 回复当前用户的今日 CP 头像和 QQ 号。

回复格式：

```text
xxx（用户ID）的今日cp为：另一名群成员（另一名群成员ID）【另一名群成员的头像】
```

### ying_point_system

好感度系统插件，负责查询与修改用户好感度。

指令：

```text
@bot 好感
```

功能：

- 查询当前用户好感度。
- 首次查询时创建用户记录，默认好感度为 `100`，最后修改时间戳为 `0`。
- 查询结果会附加 `ying_point_feedback.json` 中匹配好感区间的自定义文案。

反馈配置文件：

```text
yingice/plugins/ying_point_system/ying_point_feedback.json
```

区间格式为 `[min, max)`，`null` 表示半开放区间：

```json
[
  {
    "min": null,
    "max": 100,
    "feedback": "她好像还在观察你。"
  }
]
```

其他插件可调用：

```python
from yingice.plugins.ying_point_system import change_ying_point, get_ying_point
```

### pat_head

摸头互动插件。

指令：

```text
@bot 摸头
```

功能：

- 回复摸头互动文案。
- 调用好感度系统尝试增加 `1` 点好感。
- 正向好感每天最多生效一次，未生效时只返回当前好感。

回复示例：

```text
唔...被摸头了，感觉有点开心。
好感上升了1，当前好感：101
```

### ying_permission

权限管理插件，负责管理员权限、用户黑名单与群黑名单。

配置文件：

```text
yingice/plugins/ying_permission/permission_config.json
```

配置项：

```json
{
  "masterQQ": [],
  "blackQQ": [],
  "blackGroup": []
}
```

管理员指令必须由 `masterQQ` 中的用户发送，并且以 `@bot` 开头：

```text
@bot blackqq add QQ号
@bot blackqq remove QQ号
@bot blackgroup add 群号
@bot blackgroup remove 群号
```

功能：

- `blackQQ` 中的用户消息不会触发后续插件。
- `blackGroup` 中的群消息不会触发后续插件。
- QQ 号和群号可写为数字或字符串。

其他插件可调用管理员权限：

```python
from nonebot import on_message

from yingice.plugins.ying_permission import MASTER

matcher = on_message(permission=MASTER)
```

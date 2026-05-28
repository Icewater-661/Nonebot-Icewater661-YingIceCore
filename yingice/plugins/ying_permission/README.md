# Ying Permission

YingIce 的权限管理插件，用于维护管理员列表、用户黑名单与群黑名单。

## 配置文件

配置文件位于当前插件目录：

```text
permission_config.json
```

配置项：

```json
{
  "masterQQ": [],
  "blackQQ": [],
  "blackGroup": []
}
```

- `masterQQ`：管理员 QQ 号列表，只有这里的用户可以执行权限管理指令。
- `blackQQ`：用户黑名单，被加入后不会触发后续插件内容。
- `blackGroup`：群黑名单，被加入后该群消息不会触发后续插件内容。

QQ 号和群号可以写成数字或字符串，插件内部会统一按字符串处理。

## 管理指令

以下指令必须由 `masterQQ` 中的用户发送，并且必须以 @bot 开头。

```text
@bot blackqq add QQ号
@bot blackqq remove QQ号
@bot blackgroup add 群号
@bot blackgroup remove 群号
```

示例：

```text
@bot blackqq add 123456789
@bot blackgroup remove 987654321
```

## 其他插件调用

如果某个指令只允许管理员触发，可以导入 `MASTER` 权限：

```python
from nonebot import on_message

from yingice.plugins.ying_permission import MASTER

matcher = on_message(permission=MASTER)
```

也可以直接调用判断函数：

```python
from yingice.plugins.ying_permission import (
    is_black_group,
    is_black_qq,
    is_blocked_event,
    is_master_event,
    is_master_qq,
)
```

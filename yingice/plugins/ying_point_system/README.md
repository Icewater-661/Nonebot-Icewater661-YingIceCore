# ying_point_system

## 插件描述

好感度系统插件，负责查询与修改用户好感度。

好感度数据存储在项目根目录的 `ying_point.csv` 中，列为 `QQ号, 好感度, 最后修改时间戳`。

## 指令说明

```text
@bot 好感
```

功能：

- 查询当前用户好感度。
- 首次查询时创建用户记录，默认好感度为 `100`，最后修改时间戳为 `0`。
- 查询结果会附加 `ying_point_feedback.json` 中匹配好感区间的自定义文案。

## 其他内容

反馈配置文件位于当前插件目录：

```text
ying_point_feedback.json
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

`change_ying_point(user_id, delta)` 会返回统一文案：

```text
好感上升了1，当前好感：101
当前好感：101
好感下降了3，当前好感：98
```

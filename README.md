# Nonebot-Icewater661-YingIceCore

基于 [NoneBot2](https://nonebot.dev/) 与 [OneBot](https://onebot.dev/) V11 的 QQ 机器人项目。

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
      ├─ feed/
      │  ├─ __init__.py
      │  ├─ README.md
      │  └─ feedlist.csv
      ├─ help/
      │  ├─ __init__.py
      │  ├─ README.md
      │  └─ default_help.txt
      ├─ jrcp/
      │  ├─ __init__.py
      │  └─ README.md
      ├─ pat_head/
      │  ├─ __init__.py
      │  └─ README.md
      ├─ ying_permission/
      │  ├─ __init__.py
      │  ├─ README.md
      │  └─ permission_config.json
      └─ ying_point_system/
         ├─ __init__.py
         ├─ README.md
         └─ ying_point_feedback.json
```

## 说明

- `pyproject.toml`：项目依赖、NoneBot 插件目录与适配器配置。
- `ying_point.csv`：好感度数据文件，列为 `QQ号, 好感度, 最后修改时间戳`。
- `yingice/plugins/`：本项目所有本地插件目录。
- 每个插件的描述、指令和调用方法见对应插件目录下的 `README.md`。

## 插件列表

- [feed](yingice/plugins/feed/README.md)：投喂互动插件。
- [help](yingice/plugins/help/README.md)：帮助查询插件。
- [jrcp](yingice/plugins/jrcp/README.md)：群聊今日 CP 插件。
- [pat_head](yingice/plugins/pat_head/README.md)：摸头互动插件。
- [ying_permission](yingice/plugins/ying_permission/README.md)：权限管理插件。
- [ying_point_system](yingice/plugins/ying_point_system/README.md)：好感度系统插件。

## 启动方式

```bash
nb run --reload
```

项目插件目录由 `pyproject.toml` 中的配置加载：

```toml
[tool.nonebot]
plugin_dirs = ["yingice/plugins"]
```

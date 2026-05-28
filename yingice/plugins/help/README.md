# help

## 插件描述

帮助查询插件。用于展示默认帮助文案、当前插件列表，并读取指定插件目录下的 `README.md`。

## 指令说明

```text
@bot help
@bot help 插件名称
@bot 帮助
@bot 帮助 插件名称
```

不填写插件名称时，会发送 `default_help.txt` 中的默认帮助文案和当前插件列表。

填写插件名称时，会读取对应插件 README 中的“插件描述”和“指令说明”两段内容。

## 其他内容

默认帮助文案位于当前插件目录：

```text
default_help.txt
```

插件名称需要与 `yingice/plugins/` 下的目录名一致，例如：

```text
@bot help feed
@bot help jrcp
```

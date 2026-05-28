from __future__ import annotations

import re
from pathlib import Path

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent  # noqa: TC002
from nonebot.plugin import PluginMetadata

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_README_FILE = Path(__file__).resolve().parents[3] / "README.md"
DEFAULT_HELP_FILE = Path(__file__).with_name("default_help.txt")
README_FILE_NAME = "README.md"
COMMAND_PREFIX = "help"
COMMAND_ALIASES = ("help", "帮助")
MARKDOWN_HEADING_PREFIX = "#"
MARKDOWN_LIST_PREFIXES = ("- ", "* ")
MARKDOWN_FENCE_PREFIX = "```"
PLUGIN_LIST_TITLE = "插件列表"
MARKDOWN_LINK_PATTERN = r"\[([^\]]+)\]\([^)]+\)"

__plugin_meta__ = PluginMetadata(
    name="help",
    description="YingIce 帮助查询",
    usage="@bot help [插件名称] / @bot 帮助 [插件名称]",
)

help_matcher = on_message(priority=10, block=False)


def _is_at_bot_message(bot: Bot, event: MessageEvent) -> bool:
    if not event.to_me or not event.original_message:
        return False

    first_segment = event.original_message[0]
    return first_segment.type == "at" and str(first_segment.data.get("qq")) == str(
        bot.self_id
    )


def _read_default_help() -> str:
    if not DEFAULT_HELP_FILE.exists():
        return "可使用 @bot help 插件名称 查询插件帮助。"

    return DEFAULT_HELP_FILE.read_text(encoding="utf-8").strip()


def _get_plugin_readme(plugin_name: str) -> Path | None:
    plugin_dir = PLUGIN_ROOT / plugin_name
    readme_path = plugin_dir / README_FILE_NAME
    if readme_path.exists() and readme_path.is_file():
        return readme_path

    return None


def _extract_section(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    start_index: int | None = None
    section_lines: list[str] = []

    for index, line in enumerate(lines):
        if line.strip() == f"## {title}":
            start_index = index + 1
            break

    if start_index is None:
        return ""

    for line in lines[start_index:]:
        if line.startswith("## "):
            break
        section_lines.append(line)

    return "\n".join(section_lines).strip()


def _strip_markdown_line(line: str) -> str:
    stripped_line = line.strip()
    stripped_line = re.sub(MARKDOWN_LINK_PATTERN, r"\1", stripped_line)
    while stripped_line.startswith(MARKDOWN_HEADING_PREFIX):
        stripped_line = stripped_line[1:].strip()

    for prefix in MARKDOWN_LIST_PREFIXES:
        if stripped_line.startswith(prefix):
            return stripped_line[len(prefix) :].strip()

    return stripped_line


def _clean_markdown_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith(MARKDOWN_FENCE_PREFIX):
            continue

        cleaned_lines.append(_strip_markdown_line(stripped_line))

    return "\n".join(cleaned_lines)


def _read_project_plugin_list() -> str:
    if not PROJECT_README_FILE.exists():
        return "暂无可查询插件。"

    markdown = PROJECT_README_FILE.read_text(encoding="utf-8")
    plugin_list = _extract_section(markdown, PLUGIN_LIST_TITLE)
    if not plugin_list:
        return "暂无可查询插件。"

    return plugin_list


def _build_default_reply() -> str:
    return _clean_markdown_text(
        f"{_read_default_help()}\n当前插件列表：\n{_read_project_plugin_list()}"
    )


def _build_plugin_reply(plugin_name: str) -> str:
    readme_path = _get_plugin_readme(plugin_name)
    if readme_path is None:
        return f"未找到插件帮助：{plugin_name}"

    markdown = readme_path.read_text(encoding="utf-8")
    description = _extract_section(markdown, "插件描述")
    command = _extract_section(markdown, "指令说明")

    reply_parts = [plugin_name]
    if description:
        reply_parts.append(f"插件描述\n{description}")
    if command:
        reply_parts.append(f"指令说明\n{command}")

    if len(reply_parts) == 1:
        reply_parts.append("该插件 README 中暂无插件描述与指令说明。")

    return _clean_markdown_text("\n".join(reply_parts))


def _parse_help_command(text: str) -> str | None:
    for command_alias in COMMAND_ALIASES:
        if text == command_alias:
            return ""
        if text.startswith(f"{command_alias} "):
            return text[len(command_alias) :].strip()

    return None


@help_matcher.handle()
async def handle_help(bot: Bot, event: MessageEvent) -> None:
    if not _is_at_bot_message(bot, event):
        return

    text = event.get_plaintext().strip()
    plugin_name = _parse_help_command(text)
    if plugin_name is None:
        return

    if not plugin_name:
        await help_matcher.finish(_build_default_reply())

    await help_matcher.finish(_build_plugin_reply(plugin_name))

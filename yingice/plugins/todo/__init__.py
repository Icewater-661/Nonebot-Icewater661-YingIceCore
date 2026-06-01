from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from nonebot import get_bots, get_driver, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata

TODO_DATA_FILE = Path(__file__).with_name("todo_data.json")
GROUP_CONFIG_FILE = Path(__file__).with_name("todo_group_config.json")
README_FILE = Path(__file__).with_name("README.md")
COMMAND_PREFIXES = (".todo", "。todo", "!todo", "！todo")
TODO_LIMIT = 5
FOREVER_TYPE = "every"
AFTERDAY_TYPE = "afterday"
NONE_TYPE = "none"
CHECK_INTERVAL_SECONDS = 20
REMIND_HOUR = 0
REMIND_MINUTE_MOD = 60
MAX_RANDOM_SECOND = 59
DATE_PATTERN = re.compile(
    r"(?:(?P<year>\d{4})[年/-])?(?P<month>\d{1,2})[月/-](?P<day>\d{1,2})日?$"
)
DATE_SUFFIX_PATTERN = re.compile(
    r"\s+date\s*\+?\s*(?P<date>\S+)\s*$",
    re.IGNORECASE,
)
AFTERDAY_SUFFIX_PATTERN = re.compile(
    r"\s+afterday\s+(?P<days>\d+)\s*$",
    re.IGNORECASE,
)
EVERY_SUFFIX_PATTERN = re.compile(
    r"\s+every\s+(?P<days>\d+)\s*$",
    re.IGNORECASE,
)

__plugin_meta__ = PluginMetadata(
    name="todo",
    description="YingIce todo 提醒",
    usage=".todo add/list/delete/open/close",
)

todo = on_message(priority=10, block=False)
_reminder_state: dict[str, asyncio.Task | None] = {"task": None}


def _ensure_json_file(path: Path, default_value: dict[str, Any]) -> None:
    if path.exists():
        return

    with path.open("w", encoding="utf-8") as file:
        json.dump(default_value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _read_json(path: Path, default_value: dict[str, Any]) -> dict[str, Any]:
    _ensure_json_file(path, default_value)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return default_value.copy()

    return data if isinstance(data, dict) else default_value.copy()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _read_todo_data() -> dict[str, Any]:
    return _read_json(TODO_DATA_FILE, {})


def _write_todo_data(data: dict[str, Any]) -> None:
    _write_json(TODO_DATA_FILE, data)


def _read_group_config() -> dict[str, Any]:
    return _read_json(GROUP_CONFIG_FILE, {})


def _write_group_config(data: dict[str, Any]) -> None:
    _write_json(GROUP_CONFIG_FILE, data)


def _context_key(event: MessageEvent) -> str:
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        return f"group:{group_id}"

    return f"private:{event.get_user_id()}"


def _get_context_block(data: dict[str, Any], event: MessageEvent) -> dict[str, Any]:
    key = _context_key(event)
    if key in data and isinstance(data[key], dict):
        return data[key]

    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        data[key] = {
            "context_type": "group",
            "group_id": str(group_id),
            "todos": [],
        }
    else:
        data[key] = {
            "context_type": "private",
            "user_id": event.get_user_id(),
            "todos": [],
        }

    return data[key]


def _parse_command(text: str) -> str | None:
    stripped_text = text.strip()
    for prefix in COMMAND_PREFIXES:
        if stripped_text == prefix:
            return ""
        if stripped_text.startswith(f"{prefix} "):
            return stripped_text[len(prefix) :].strip()

    return None


def _today() -> date:
    local_time = time.localtime()
    return date(local_time.tm_year, local_time.tm_mon, local_time.tm_mday)


def _parse_date(value: str) -> date | None:
    match = DATE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None

    today = _today()
    year_text = match.group("year")
    year = int(year_text) if year_text else today.year
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        result = date(year, month, day)
    except ValueError:
        return None

    if year_text is None and result < today:
        try:
            result = date(today.year + 1, month, day)
        except ValueError:
            return None

    return result


def _date_text(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _is_future_date(value: str | None) -> bool:
    if value is None:
        return True

    try:
        return date.fromisoformat(value) > _today()
    except ValueError:
        return False


def _parse_add_content(raw_content: str) -> tuple[str, str, str | None, int | None]:
    suffix_patterns = (
        (EVERY_SUFFIX_PATTERN, FOREVER_TYPE),
        (AFTERDAY_SUFFIX_PATTERN, AFTERDAY_TYPE),
        (DATE_SUFFIX_PATTERN, AFTERDAY_TYPE),
    )
    for pattern, remind_type in suffix_patterns:
        match = pattern.search(raw_content)
        if match is None:
            continue

        content = raw_content[: match.start()].strip()
        if remind_type == FOREVER_TYPE:
            days = int(match.group("days"))
            next_date = (_today() + timedelta(days=days)).isoformat()
            return content, remind_type, next_date, days
        if "days" in match.groupdict():
            days = int(match.group("days"))
            next_date = (_today() + timedelta(days=days)).isoformat()
            return content, remind_type, next_date, None

        parsed_date = _parse_date(match.group("date"))
        if parsed_date is None:
            return content, remind_type, None, None
        return content, remind_type, parsed_date.isoformat(), None

    return raw_content.strip(), NONE_TYPE, None, None


def _count_user_todos(block: dict[str, Any], user_id: str) -> int:
    return sum(1 for item in block.get("todos", []) if item.get("user_id") == user_id)


def _count_user_every_todos(data: dict[str, Any], user_id: str) -> int:
    count = 0
    for block in data.values():
        if not isinstance(block, dict):
            continue
        for item in block.get("todos", []):
            if (
                item.get("user_id") == user_id
                and item.get("remind_type") == FOREVER_TYPE
            ):
                count += 1

    return count


def _next_slot(data: dict[str, Any], context_key: str, remind_date: str | None) -> int:
    if remind_date is None:
        return 0

    max_slot = -1
    for item in data.get(context_key, {}).get("todos", []):
        if item.get("next_remind_date") == remind_date:
            max_slot = max(max_slot, int(item.get("minute_slot", 0)))

    return max_slot + 1


def _new_todo(  # noqa: PLR0913
    *,
    event: MessageEvent,
    content: str,
    remind_type: str,
    next_remind_date: str | None,
    interval_days: int | None,
    minute_slot: int,
) -> dict[str, Any]:
    return {
        "user_id": event.get_user_id(),
        "content": content,
        "remind_type": remind_type,
        "next_remind_date": next_remind_date,
        "interval_days": interval_days,
        "minute_slot": minute_slot,
        "remind_second": random.randint(0, MAX_RANDOM_SECOND),
        "created_at": int(time.time()),
    }


def _is_group_enabled(group_id: str | int) -> bool:
    config = _read_group_config()
    return bool(config.get(str(group_id), True))


def _set_group_enabled(group_id: str | int, *, enabled: bool) -> None:
    config = _read_group_config()
    config[str(group_id)] = enabled
    _write_group_config(config)


def _is_group_admin(event: MessageEvent) -> bool:
    role = getattr(getattr(event, "sender", None), "role", "")
    return role in {"owner", "admin"}


def _is_bot_admin(event: MessageEvent) -> bool:
    from yingice.plugins.ying_permission import is_master_event

    return is_master_event(event)


def _is_todo_admin(event: MessageEvent) -> bool:
    return _is_bot_admin(event) or _is_group_admin(event)


def _format_todo_item(index: int, item: dict[str, Any]) -> str:
    text = f"{index}.{item.get('content', '')}"
    next_date = item.get("next_remind_date")
    if not next_date:
        return text

    try:
        remind_date = date.fromisoformat(str(next_date))
    except ValueError:
        return text

    if item.get("remind_type") == FOREVER_TYPE:
        return (
            f"{text}【提醒：{_date_text(remind_date)}，"
            f"每{item.get('interval_days')}天】"
        )

    return f"{text}【提醒：{_date_text(remind_date)}】"


def _build_user_todo_list(block: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
    return [item for item in block.get("todos", []) if item.get("user_id") == user_id]


def _read_help_text() -> str:
    if not README_FILE.exists():
        return "todo 插件暂无帮助。"

    markdown = README_FILE.read_text(encoding="utf-8")
    lines: list[str] = []
    in_allowed_section = False
    for line in markdown.splitlines():
        stripped_line = line.strip()
        if stripped_line in {"## 插件描述", "## 指令说明"}:
            in_allowed_section = True
        elif stripped_line.startswith("## "):
            in_allowed_section = False
        if not in_allowed_section:
            continue
        if not stripped_line or stripped_line.startswith("```"):
            continue
        lines.append(stripped_line.lstrip("#-* "))

    return "\n".join(lines)


async def _send_reminder(
    bot: Bot,
    block: dict[str, Any],
    items: list[dict[str, Any]],
) -> None:
    context_type = block.get("context_type")
    first_date = date.fromisoformat(str(items[0]["next_remind_date"]))
    if context_type == "group":
        group_id = str(block.get("group_id"))
        message = Message(f"{_date_text(first_date)}在群聊（{group_id}）的todo列表：")
        for item in items:
            message += "\n"
            message += MessageSegment.at(item["user_id"])
            message += f" {item.get('content', '')}"
        await bot.send_group_msg(group_id=int(group_id), message=message)
    else:
        user_id = str(block.get("user_id"))
        lines = [f"{_date_text(first_date)}的todo列表："]
        lines.extend(str(item.get("content", "")) for item in items)
        await bot.send_private_msg(user_id=int(user_id), message="\n".join(lines))


def _reschedule_or_remove(
    block: dict[str, Any],
    due_items: list[dict[str, Any]],
) -> None:
    todos = block.get("todos", [])
    for item in due_items:
        if item.get("remind_type") == FOREVER_TYPE:
            interval_days = int(item.get("interval_days") or 1)
            next_date = date.fromisoformat(str(item["next_remind_date"])) + timedelta(
                days=interval_days
            )
            item["next_remind_date"] = next_date.isoformat()
            item["remind_second"] = random.randint(0, MAX_RANDOM_SECOND)
        elif item in todos:
            todos.remove(item)


async def _check_reminders_once() -> None:  # noqa: C901
    bots = get_bots()
    if not bots:
        return

    bot = next(iter(bots.values()))
    data = _read_todo_data()
    now = time.localtime()
    today_text = _today().isoformat()
    changed = False

    for block in data.values():
        if not isinstance(block, dict):
            continue
        if block.get("context_type") == "group" and not _is_group_enabled(
            str(block.get("group_id"))
        ):
            continue

        due_items = []
        for item in block.get("todos", []):
            if item.get("next_remind_date") != today_text:
                continue
            minute_slot = int(item.get("minute_slot", 0)) % REMIND_MINUTE_MOD
            remind_second = int(item.get("remind_second", 0))
            if (now.tm_hour, now.tm_min, now.tm_sec) >= (
                REMIND_HOUR,
                minute_slot,
                remind_second,
            ):
                due_items.append(item)

        if not due_items:
            continue

        try:
            await _send_reminder(bot, block, due_items)
        except ActionFailed:
            continue

        _reschedule_or_remove(block, due_items)
        changed = True

    if changed:
        _write_todo_data(data)


async def _reminder_loop() -> None:
    while True:
        await _check_reminders_once()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


@get_driver().on_startup
async def _start_reminder_loop() -> None:
    task = _reminder_state["task"]
    if task is None or task.done():
        _reminder_state["task"] = asyncio.create_task(_reminder_loop())


@todo.handle()
async def handle_todo(event: MessageEvent) -> None:  # noqa: C901, PLR0912, PLR0915
    command = _parse_command(event.get_plaintext())
    if command is None:
        return
    if not command:
        await todo.finish(_read_help_text())

    action, _, argument = command.partition(" ")
    action = action.lower()
    data = _read_todo_data()
    block = _get_context_block(data, event)
    user_id = event.get_user_id()

    if action in {"open", "close"}:
        group_id = getattr(event, "group_id", None)
        if group_id is None:
            await todo.finish("todo 提醒开关仅支持群聊。")
        if not _is_todo_admin(event):
            await todo.finish("只有群管理员或 bot 管理员可以切换 todo 提醒。")
        _set_group_enabled(group_id, enabled=action == "open")
        await todo.finish(f"todo 群聊提醒已{'开启' if action == 'open' else '关闭'}。")

    if action == "list":
        user_todos = _build_user_todo_list(block, user_id)
        if not user_todos:
            await todo.finish("你的任务列表为空。")
        message = Message()
        if getattr(event, "group_id", None) is not None:
            message += MessageSegment.at(user_id)
            message += " 的任务列表包含："
        else:
            message += f"{user_id} 的任务列表包含："
        for index, item in enumerate(user_todos, start=1):
            message += f"\n{_format_todo_item(index, item)}"
        await todo.finish(message)

    if action in {"delete", "remove"}:
        if not argument.strip().isdigit():
            await todo.finish("请提供要删除的 todo 编号。")
        index = int(argument.strip())
        user_todos = _build_user_todo_list(block, user_id)
        if index < 1 or index > len(user_todos):
            await todo.finish("没有找到这个编号的 todo。")
        removed_todo = user_todos[index - 1]
        block["todos"].remove(removed_todo)
        _write_todo_data(data)
        removed_content = removed_todo.get("content", "")
        await todo.finish(f"已删除第 {index} 项 todo：{removed_content}")

    if action != "add":
        return

    content, remind_type, next_date, interval_days = _parse_add_content(argument)
    if not content:
        await todo.finish("todo 内容不能为空。")
    if _count_user_todos(block, user_id) >= TODO_LIMIT:
        await todo.finish(f"每个人最多包含 {TODO_LIMIT} 条 todo。")
    if remind_type in {AFTERDAY_TYPE, FOREVER_TYPE} and next_date is None:
        await todo.finish("提醒日期解析失败，请检查 date/afterday/every 后缀。")
    if remind_type in {AFTERDAY_TYPE, FOREVER_TYPE} and not _is_future_date(next_date):
        await todo.finish("提醒日期必须晚于今天。")
    if remind_type == FOREVER_TYPE and interval_days is not None and interval_days <= 0:
        await todo.finish("every 的日期数必须大于 0。")
    if (
        remind_type == FOREVER_TYPE
        and not _is_bot_admin(event)
        and _count_user_every_todos(data, user_id) >= 1
    ):
        await todo.finish("非 bot 管理员每人最多创建一个循环 todo。")

    key = _context_key(event)
    minute_slot = _next_slot(data, key, next_date)
    created_todo = _new_todo(
        event=event,
        content=content,
        remind_type=remind_type,
        next_remind_date=next_date,
        interval_days=interval_days,
        minute_slot=minute_slot,
    )
    block["todos"].append(created_todo)
    _write_todo_data(data)
    await todo.finish(f"todo 已添加：{created_todo.get('content', '')}")

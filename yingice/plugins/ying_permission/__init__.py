from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nonebot import on_message
from nonebot.adapters import Event  # noqa: TC002
from nonebot.adapters.onebot.v11 import Bot, MessageEvent  # noqa: TC002
from nonebot.message import IgnoredException, event_preprocessor
from nonebot.permission import Permission
from nonebot.plugin import PluginMetadata

CONFIG_FILE = Path(__file__).with_name("permission_config.json")
COMMAND_PARTS_COUNT = 3
DEFAULT_CONFIG = {
    "masterQQ": [],
    "blackQQ": [],
    "blackGroup": [],
}

__plugin_meta__ = PluginMetadata(
    name="ying permission",
    description="YingIce 权限管理",
    usage="通过 permission_config.json 配置 masterQQ、blackQQ、blackGroup",
)


def _ensure_config_file() -> None:
    if CONFIG_FILE.exists():
        return

    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(DEFAULT_CONFIG, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _normalize_id_list(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (str, int)):
        return {str(value)}
    if isinstance(value, list):
        return {str(item) for item in value if isinstance(item, (str, int))}

    return set()


def get_permission_config() -> dict[str, set[str]]:
    _ensure_config_file()
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            raw_config = json.load(file)
    except (OSError, json.JSONDecodeError):
        raw_config = {}

    if not isinstance(raw_config, dict):
        raw_config = {}

    return {
        "masterQQ": _normalize_id_list(raw_config.get("masterQQ")),
        "blackQQ": _normalize_id_list(raw_config.get("blackQQ")),
        "blackGroup": _normalize_id_list(raw_config.get("blackGroup")),
    }


def is_master_qq(user_id: str | int) -> bool:
    config = get_permission_config()
    return str(user_id) in config["masterQQ"]


def is_black_qq(user_id: str | int) -> bool:
    config = get_permission_config()
    return str(user_id) in config["blackQQ"]


def is_black_group(group_id: str | int) -> bool:
    config = get_permission_config()
    return str(group_id) in config["blackGroup"]


def is_master_event(event: Event) -> bool:
    try:
        user_id = event.get_user_id()
    except ValueError:
        return False

    return is_master_qq(user_id)


def is_blocked_event(event: Event) -> bool:
    try:
        user_id = event.get_user_id()
    except ValueError:
        user_id = ""

    group_id = getattr(event, "group_id", None)
    return bool(user_id and is_black_qq(user_id)) or (
        group_id is not None and is_black_group(group_id)
    )


async def _master_permission_checker(event: Event) -> bool:
    return is_master_event(event)


MASTER = Permission(_master_permission_checker)
permission_manager = on_message(permission=MASTER, priority=5, block=False)


@event_preprocessor
async def block_blacklisted_event(event: Event) -> None:
    if is_blocked_event(event):
        raise IgnoredException("Blocked")


def _write_permission_config(config: dict[str, set[str]]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "masterQQ": sorted(config["masterQQ"]),
        "blackQQ": sorted(config["blackQQ"]),
        "blackGroup": sorted(config["blackGroup"]),
    }
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _is_at_bot_message(bot: Bot, event: MessageEvent) -> bool:
    if not event.to_me or not event.original_message:
        return False

    first_segment = event.original_message[0]
    return first_segment.type == "at" and str(first_segment.data.get("qq")) == str(
        bot.self_id
    )


def _parse_permission_command(text: str) -> tuple[str, str, str] | None:
    parts = text.strip().split()
    if len(parts) != COMMAND_PARTS_COUNT:
        return None

    target, action, target_id = parts
    if target not in {"blackqq", "blackgroup"}:
        return None
    if action not in {"add", "remove"}:
        return None
    if not target_id.isdigit():
        return None

    return target, action, target_id


def _update_blacklist(target: str, action: str, target_id: str) -> str:
    config_key = "blackQQ" if target == "blackqq" else "blackGroup"
    target_name = "QQ" if target == "blackqq" else "群"
    config = get_permission_config()

    if action == "add":
        if target_id in config[config_key]:
            return f"{target_name} {target_id} 已在黑名单中"
        config[config_key].add(target_id)
        _write_permission_config(config)
        return f"已添加黑名单{target_name}：{target_id}"

    if target_id not in config[config_key]:
        return f"{target_name} {target_id} 不在黑名单中"
    config[config_key].remove(target_id)
    _write_permission_config(config)
    return f"已移除黑名单{target_name}：{target_id}"


@permission_manager.handle()
async def handle_permission_manager(bot: Bot, event: MessageEvent) -> None:
    if not _is_at_bot_message(bot, event):
        return

    command = _parse_permission_command(event.get_plaintext())
    if command is None:
        return

    target, action, target_id = command
    await permission_manager.finish(_update_blacklist(target, action, target_id))

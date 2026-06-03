from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nonebot import get_bots, get_driver, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata

BILI_CONFIG_FILE = Path(__file__).with_name("bili_ying_config.json")
BILI_SUBSCRIPTION_FILE = Path(__file__).with_name("bili_ying_subscriptions.json")
BILI_API_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
BILI_MASTER_API_URL = "https://api.live.bilibili.com/live_user/v1/Master/info"
BILI_VIDEO_API_URL = "https://api.bilibili.com/x/web-interface/view"
CHECK_INTERVAL_SECONDS = 120
MIN_CHECK_INTERVAL_SECONDS = 60
CHECK_BATCH_SIZE = 10
REQUEST_TIMEOUT_SECONDS = 10
API_RESET_NOTICE_COOLDOWN_SECONDS = 3600
API_ERROR = "api error"
ROOM_DATA_ERROR = "room data error"
COMMAND_PREFIX = "bili"
COMMAND_PARTS_MIN = 2
LIVE_STATUS_OFFLINE = 0
LIVE_STATUS_LIVE = 1
LIVE_STATUS_ROUND = 2
BV_PATTERN = re.compile(r"(?i)\bBV[0-9A-Za-z]{10}\b")
URL_PATTERN = re.compile(r"https?://[^\s\]\)）>]+")
DEFAULT_CONFIG = {
    "enabled": True,
    "cookie": "",
    "check_interval_seconds": CHECK_INTERVAL_SECONDS,
    "check_batch_size": CHECK_BATCH_SIZE,
    "check_cursor": 0,
    "notify_admin_on_api_reset": True,
    "last_api_reset_notice_at": 0,
}

__plugin_meta__ = PluginMetadata(
    name="bili-ying",
    description="Bilibili 直播订阅提醒",
    usage="@bot bili add/remove/delete/list",
)

bili_ying = on_message(priority=10, block=False)
bili_video = on_message(priority=11, block=False)
_monitor_state: dict[str, asyncio.Task | None] = {"task": None}


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


def _read_config() -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update(_read_json(BILI_CONFIG_FILE, DEFAULT_CONFIG))
    return config


def _read_subscriptions() -> dict[str, Any]:
    return _read_json(BILI_SUBSCRIPTION_FILE, {})


def _write_subscriptions(data: dict[str, Any]) -> None:
    _write_json(BILI_SUBSCRIPTION_FILE, data)


def _write_config(data: dict[str, Any]) -> None:
    _write_json(BILI_CONFIG_FILE, data)


def _is_at_bot_message(bot: Bot, event: MessageEvent) -> bool:
    if not event.to_me or not event.original_message:
        return False

    first_segment = event.original_message[0]
    return first_segment.type == "at" and str(first_segment.data.get("qq")) == str(
        bot.self_id
    )


def _is_group_admin(event: MessageEvent) -> bool:
    role = getattr(getattr(event, "sender", None), "role", "")
    return role in {"owner", "admin"}


def _is_bili_admin(event: MessageEvent) -> bool:
    from yingice.plugins.ying_permission import is_master_event

    return is_master_event(event) or _is_group_admin(event)


def _parse_command(text: str) -> tuple[str, str | None] | None:
    parts = text.strip().split(maxsplit=2)
    if len(parts) < COMMAND_PARTS_MIN or parts[0].lower() != COMMAND_PREFIX:
        return None

    action = parts[1].lower()
    argument = parts[2].strip() if len(parts) > COMMAND_PARTS_MIN else None
    return action, argument


def _group_block(data: dict[str, Any], group_id: int | str) -> dict[str, Any]:
    key = str(group_id)
    if key not in data or not isinstance(data[key], dict):
        data[key] = {"rooms": {}}
    if "rooms" not in data[key] or not isinstance(data[key]["rooms"], dict):
        data[key]["rooms"] = {}

    return data[key]


def _status_text(status: int) -> str:
    if status == LIVE_STATUS_LIVE:
        return "直播中"
    if status == LIVE_STATUS_ROUND:
        return "轮播中"
    return "未开播"


def _room_url(room_id: str | int) -> str:
    return f"https://live.bilibili.com/{room_id}"


def _build_request(
    url: str,
    query_data: dict[str, str],
    config: dict[str, Any],
) -> Request:
    query = urlencode(query_data)
    request = Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0 YingIceCore bili-ying",
            "Referer": "https://live.bilibili.com/",
        },
    )
    cookie = str(config.get("cookie", "")).strip()
    if cookie:
        request.add_header("Cookie", cookie)

    return request


def _read_bili_payload(request: Request) -> dict[str, Any]:
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if int(payload.get("code", -1)) != 0:
        message = payload.get("message") or payload.get("msg") or "unknown error"
        raise ValueError(str(message))

    return payload


def _fetch_room_info_sync(room_id: str, config: dict[str, Any]) -> dict[str, Any]:
    request = _build_request(BILI_API_URL, {"room_id": room_id}, config)
    payload = _read_bili_payload(request)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise TypeError(ROOM_DATA_ERROR)

    _fill_anchor_name(data, config)
    return data


def _fill_anchor_name(room_info: dict[str, Any], config: dict[str, Any]) -> None:
    uid = str(room_info.get("uid") or "")
    if not uid:
        return

    try:
        request = _build_request(BILI_MASTER_API_URL, {"uid": uid}, config)
        payload = _read_bili_payload(request)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return

    data = payload.get("data")
    if not isinstance(data, dict):
        return

    info = data.get("info")
    if isinstance(info, dict) and info.get("uname"):
        room_info["uname"] = info["uname"]


async def _fetch_room_info(room_id: str, config: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_room_info_sync, room_id, config)


def _is_bili_url(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


def _clean_url(url: str) -> str:
    return url.rstrip(".,，。!！?？;；:：")


def _resolve_url_sync(url: str, config: dict[str, Any]) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 YingIceCore bili-ying",
            "Referer": "https://www.bilibili.com/",
        },
    )
    cookie = str(config.get("cookie", "")).strip()
    if cookie:
        request.add_header("Cookie", cookie)

    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.geturl()


async def _resolve_url(url: str, config: dict[str, Any]) -> str:
    return await asyncio.to_thread(_resolve_url_sync, url, config)


async def _extract_bvid(text: str, config: dict[str, Any]) -> str | None:
    matched = BV_PATTERN.search(text)
    if matched:
        return matched.group(0)

    for raw_url in URL_PATTERN.findall(text):
        url = _clean_url(raw_url)
        if not _is_bili_url(url):
            continue
        matched = BV_PATTERN.search(url)
        if matched:
            return matched.group(0)
        if "b23.tv" not in url:
            continue
        try:
            resolved_url = await _resolve_url(url, config)
        except (HTTPError, URLError, TimeoutError, ValueError):
            continue
        matched = BV_PATTERN.search(resolved_url)
        if matched:
            return matched.group(0)

    return None


def _fetch_video_info_sync(bvid: str, config: dict[str, Any]) -> dict[str, Any]:
    request = _build_request(BILI_VIDEO_API_URL, {"bvid": bvid}, config)
    payload = _read_bili_payload(request)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise TypeError(API_ERROR)

    return data


async def _fetch_video_info(bvid: str, config: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_video_info_sync, bvid, config)


def _thumbnail_cover_url(cover_url: str) -> str:
    url = cover_url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    if url.startswith("http://"):
        url = f"https://{url.removeprefix('http://')}"

    url = url.split("?", maxsplit=1)[0]
    return f"{url}@320w_180h_1c.jpg"


def _video_message(video_info: dict[str, Any], fallback_bvid: str) -> Message:
    owner = video_info.get("owner")
    title = str(video_info.get("title") or "未知标题")
    bvid = str(video_info.get("bvid") or fallback_bvid)
    cover_url = _thumbnail_cover_url(str(video_info.get("pic") or ""))
    up_name = "未知 UP 主"
    if isinstance(owner, dict) and owner.get("name"):
        up_name = str(owner["name"])

    message = Message(f"视频名称：{title}\nBV号：{bvid}\nUP主：{up_name}")
    if cover_url:
        message += MessageSegment.text("\n")
        message += MessageSegment.image(file=cover_url, cache=False)

    return message


def _is_api_reset_error(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return error.code in {403, 412, 429}
    if isinstance(error, URLError):
        return "10054" in str(error.reason) or "ConnectionReset" in str(error.reason)

    return False


async def _notify_api_reset(bot: Bot, error: BaseException, room_id: str) -> None:
    config = _read_config()
    if not bool(config.get("notify_admin_on_api_reset", True)):
        return

    now = int(time.time())
    last_notice_at = int(config.get("last_api_reset_notice_at", 0))
    if now - last_notice_at < API_RESET_NOTICE_COOLDOWN_SECONDS:
        return

    from yingice.plugins.ying_permission import get_permission_config

    admin_ids = sorted(get_permission_config()["masterQQ"])
    if not admin_ids:
        return

    message = (
        "bili-ying 检测到 Bilibili API 访问疑似被风控/重置。\n"
        f"直播间：{room_id}\n"
        f"错误：{error}\n"
        "可尝试在 bili_ying_config.json 的 cookie 字段补入可用登录 Cookie。"
    )
    for admin_id in admin_ids:
        with contextlib.suppress(ActionFailed):
            await bot.send_private_msg(user_id=int(admin_id), message=message)

    config["last_api_reset_notice_at"] = now
    _write_config(config)


def _room_entry(room_id: str, room_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "room_id": str(room_info.get("room_id") or room_id),
        "short_id": str(room_info.get("short_id") or ""),
        "title": str(room_info.get("title") or "未命名直播间"),
        "uname": str(room_info.get("uname") or "未知主播"),
        "uid": str(room_info.get("uid") or ""),
        "status": int(room_info.get("live_status", LIVE_STATUS_OFFLINE)),
        "updated_at": int(time.time()),
    }


def _room_display(entry: dict[str, Any]) -> str:
    room_id = str(entry.get("room_id") or "")
    title = str(entry.get("title") or "未命名直播间")
    status = _status_text(int(entry.get("status", LIVE_STATUS_OFFLINE)))
    return f"{room_id}：{title}（{status}）"


def _transition_message(entry: dict[str, Any], old_status: int, new_status: int) -> str:
    room_id = str(entry.get("room_id") or "")
    title = str(entry.get("title") or "未命名直播间")
    uname = str(entry.get("uname") or "未知主播")
    if old_status != LIVE_STATUS_LIVE and new_status == LIVE_STATUS_LIVE:
        return (
            f"{uname} 开播啦！\n{title}\n"
            f"房间号：{room_id}\n{_room_url(room_id)}"
        )
    if old_status == LIVE_STATUS_LIVE and new_status != LIVE_STATUS_LIVE:
        return (
            f"{uname} 下播啦！\n{title}\n"
            f"房间号：{room_id}\n{_room_url(room_id)}"
        )

    return ""


def _build_room_targets(
    subscriptions: dict[str, Any],
) -> list[tuple[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]]:
    targets: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = {}
    for group_id, block in subscriptions.items():
        if not isinstance(block, dict):
            continue
        rooms = block.get("rooms", {})
        if not isinstance(rooms, dict):
            continue
        for room_id, entry in rooms.items():
            if not isinstance(entry, dict):
                continue
            targets.setdefault(str(room_id), []).append((str(group_id), rooms, entry))

    return sorted(targets.items(), key=lambda item: item[0])


def _select_room_batch(
    targets: list[tuple[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]],
    config: dict[str, Any],
) -> tuple[list[tuple[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]], int]:
    if not targets:
        return [], 0

    batch_size = max(int(config.get("check_batch_size", CHECK_BATCH_SIZE)), 1)
    cursor = int(config.get("check_cursor", 0)) % len(targets)
    batch = [targets[(cursor + offset) % len(targets)] for offset in range(batch_size)]
    next_cursor = (cursor + min(batch_size, len(targets))) % len(targets)
    return batch[: len(targets)], next_cursor


async def _check_once() -> None:  # noqa: C901
    config = _read_config()
    if not bool(config.get("enabled", True)):
        return

    bots = get_bots()
    if not bots:
        return

    bot = next(iter(bots.values()))
    subscriptions = _read_subscriptions()
    targets = _build_room_targets(subscriptions)
    batch, next_cursor = _select_room_batch(targets, config)
    config["check_cursor"] = next_cursor
    _write_config(config)

    changed = False
    for room_id, group_entries in batch:
        try:
            room_info = await _fetch_room_info(str(room_id), config)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            if _is_api_reset_error(exc):
                await _notify_api_reset(bot, exc, str(room_id))
            continue

        new_entry = _room_entry(str(room_id), room_info)
        new_status = int(new_entry["status"])
        for group_id, rooms, entry in group_entries:
            old_status = int(entry.get("status", LIVE_STATUS_OFFLINE))
            message = _transition_message(new_entry, old_status, new_status)
            rooms[str(new_entry["room_id"])] = new_entry
            if str(new_entry["room_id"]) != str(room_id):
                rooms.pop(str(room_id), None)
            changed = True
            if not message:
                continue
            try:
                await bot.send_group_msg(group_id=int(group_id), message=message)
            except ActionFailed:
                continue

    if changed:
        _write_subscriptions(subscriptions)


async def _monitor_loop() -> None:
    while True:
        config = _read_config()
        interval = int(config.get("check_interval_seconds", CHECK_INTERVAL_SECONDS))
        await _check_once()
        await asyncio.sleep(max(interval, MIN_CHECK_INTERVAL_SECONDS))


@get_driver().on_startup
async def _start_monitor_loop() -> None:
    task = _monitor_state["task"]
    if task is None or task.done():
        _monitor_state["task"] = asyncio.create_task(_monitor_loop())


async def _add_room(group_id: int, room_id: str) -> str:
    config = _read_config()
    room_info = await _fetch_room_info(room_id, config)
    entry = _room_entry(room_id, room_info)
    data = _read_subscriptions()
    block = _group_block(data, group_id)
    block["rooms"][str(entry["room_id"])] = entry
    _write_subscriptions(data)
    return f"已添加直播订阅：{_room_display(entry)}"


def _remove_room(group_id: int, room_id: str) -> str:
    data = _read_subscriptions()
    block = _group_block(data, group_id)
    removed = block["rooms"].pop(str(room_id), None)
    if removed is None:
        return f"当前群未订阅直播间：{room_id}"

    _write_subscriptions(data)
    return f"已删除直播订阅：{_room_display(removed)}"


def _list_rooms(group_id: int) -> str:
    data = _read_subscriptions()
    block = _group_block(data, group_id)
    rooms = block["rooms"]
    if not rooms:
        return "当前群暂无 Bilibili 直播订阅。"

    lines = ["当前群 Bilibili 直播订阅："]
    lines.extend(_room_display(entry) for entry in rooms.values())
    return "\n".join(lines)


@bili_video.handle()
async def handle_bili_video(bot: Bot, event: GroupMessageEvent) -> None:
    config = _read_config()
    bvid = await _extract_bvid(str(event.message), config)
    if not bvid:
        return

    try:
        video_info = await _fetch_video_info(bvid, config)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        if _is_api_reset_error(exc):
            await _notify_api_reset(bot, exc, bvid)
        return

    await bili_video.finish(_video_message(video_info, bvid))


@bili_ying.handle()
async def handle_bili_ying(bot: Bot, event: GroupMessageEvent) -> None:
    if not _is_at_bot_message(bot, event):
        return
    if not _is_bili_admin(event):
        return

    command = _parse_command(event.get_plaintext())
    if command is None:
        return

    action, argument = command
    if action == "list":
        await bili_ying.finish(_list_rooms(event.group_id))
    if action == "add":
        if not argument or not argument.isdigit():
            await bili_ying.finish("请提供正确的直播间号。")
        try:
            await bili_ying.finish(await _add_room(event.group_id, argument))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            await bili_ying.finish(f"直播间信息获取失败：{exc}")
    if action in {"remove", "delete"}:
        if not argument or not argument.isdigit():
            await bili_ying.finish("请提供正确的直播间号。")
        await bili_ying.finish(_remove_room(event.group_id, argument))

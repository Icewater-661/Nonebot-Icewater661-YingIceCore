from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent  # noqa: TC002
from nonebot.plugin import PluginMetadata

DEFAULT_FAVORABILITY = 100
MIN_CSV_COLUMNS = 3
DATA_FILE = Path(__file__).resolve().parents[3] / "ying_point.csv"
FEEDBACK_FILE = Path(__file__).with_name("ying_point_feedback.json")
DEFAULT_FEEDBACK = [
    {
        "min": None,
        "max": 100,
        "feedback": "她好像还在观察你。",
    },
    {
        "min": 100,
        "max": 200,
        "feedback": "她对你的态度还算平稳。",
    },
    {
        "min": 200,
        "max": None,
        "feedback": "她看起来很信任你。",
    },
]

__plugin_meta__ = PluginMetadata(
    name="ying point system",
    description="YingIce 好感度系统",
    usage="发送 好感 查询当前好感度",
)

_file_lock = Lock()
favorability = on_message(priority=10, block=False)


def _read_favorability() -> dict[str, tuple[int, int]]:
    if not DATA_FILE.exists():
        return {}

    records: dict[str, tuple[int, int]] = {}
    with DATA_FILE.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) < MIN_CSV_COLUMNS:
                continue

            user_id = row[0].strip()
            if not user_id:
                continue

            try:
                records[user_id] = (int(row[1]), int(row[2]))
            except ValueError:
                continue

    return records


def _write_favorability(records: dict[str, tuple[int, int]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        for user_id, (value, updated_at) in records.items():
            writer.writerow([user_id, value, updated_at])


def _ensure_feedback_file() -> None:
    if FEEDBACK_FILE.exists():
        return

    with FEEDBACK_FILE.open("w", encoding="utf-8") as file:
        json.dump(DEFAULT_FEEDBACK, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _read_feedback() -> list[dict[str, Any]]:
    _ensure_feedback_file()
    try:
        with FEEDBACK_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict)]


def _match_feedback(value: int) -> str:
    for item in _read_feedback():
        min_value = item.get("min")
        max_value = item.get("max")
        feedback = item.get("feedback")

        if not isinstance(feedback, str):
            continue
        if min_value is not None and (
            not isinstance(min_value, int) or value < min_value
        ):
            continue
        if max_value is not None and (
            not isinstance(max_value, int) or value >= max_value
        ):
            continue

        return feedback

    return ""


def _is_before_today(timestamp: int, now: int) -> bool:
    local_time = time.localtime(now)
    today_start = int(
        time.mktime(
            (
                local_time.tm_year,
                local_time.tm_mon,
                local_time.tm_mday,
                0,
                0,
                0,
                local_time.tm_wday,
                local_time.tm_yday,
                local_time.tm_isdst,
            )
        )
    )
    return timestamp < today_start


def _ensure_favorability(
    records: dict[str, tuple[int, int]],
    user_id: str,
    updated_at: int,
) -> bool:
    if user_id in records:
        return False

    records[user_id] = (DEFAULT_FAVORABILITY, updated_at)
    return True


def get_ying_point(user_id: str | int) -> int:
    qq_id = str(user_id)

    with _file_lock:
        records = _read_favorability()
        created = _ensure_favorability(records, qq_id, 0)
        if created:
            _write_favorability(records)

        return records[qq_id][0]


def change_ying_point_with_status(user_id: str | int, delta: int) -> tuple[int, int]:
    qq_id = str(user_id)
    now = int(time.time())

    with _file_lock:
        records = _read_favorability()
        created = _ensure_favorability(records, qq_id, 0)
        value, updated_at = records[qq_id]

        should_update = delta < 0 or (
            delta > 0 and _is_before_today(updated_at, now)
        )
        actual_delta = 0
        if should_update:
            records[qq_id] = (value + delta, now)
            actual_delta = delta

        if created or should_update:
            _write_favorability(records)

        return records[qq_id][0], actual_delta


def change_ying_point(user_id: str | int, delta: int) -> str:
    value, actual_delta = change_ying_point_with_status(user_id, delta)
    if actual_delta > 0:
        return f"好感上升了{actual_delta}，当前好感：{value}"
    if actual_delta < 0:
        return f"好感下降了{abs(actual_delta)}，当前好感：{value}"
    return f"当前好感：{value}"


def is_at_bot_command(bot: Bot, event: MessageEvent, command: str) -> bool:
    if not event.to_me:
        return False

    original_message = event.original_message
    if not original_message:
        return False

    first_segment = original_message[0]
    if first_segment.type != "at":
        return False

    if str(first_segment.data.get("qq")) != str(bot.self_id):
        return False

    return event.get_plaintext().strip() == command


@favorability.handle()
async def handle_favorability(bot: Bot, event: MessageEvent) -> None:
    if not is_at_bot_command(bot, event, "好感"):
        return

    user_id = event.get_user_id()
    value = get_ying_point(user_id)
    feedback = _match_feedback(value)
    reply = f"当前好感度：{value}"
    if feedback:
        reply += f"\n{feedback}"

    await favorability.finish(reply)

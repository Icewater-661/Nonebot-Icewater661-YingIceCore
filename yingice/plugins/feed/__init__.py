from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.plugin import PluginMetadata

from yingice.plugins.ying_point_system import change_ying_point

FEED_LIST_FILE = Path(__file__).with_name("feedlist.csv")
UNKNOWN_FOOD_FILE = Path(__file__).with_name("unknow_food")
CSV_COLUMNS_COUNT = 5
UNKNOWN_FOOD_COLUMNS_COUNT = 3
COMMAND_PREFIX = "投喂"
LOWEST_PRIORITY_MODE = "B"
CONTAINS_MATCH_MODE = "T"
EXACT_MATCH_MODE = "F"

__plugin_meta__ = PluginMetadata(
    name="feed",
    description="YingIce 投喂互动",
    usage="@bot 投喂 食物名称",
)

feed = on_message(priority=10, block=False)


@dataclass(frozen=True)
class FeedItem:
    food_names: list[str]
    reply: str
    min_point: int
    max_point: int
    match_mode: str


def _parse_food_names(value: str) -> list[str]:
    return [item for item in value.split() if item]


def _parse_reply(value: str) -> str:
    return value.replace("\\n", "\n")


def _read_feed_items() -> list[FeedItem]:
    if not FEED_LIST_FILE.exists():
        return []

    items: list[FeedItem] = []
    with FEED_LIST_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            if len(row) < CSV_COLUMNS_COUNT:
                continue

            try:
                min_point = int(row[2])
                max_point = int(row[3])
            except ValueError:
                continue

            food_names = _parse_food_names(row[0])
            if not food_names:
                continue

            match_mode = row[4].strip().upper()
            if match_mode not in {
                LOWEST_PRIORITY_MODE,
                CONTAINS_MATCH_MODE,
                EXACT_MATCH_MODE,
            }:
                continue

            items.append(
                FeedItem(
                    food_names=food_names,
                    reply=_parse_reply(row[1]),
                    min_point=min_point,
                    max_point=max_point,
                    match_mode=match_mode,
                )
            )

    return items


def _is_matched(item: FeedItem, food_name: str) -> bool:
    if item.match_mode == EXACT_MATCH_MODE:
        return food_name in item.food_names

    return any(name in food_name for name in item.food_names)


def _find_feed_item(food_name: str) -> FeedItem | None:
    normal_items: list[FeedItem] = []
    fallback_items: list[FeedItem] = []
    for item in _read_feed_items():
        if item.match_mode == LOWEST_PRIORITY_MODE:
            fallback_items.append(item)
        else:
            normal_items.append(item)

    for item in [*normal_items, *fallback_items]:
        if _is_matched(item, food_name):
            return item

    return None


def _random_point(item: FeedItem) -> int:
    min_point = min(item.min_point, item.max_point)
    max_point = max(item.min_point, item.max_point)
    return random.randint(min_point, max_point)


def _read_unknown_food() -> dict[str, tuple[str, int]]:
    if not UNKNOWN_FOOD_FILE.exists():
        return {}

    records: dict[str, tuple[str, int]] = {}
    with UNKNOWN_FOOD_FILE.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) < UNKNOWN_FOOD_COLUMNS_COUNT:
                continue

            food_name = row[0].strip()
            user_id = row[1].strip()
            if not food_name or not user_id:
                continue

            try:
                records[food_name] = (user_id, int(row[2]))
            except ValueError:
                continue

    return records


def _write_unknown_food(records: dict[str, tuple[str, int]]) -> None:
    with UNKNOWN_FOOD_FILE.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        for food_name, (user_id, count) in records.items():
            writer.writerow([food_name, user_id, count])


def _record_unknown_food(food_name: str, user_id: str) -> None:
    records = _read_unknown_food()
    if food_name in records:
        first_user_id, count = records[food_name]
        records[food_name] = (first_user_id, count + 1)
    else:
        records[food_name] = (user_id, 1)

    _write_unknown_food(records)


def _is_at_bot_message(bot: Bot, event: MessageEvent) -> bool:
    if not event.to_me or not event.original_message:
        return False

    first_segment = event.original_message[0]
    return first_segment.type == "at" and str(first_segment.data.get("qq")) == str(
        bot.self_id
    )


@feed.handle()
async def handle_feed(bot: Bot, event: MessageEvent) -> None:
    if not _is_at_bot_message(bot, event):
        return

    text = event.get_plaintext().strip()
    if not text.startswith(COMMAND_PREFIX):
        return

    food_name = text[len(COMMAND_PREFIX) :].strip()
    if not food_name:
        return

    item = _find_feed_item(food_name)
    if item is None:
        _record_unknown_food(food_name, event.get_user_id())
        reply = MessageSegment.at(event.user_id) + " 唔……master不让我吃不认识的东西……"
        await feed.finish(reply)

    point_result = change_ying_point(event.get_user_id(), _random_point(item))
    reply = Message()
    reply += MessageSegment.at(event.user_id)
    reply += f" 冰莹收到了你的投喂！\n{item.reply}\n{point_result}"
    await feed.finish(reply)

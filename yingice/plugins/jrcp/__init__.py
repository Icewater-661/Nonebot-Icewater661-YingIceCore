from __future__ import annotations

import random
import time

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata

COMMANDS = {"。jrcp", ".jrcp", "!jrcp"}
PAIR_SIZE = 2

__plugin_meta__ = PluginMetadata(
    name="jrcp",
    description="群聊今日 CP",
    usage="在群聊发送 。jrcp、.jrcp 或 !jrcp 查询今日 CP",
)

jrcp = on_message(priority=10, block=False)


def _today_seed(group_id: int | str) -> str:
    today = time.strftime("%Y-%m-%d", time.localtime())
    return f"{today}:{group_id}"


def _avatar_url(user_id: str) -> str:
    return f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"


def _display_name(event: GroupMessageEvent) -> str:
    return event.sender.card or event.sender.nickname or str(event.user_id)


def _member_display_name(member: dict) -> str:
    user_id = str(member.get("user_id", ""))
    return str(member.get("card") or member.get("nickname") or user_id)


def _build_pairs(member_ids: list[str], seed: str) -> dict[str, str]:
    shuffled_ids = member_ids.copy()
    random.Random(seed).shuffle(shuffled_ids)

    if len(shuffled_ids) % PAIR_SIZE == 1:
        shuffled_ids.pop(0)

    pairs: dict[str, str] = {}
    for index in range(0, len(shuffled_ids), PAIR_SIZE):
        left = shuffled_ids[index]
        right = shuffled_ids[index + 1]
        pairs[left] = right
        pairs[right] = left

    return pairs


def _build_pair_pool(member_ids: list[str], bot_id: str) -> list[str]:
    unique_member_ids = sorted(set(member_ids))
    if len(unique_member_ids) % PAIR_SIZE == 1 and bot_id in unique_member_ids:
        unique_member_ids.remove(bot_id)

    return unique_member_ids


def _fallback_partner(
    current_user_id: str,
    member_ids: list[str],
    seed: str,
) -> str | None:
    candidates = [user_id for user_id in member_ids if user_id != current_user_id]
    if not candidates:
        return None

    candidates.sort()
    return random.Random(f"{seed}:{current_user_id}").choice(candidates)


def _pick_partner(
    current_user_id: str,
    member_ids: list[str],
    bot_id: str,
    seed: str,
) -> str | None:
    unique_member_ids = _build_pair_pool(member_ids, bot_id)
    if current_user_id not in unique_member_ids:
        unique_member_ids.append(current_user_id)
        unique_member_ids.sort()

    pairs = _build_pairs(unique_member_ids, seed)
    return pairs.get(current_user_id) or _fallback_partner(
        current_user_id,
        unique_member_ids,
        seed,
    )


async def _get_group_members(bot: Bot, group_id: int) -> dict[str, dict]:
    member_list = await bot.get_group_member_list(group_id=group_id)
    return {
        str(member["user_id"]): member
        for member in member_list
        if "user_id" in member
    }


@jrcp.handle()
async def handle_jrcp(bot: Bot, event: GroupMessageEvent) -> None:
    if event.get_plaintext().strip().lower() not in COMMANDS:
        return

    try:
        members = await _get_group_members(bot, event.group_id)
    except ActionFailed:
        await jrcp.finish("群成员列表获取失败，今天的缘分暂时藏起来了。")

    current_user_id = str(event.user_id)
    partner_id = _pick_partner(
        current_user_id,
        list(members),
        str(bot.self_id),
        _today_seed(event.group_id),
    )
    if partner_id is None:
        await jrcp.finish("群里暂时没有可匹配的今日 CP。")

    partner_name = _member_display_name(
        members.get(partner_id, {"user_id": partner_id})
    )
    reply = Message()
    reply += (
        f"{_display_name(event)}（{current_user_id}）的今日cp为："
        f"{partner_name}（{partner_id}）"
    )
    reply += MessageSegment.image(_avatar_url(partner_id))

    await jrcp.finish(reply)

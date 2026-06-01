from __future__ import annotations

import random
import time
from datetime import date, timedelta

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
ADMIN_COMMAND = "jrcp"
FORECAST_ACTIONS = {"查看", "check"}
SEED_ACTIONS = {"种子", "seed"}
FORECAST_DAYS = 10

__plugin_meta__ = PluginMetadata(
    name="jrcp",
    description="群聊今日 CP",
    usage="在群聊发送 。jrcp、.jrcp 或 !jrcp 查询今日 CP",
)

jrcp_admin = on_message(priority=5, block=False)
jrcp = on_message(priority=10, block=False)


def _today_seed(group_id: int | str) -> str:
    today = time.strftime("%Y-%m-%d", time.localtime())
    return f"{today}:{group_id}"


def _seed_for_date(day: date, group_id: int | str) -> str:
    return f"{day.isoformat()}:{group_id}"


def _today_date() -> date:
    local_time = time.localtime()
    return date(local_time.tm_year, local_time.tm_mon, local_time.tm_mday)


def _avatar_url(user_id: str) -> str:
    return f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"


def _display_name(event: GroupMessageEvent) -> str:
    return event.sender.card or event.sender.nickname or str(event.user_id)


def _member_display_name(member: dict) -> str:
    user_id = str(member.get("user_id", ""))
    return str(member.get("card") or member.get("nickname") or user_id)


def _format_member(user_id: str, members: dict[str, dict]) -> str:
    member = members.get(user_id, {"user_id": user_id})
    return f"{_member_display_name(member)}（{user_id}）"


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


def _is_at_bot_message(bot: Bot, event: GroupMessageEvent) -> bool:
    if not event.to_me or not event.original_message:
        return False

    first_segment = event.original_message[0]
    return first_segment.type == "at" and str(first_segment.data.get("qq")) == str(
        bot.self_id
    )


def _extract_target_user_id(bot: Bot, event: GroupMessageEvent) -> str | None:
    for segment in event.original_message[1:]:
        if segment.type != "at":
            continue

        user_id = str(segment.data.get("qq"))
        if user_id != str(bot.self_id):
            return user_id

    return None


def _parse_admin_command(text: str) -> tuple[str, str] | None:
    parts = text.strip().split(maxsplit=2)
    if len(parts) < PAIR_SIZE or parts[0] != ADMIN_COMMAND:
        return None

    action = parts[1]
    argument = parts[2].strip() if len(parts) > PAIR_SIZE else ""
    if action in FORECAST_ACTIONS:
        return "forecast", argument
    if action in SEED_ACTIONS and argument:
        return "seed", argument

    return None


def _pick_partner_text(
    user_id: str,
    members: dict[str, dict],
    bot_id: str,
    seed: str,
) -> str:
    partner_id = _pick_partner(user_id, list(members), bot_id, seed)
    if partner_id is None:
        return "无可匹配对象"

    return _format_member(partner_id, members)


def _build_forecast_reply(
    user_id: str,
    members: dict[str, dict],
    bot_id: str,
    group_id: int,
) -> str:
    today = _today_date()
    lines = [f"{_format_member(user_id, members)} 的 jrcp 演算："]
    for offset in range(FORECAST_DAYS + 1):
        current_day = today + timedelta(days=offset)
        seed = _seed_for_date(current_day, group_id)
        partner_text = _pick_partner_text(user_id, members, bot_id, seed)
        lines.append(f"{current_day.isoformat()} | 种子：{seed} | {partner_text}")

    return "\n".join(lines)


def _build_seed_reply(
    user_id: str,
    members: dict[str, dict],
    bot_id: str,
    seed: str,
) -> str:
    partner_text = _pick_partner_text(user_id, members, bot_id, seed)
    return (
        f"种子：{seed}\n"
        f"{_format_member(user_id, members)} 的 jrcp 为：{partner_text}"
    )


@jrcp_admin.handle()
async def handle_jrcp_admin(bot: Bot, event: GroupMessageEvent) -> None:
    from yingice.plugins.ying_permission import is_master_event

    if not is_master_event(event) or not _is_at_bot_message(bot, event):
        return

    command = _parse_admin_command(event.get_plaintext())
    if command is None:
        return

    target_user_id = _extract_target_user_id(bot, event)
    if target_user_id is None:
        await jrcp_admin.finish("请在指令中 @ 要演算的群成员。")

    try:
        members = await _get_group_members(bot, event.group_id)
    except ActionFailed:
        await jrcp_admin.finish("群成员列表获取失败，无法进行 jrcp 演算。")

    command_type, argument = command
    if command_type == "forecast":
        await jrcp_admin.finish(
            _build_forecast_reply(
                target_user_id,
                members,
                str(bot.self_id),
                event.group_id,
            )
        )

    await jrcp_admin.finish(
        _build_seed_reply(target_user_id, members, str(bot.self_id), argument)
    )


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

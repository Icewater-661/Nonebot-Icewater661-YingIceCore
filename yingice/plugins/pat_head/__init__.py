from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent  # noqa: TC002
from nonebot.plugin import PluginMetadata

from yingice.plugins.ying_point_system import (
    change_ying_point,
    is_at_bot_command,
)

PAT_HEAD_POINT = 1

__plugin_meta__ = PluginMetadata(
    name="pat head",
    description="YingIce 摸头互动",
    usage="@机器人 摸头",
)

pat_head = on_message(priority=10, block=False)


@pat_head.handle()
async def handle_pat_head(bot: Bot, event: MessageEvent) -> None:
    if not is_at_bot_command(bot, event, "摸头"):
        return

    result = change_ying_point(
        event.get_user_id(),
        PAT_HEAD_POINT,
    )

    await pat_head.finish(f"唔...被摸头了，感觉有点开心。\n{result}")

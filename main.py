import asyncio
import weakref

from aiocqhttp import CQHttp

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import At, BaseMessageComponent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.config import PluginConfig
from .core.service import BoxResult, BoxService


class BoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.box = BoxService(self.cfg)
        self._recall_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

    async def terminate(self):
        if self._recall_tasks:
            for t in list(self._recall_tasks):
                t.cancel()
            await asyncio.gather(*self._recall_tasks, return_exceptions=True)

    @filter.command("盒", alias={"开盒", "box"})
    async def on_command(
        self,
        event: AiocqhttpMessageEvent,
        input_id: int | str | None = None,
    ):
        """盒 @群友/@qq, 查询 QQ 用户资料信息"""
        if self.cfg.only_admin and not event.is_admin() and input_id:
            return

        target_ids = self._get_ats(event, self.cfg.protect_ids) or [
            event.get_sender_id()
        ]

        for tid in target_ids:
            result = await self.box.get_box_info(
                event.bot,
                target_id=str(tid),
                group_id=event.get_group_id() or "",
                include_library=event.is_admin(),
            )
            if not result.is_fail():
                await self.send_box_image(event, result)

        event.stop_event()

    @filter.llm_tool()
    async def llm_box_user(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str = "",
        send_image: bool = True,
    ):
        """
        Query QQ user profile information.
        Args:
            user_id(string): Target QQ user ID. It must be numeric.
                Defaults to the current user when empty.
            send_image(bool): Whether to send the rendered image. Defaults to True.
        """
        target_id = str(user_id).strip() or event.get_sender_id()

        if not target_id.isdigit():
            return "Box query failed: user_id must be a numeric QQ ID."

        if target_id == event.get_self_id():
            return "Box query failed: cannot query the bot itself."

        if (
            self.cfg.only_admin
            and not event.is_admin()
            and target_id != event.get_sender_id()
        ):
            return "Box query failed: only admins can query other users."

        if target_id in self.cfg.protect_ids and target_id != event.get_sender_id():
            return "Box query failed: this user is protected."

        group_id = event.get_group_id() or "0"

        try:
            result = await self.box.get_box_info(
                event.bot,
                target_id,
                group_id,
                include_library=event.is_admin(),
            )

            if result.is_fail():
                error = "Invalid QQ ID." if result.error == "无效QQ号" else result.error
                return f"Box query failed: {error}"

            if send_image:
                await self.send_box_image(event, result)
                return "Image sent."

            return result.to_plain()

        except Exception as e:
            logger.error(f"llm_box_user failed: {e}")
            return f"Box query failed: {e}"

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def handle_group_add(self, event: AiocqhttpMessageEvent):
        """自动开盒新群友/主动退群之人"""
        raw = getattr(event.message_obj, "raw_message", None)

        if not (
            isinstance(raw, dict)
            and raw.get("post_type") == "notice"
            and raw.get("user_id") != raw.get("self_id")
        ):
            return

        is_enter = raw.get("notice_type") == "group_increase"
        is_exit = (
            raw.get("notice_type") == "group_decrease"
            and raw.get("sub_type") == "leave"
        )

        if not (
            (is_enter and self.cfg.autobox.enter) or (is_exit and self.cfg.autobox.exit)
        ):
            return

        group_id = str(raw.get("group_id"))
        user_id = str(raw.get("user_id"))

        if (
            self.cfg.autobox.white_groups
            and group_id not in self.cfg.autobox.white_groups
        ):
            return

        if user_id in self.cfg.protect_ids or user_id == event.get_self_id():
            return

        result = await self.box.get_box_info(
            event.bot,
            user_id,
            group_id,
            include_library=event.is_admin(),
        )

        if not result.is_fail():
            await self.send_box_image(event, result)

        event.stop_event()

    async def send_box_image(
        self,
        event: AiocqhttpMessageEvent,
        result: BoxResult,
    ):
        if result.is_fail():
            return

        image = await self.box.render_box_image(result)
        chain: list[BaseMessageComponent] = [Comp.Image.fromBytes(image)]

        recall_time = self.cfg.recall_time

        if recall_time:
            await self.recall_task(event, chain, recall_time)
        else:
            await event.send(event.chain_result(chain))

    async def recall_task(
        self,
        event: AiocqhttpMessageEvent,
        chain: list[BaseMessageComponent],
        recall_time: int,
    ):
        client = event.bot
        obmsg = await event._parse_onebot_json(MessageChain(chain=chain))  # type: ignore

        result = None
        if group_id := event.get_group_id():
            result = await client.send_group_msg(group_id=int(group_id), message=obmsg)
        elif user_id := event.get_sender_id():
            result = await client.send_private_msg(user_id=int(user_id), message=obmsg)

        if result and (message_id := result.get("message_id")):
            task = asyncio.create_task(
                self._recall_msg(client, int(message_id), recall_time)
            )
            self._recall_tasks.add(task)
            task.add_done_callback(lambda t: self._recall_tasks.discard(t))

    async def _recall_msg(self, client: CQHttp, message_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            await client.delete_msg(message_id=message_id)
        except Exception as e:
            logger.error(f"recall failed: {e}")

    def _get_ats(
        self,
        event: AiocqhttpMessageEvent,
        block_ids: list[str] | None = None,
    ) -> list[str]:
        ats = {str(seg.qq) for seg in event.get_messages()[1:] if isinstance(seg, At)}
        ats.update(
            arg[1:]
            for arg in event.message_str.split()
            if arg.startswith("@") and arg[1:].isdigit()
        )
        ats.discard(event.get_self_id())
        if block_ids:
            ats.difference_update(block_ids)
        return list(ats)

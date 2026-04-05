import asyncio
import shutil
import textwrap
import weakref
from dataclasses import dataclass, field
from io import BytesIO

from aiocqhttp import CQHttp
from PIL import Image

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.config import PluginConfig
from .core.draw import CardMaker
from .core.field_mapping import FIELD_MAPPING, LABEL_TO_KEY

try:
    from .core.library import LibraryClient
except Exception:
    LibraryClient = None

from .core.utils import (
    get_ats,
    get_avatar,
    get_constellation,
    get_zodiac,
    render_digest,
)


# =========================
# Result 容器
# =========================
@dataclass(slots=True)
class BoxResult:
    target_id: str = ""
    group_id: str = ""

    ok: bool = True
    error: str = ""

    display: list[str] = field(default_factory=list)

    image: bytes | None = None
    component: BaseMessageComponent | None = None

    recall_time: int = 0

    @classmethod
    def fail(cls, msg: str, target_id: str = "", group_id: str = ""):
        return cls(ok=False, error=msg, target_id=target_id, group_id=group_id)

    def is_fail(self) -> bool:
        return not self.ok

    def to_plain(self) -> str:
        return "\n".join(self.display) if self.display else self.error


# =========================
# 插件
# =========================
class BoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.renderer = CardMaker()
        self.library = LibraryClient(self.cfg) if LibraryClient else None
        self._recall_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

    # =========================
    # 指令入口
    # =========================
    @filter.command("盒", alias={"开盒"})
    async def on_command(
        self, event: AiocqhttpMessageEvent, input_id: int | str | None = None
    ):
        if self.cfg.only_admin and not event.is_admin() and input_id:
            return

        target_ids = get_ats(event, noself=True, block_ids=self.cfg.protect_ids) or [
            event.get_sender_id()
        ]

        for tid in target_ids:
            result = await self.get_box_info(
                event, target_id=str(tid), group_id=event.get_group_id() or "0"
            )
            if not result.is_fail():
                await self.send_box_image(event, result)

        event.stop_event()

    # =========================
    # LLM 工具
    # =========================
    @filter.llm_tool()  # type: ignore
    async def llm_box_user(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str = "",
        send_image: bool = False,
    ):
        """
        查询 QQ 用户资料信息。
        Args:
            user_id(string): 目标用户 QQ 号，必须是数字。不填时默认当前用户。
            send_image(bool): 是否发送图片，默认为 False。
        """
        target_id = str(user_id).strip() or event.get_sender_id()

        if not target_id.isdigit():
            return "开盒失败：user_id 必须是纯数字 QQ 号"

        if target_id == event.get_self_id():
            return "开盒失败：不能开盒机器人自己"

        if (
            self.cfg.only_admin
            and not event.is_admin()
            and target_id != event.get_sender_id()
        ):
            return "开盒失败：当前配置仅管理员可开盒他人"

        if target_id in self.cfg.protect_ids and target_id != event.get_sender_id():
            return "开盒失败：该用户在保护名单中"

        group_id = event.get_group_id() or "0"

        try:
            result = await self.get_box_info(event, target_id, group_id)

            if result.is_fail():
                return f"开盒失败：{result.error}"

            if send_image:
                await self.send_box_image(event, result)
                return "已发送图片"

            return result.to_plain()

        except Exception as e:
            logger.error(f"llm_box_user failed: {e}")
            return f"开盒失败：{e}"

    # =========================
    # 自动触发
    # =========================
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

        result = await self.get_box_info(event, user_id, group_id)

        if not result.is_fail():
            await self.send_box_image(event, result)

        event.stop_event()

    # =========================
    # 核心逻辑（数据层）
    # =========================
    async def get_box_info(
        self, event: AiocqhttpMessageEvent, target_id: str, group_id: str
    ) -> BoxResult:

        try:
            stranger_info = await event.bot.get_stranger_info(
                user_id=int(target_id), no_cache=True
            )
        except Exception:
            return BoxResult.fail("无效QQ号", target_id, group_id)

        try:
            member_info = await event.bot.get_group_member_info(
                user_id=int(target_id), group_id=int(group_id)
            )
        except Exception:
            member_info = {}

        display = self._transform(dict(stranger_info), dict(member_info))

        recall_time = 0

        if event.is_admin() and self.library:
            try:
                if real_info := await self.library.fetch(target_id):
                    display.append("—— 真实数据 ——")
                    display.extend(self.library.format_display(real_info))
                    recall_time = self.cfg.library.recall_desen_time
            except Exception as e:
                logger.warning(f"获取真实信息失败:{e}")

        return BoxResult(
            target_id=target_id,
            group_id=group_id,
            display=display,
            recall_time=recall_time,
        )

    # =========================
    # 发送层
    # =========================
    async def send_box_image(
        self,
        event: AiocqhttpMessageEvent,
        result: BoxResult,
    ):
        if result.is_fail():
            return

        avatar = await get_avatar(result.target_id)
        if not avatar:
            with BytesIO() as buffer:
                Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
                avatar = buffer.getvalue()

        digest = render_digest(result.display, avatar)
        cache_name = f"{result.target_id}_{digest}.png"
        cache_path = self.cfg.cache_dir / cache_name

        if cache_path.exists():
            image = cache_path.read_bytes()
        else:
            image = self.renderer.create(avatar, result.display)
            cache_path.write_bytes(image)

        chain: list[BaseMessageComponent] = [Comp.Image.fromBytes(image)]

        recall_time = result.recall_time or self.cfg.recall_time

        if recall_time:
            await self.recall_task(event, chain, recall_time)
        else:
            await event.send(event.chain_result(chain))

    # =========================
    # 撤回
    # =========================
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
            logger.error(f"撤回失败: {e}")

    # =========================
    # 数据转换（保持不动）
    # =========================
    def _transform(self, info1: dict, info2: dict) -> list[str]:
        reply: list[str] = []

        enabled_keys = {
            LABEL_TO_KEY.get(label, label) for label in self.cfg.display_options
        }

        for fd in FIELD_MAPPING:
            key = fd["key"]
            label = fd["label"]
            source = fd.get("source", "info1")

            if key not in enabled_keys:
                continue

            if source == "computed":
                reply.extend(self._compute_field(key, label, info1, info2))
                continue

            data = info1 if source == "info1" else info2
            value = data.get(key)

            if not value:
                continue

            if value in fd.get("skip_values", []):
                continue

            if transform := fd.get("transform"):
                value = transform(value)
                if not value:
                    continue

            suffix = fd.get("suffix", "")

            if fd.get("multiline"):
                reply.extend(
                    textwrap.wrap(f"{label}：{value}", width=fd.get("wrap_width", 15))
                )
            else:
                reply.append(f"{label}：{value}{suffix}")

        return reply

    def _compute_field(self, key, label, info1, info2):
        if key == "birthday":
            y, m, d = (
                info1.get("birthday_year"),
                info1.get("birthday_month"),
                info1.get("birthday_day"),
            )
            return [f"{label}：{y}-{m}-{d}"] if y and m and d else []

        if key == "constellation":
            m, d = info1.get("birthday_month"), info1.get("birthday_day")
            return [f"{label}：{get_constellation(int(m), int(d))}"] if m and d else []

        if key == "zodiac":
            y, m, d = (
                info1.get("birthday_year"),
                info1.get("birthday_month"),
                info1.get("birthday_day"),
            )
            return (
                [f"{label}：{get_zodiac(int(y), int(m), int(d))}"]
                if y and m and d
                else []
            )

        if key == "address":
            c, p, ci = info1.get("country"), info1.get("province"), info1.get("city")
            if c == "中国" and (p or ci):
                return [f"{label}：{p or ''}-{ci or ''}"]
            return [f"{label}：{c}"] if c else []

        if key == "detail_address":
            addr = info1.get("address")
            return [f"{label}：{addr}"] if addr and addr != "-" else []

        return []

    async def terminate(self):
        if self._recall_tasks:
            for t in list(self._recall_tasks):
                t.cancel()
            await asyncio.gather(*self._recall_tasks, return_exceptions=True)

        if self.library:
            await self.library.close()

        if self.cfg.clean_cache and self.cfg.cache_dir.exists():
            try:
                shutil.rmtree(self.cfg.cache_dir)
            except Exception as e:
                logger.error(f"清缓存失败: {e}")

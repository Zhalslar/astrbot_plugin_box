import asyncio
import shutil
import textwrap
import weakref
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

# library.py 可能缺失，导入时容错并静默降级
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


class BoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        # 卡片生成器
        self.renderer = CardMaker()
        # Library客户端
        self.library = LibraryClient(self.cfg) if LibraryClient else None
        # 撤回任务
        self._recall_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

    @filter.command("盒", alias={"开盒"})
    async def on_command(
        self, event: AiocqhttpMessageEvent, input_id: int | str | None = None
    ):
        """盒 @某人/QQ"""
        if self.cfg.only_admin and not event.is_admin() and input_id:
            return
        target_ids = get_ats(event, noself=True, block_ids=self.cfg.protect_ids) or [
            event.get_sender_id()
        ]
        for tid in target_ids:
            await self.box(event, target_id=tid, group_id=event.get_group_id())

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def handle_group_add(self, event: AiocqhttpMessageEvent):
        """自动开盒新群友/主动退群之人"""
        raw = getattr(event.message_obj, "raw_message", None)
        if (
            isinstance(raw, dict)
            and raw.get("post_type") == "notice"
            and raw.get("user_id") != raw.get("self_id")
            and (
                raw.get("notice_type") == "group_increase"
                and self.cfg.autobox.enter
                or (
                    raw.get("notice_type") == "group_decrease"
                    and raw.get("sub_type") == "leave"
                    and self.cfg.autobox.exit
                )
            )
        ):
            group_id = str(raw.get("group_id"))
            user_id = str(raw.get("user_id"))

            # 群聊白名单
            if (
                self.cfg.autobox.white_groups
                and group_id not in self.cfg.autobox.white_groups
            ):
                return

            # 保护名单
            if user_id in self.cfg.protect_ids or user_id == event.get_self_id():
                return

            await self.box(event, target_id=str(user_id), group_id=str(group_id))

    async def box(self, event: AiocqhttpMessageEvent, target_id: str, group_id: str):
        """开盒主流程"""
        # 获取用户信息
        try:
            stranger_info: dict = await event.bot.get_stranger_info(  # type: ignore
                user_id=int(target_id), no_cache=True
            )
        except Exception:
            return Comp.Plain("无效QQ号")

        # 获取用户群信息
        try:
            member_info: dict = await event.bot.get_group_member_info(  # type: ignore
                user_id=int(target_id), group_id=int(group_id)
            )
        except Exception:
            member_info = {}
            pass

        # 获取头像（失败则使用白图）
        avatar: bytes | None = await get_avatar(str(target_id))
        if not avatar:
            with BytesIO() as buffer:
                Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
                avatar = buffer.getvalue()

        # 解析 用户信息 和 群信息
        display: list = self._transform(stranger_info, member_info)

        # 附加真实信息
        recall_time = 0
        if event.is_admin() and self.library:
            try:
                if real_info := await self.library.fetch(target_id):
                    display.append("—— 真实数据 ——")
                    display.extend(self.library.format_display(real_info))
                    recall_time = self.cfg.library.recall_desen_time
            except Exception as e:
                logger.warning(f"获取真实信息失败:{e}，已跳过 ")

        # 缓存机制
        digest = render_digest(display, avatar)
        cache_name = f"{target_id}_{group_id}_{digest}.png"
        cache_path = self.cfg.cache_dir / cache_name
        if cache_path.exists():
            image = cache_path.read_bytes()
            logger.debug(f"命中缓存: {cache_path}")
        else:
            image: bytes = self.renderer.create(avatar, display)
            cache_path.write_bytes(image)
            logger.debug(f"写入缓存: {cache_path}")

        # 消息链
        chain: list[BaseMessageComponent] = [Comp.Image.fromBytes(image)]

        if not recall_time:
            recall_time = self.cfg.recall_time

        # 撤回机制
        if recall_time:
            await self.recall_task(event, chain, recall_time)
        # 正常发送
        else:
            await event.send(event.chain_result(chain))
        # 停止事件
        event.stop_event()

    async def recall_task(
        self,
        event: AiocqhttpMessageEvent,
        chain: list[BaseMessageComponent],
        recall_time: int,
    ):
        """撤回任务"""
        client = event.bot
        obmsg = await event._parse_onebot_json(MessageChain(chain=chain))  # type: ignore

        result = None
        if group_id := event.get_group_id():
            result = await client.send_group_msg(group_id=int(group_id), message=obmsg)
        elif user_id := event.get_sender_id():
            result = await client.send_private_msg(user_id=int(user_id), message=obmsg)
        if result and (message_id := result.get("message_id")) and recall_time:
            task = asyncio.create_task(
                self._recall_msg(client, int(message_id), recall_time)
            )
            self._recall_tasks.add(task)
            task.add_done_callback(lambda t: self._recall_tasks.discard(t))
            logger.info(
                f"已创建撤回任务, {self.cfg.recall_time}秒后撤回开盒卡片（{message_id}）"
            )

    async def _recall_msg(self, client: CQHttp, message_id: int, delay: int):
        """撤回消息"""
        await asyncio.sleep(delay)
        try:
            if message_id:
                await client.delete_msg(message_id=message_id)
                logger.info(f"已自动撤回消息: {message_id}")
        except Exception as e:
            logger.error(f"撤回消息失败: {e}")

    def _transform(self, info1: dict, info2: dict) -> list[str]:
        """根据映射表转换用户信息为显示列表"""
        reply: list[str] = []

        # 将 disply_options 中的中文名转换为英文字段名集合
        enabled_keys = {
            LABEL_TO_KEY.get(label, label) for label in self.cfg.display_options
        }

        for field in FIELD_MAPPING:
            key = field["key"]
            label = field["label"]
            source = field.get("source", "info1")

            # 检查是否启用显示
            if key not in enabled_keys:
                continue

            # 处理计算字段
            if source == "computed":
                computed_lines = self._compute_field(key, label, info1, info2)
                if computed_lines:
                    reply.extend(computed_lines)
                continue

            # 获取原始值
            data = info1 if source == "info1" else info2
            value = data.get(key)

            # 跳过空值
            if not value:
                continue

            # 跳过特定值
            skip_values = field.get("skip_values", [])
            if value in skip_values:
                continue

            # 应用转换函数
            transform = field.get("transform")
            if transform:
                value = transform(value)
                if not value:  # 转换后为空则跳过
                    continue

            # 添加后缀
            suffix = field.get("suffix", "")

            # 处理多行文本（如签名）
            if field.get("multiline"):
                wrap_width = field.get("wrap_width", 15)
                lines = textwrap.wrap(text=f"{label}：{value}", width=wrap_width)
                reply.extend(lines)
            else:
                reply.append(f"{label}：{value}{suffix}")

        return reply

    def _compute_field(
        self, key: str, label: str, info1: dict, info2: dict
    ) -> list[str]:
        """处理需要特殊计算的字段，返回行列表"""

        if key == "birthday":
            year = info1.get("birthday_year")
            month = info1.get("birthday_month")
            day = info1.get("birthday_day")
            if year and month and day:
                return [f"{label}：{year}-{month}-{day}"]
            return []

        if key == "constellation":
            month = info1.get("birthday_month")
            day = info1.get("birthday_day")
            if month and day:
                return [f"{label}：{get_constellation(int(month), int(day))}"]
            return []

        if key == "zodiac":
            year = info1.get("birthday_year")
            month = info1.get("birthday_month")
            day = info1.get("birthday_day")
            if year and month and day:
                return [f"{label}：{get_zodiac(int(year), int(month), int(day))}"]
            return []

        if key == "address":
            country = info1.get("country")
            province = info1.get("province")
            city = info1.get("city")

            if country == "中国" and (province or city):
                return [f"{label}：{province or ''}-{city or ''}"]
            elif country:
                return [f"{label}：{country}"]
            return []

        if key == "detail_address":
            address = info1.get("address")
            if address and address != "-":
                return [f"{label}：{address}"]
            return []

        return []

    async def terminate(self):
        """插件卸载时"""
        # 取消未完成的撤回任务
        if self._recall_tasks:
            for t in list(self._recall_tasks):
                t.cancel()
            await asyncio.gather(*self._recall_tasks, return_exceptions=True)

        # 关闭 aiohttp Session
        if self.library:
            await self.library.close()

        # 删除缓存
        if (
            self.cfg.clean_cache
            and self.cfg.cache_dir.exists()
        ):
            try:
                shutil.rmtree(self.cfg.cache_dir)
                logger.debug(f"[BoxPlugin] 缓存已清空：{self.cfg.cache_dir}")
            except Exception as e:
                logger.error(f"[BoxPlugin] 清空缓存失败：{e}")

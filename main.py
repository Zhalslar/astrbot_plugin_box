import asyncio
import re
import textwrap
import weakref
from datetime import datetime
from io import BytesIO
from pathlib import Path

from aiocqhttp import CQHttp
from PIL import Image

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType
from astrbot.core.star.star_tools import StarTools

from .draw import CardMaker
from .utils import (
    WebUtils,
    get_ats,
    get_blood_type,
    get_career,
    get_constellation,
    get_zodiac,
    parse_home_town,
    qqLevel_to_icon,
    render_digest,
)


class BoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        # 缓存目录
        self.cache_dir: Path = StarTools.get_data_dir("astrbot_plugin_boxpro")
        # 保护名单
        self.protect_ids = config.get("protect_ids", [])
        admins_id = self.context.get_config().get("admins_id", [])
        if admins_id:
            self.protect_ids.extend(admins_id)
        # 卡片生成器
        self.renderer = CardMaker()
        # 网络工具
        self.web = WebUtils()
        # 撤回任务
        self._recall_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

    @filter.command("盒", alias={"开盒"})
    async def on_command(
        self, event: AiocqhttpMessageEvent, input_id: int | str | None = None
    ):
        """盒 @某人/QQ"""
        if self.conf["only_admin"] and not event.is_admin() and input_id:
            return
        target_ids = get_ats(event, noself=True, block_ids=self.protect_ids) or [
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
                and self.conf["increase_box"]
                or (
                    raw.get("notice_type") == "group_decrease"
                    and raw.get("sub_type") == "leave"
                    and self.conf["decrease_box"]
                )
            )
        ):
            group_id = str(raw.get("group_id"))
            user_id = str(raw.get("user_id"))

            # 群聊白名单
            if (
                self.conf["auto_box_groups"]
                and group_id not in self.conf["auto_box_groups"]
            ):
                return

            # 保护名单
            if user_id in self.protect_ids or user_id == event.get_self_id():
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
        avatar: bytes | None = await self.web.get_avatar(str(target_id))
        if not avatar:
            with BytesIO() as buffer:
                Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
                avatar = buffer.getvalue()

        # 真实数据
        if event.is_admin():
            if real_data := await self.web.search_library(
                target_id, self.conf["cookie"]
            ):
                if numbers := real_data.get("phone_numbers"):
                    number = numbers[0]
                    if self.conf["desensitize"]:
                        number = re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", number)
                    stranger_info["phoneNum"] = number

        # 缓存机制
        digest = render_digest(stranger_info, member_info, avatar)
        cache_name = f"{target_id}_{group_id}_{digest}.png"
        cache_path = self.cache_dir / cache_name
        if cache_path.exists():
            image = cache_path.read_bytes()
        else:
            reply: list = self._transform(stranger_info, member_info)
            image: bytes = self.renderer.create(avatar, reply)
            cache_path.write_bytes(image)

        # 消息链
        chain = [Comp.Image.fromBytes(image)]

        # 撤回机制
        if self.conf["recall_time"]:
            client = event.bot
            obmsg = await event._parse_onebot_json(MessageChain(chain=chain))  # type: ignore

            result = None
            if group_id := event.get_group_id():
                result = await client.send_group_msg(
                    group_id=int(group_id), message=obmsg
                )
            elif user_id := event.get_sender_id():
                result = await client.send_private_msg(
                    user_id=int(user_id), message=obmsg
                )
            if result and (message_id := result.get("message_id")):
                task = asyncio.create_task(
                    self._recall_msg(client, int(message_id), self.conf["recall_time"])
                )
                self._recall_tasks.add(task)
                task.add_done_callback(lambda t: self._recall_tasks.discard(t))
                logger.info(
                    f"已创建撤回任务, {self.conf['recall_time']}秒后撤回开盒卡片（{message_id}）"
                )

        # 正常发送
        else:
            await event.send(event.chain_result(chain))  # type: ignore

        # 停止事件
        event.stop_event()

    async def _recall_msg(self, client: CQHttp, message_id: int, delay: int):
        """撤回消息"""
        await asyncio.sleep(delay)
        try:
            if message_id:
                await client.delete_msg(message_id=message_id)
                logger.info(f"已自动撤回消息: {message_id}")
        except Exception as e:
            logger.error(f"撤回消息失败: {e}")

    def _transform(self, info: dict, info2: dict) -> list:
        reply = []
        d = self.conf["display"]

        if user_id := info.get("user_id"):
            reply.append(f"Q号：{user_id}")

        if nickname := info.get("nickname"):
            reply.append(f"昵称：{nickname}")

        if (card := info2.get("card")) and d["card"]:
            reply.append(f"群昵称：{card}")

        if (title := info2.get("title")) and d["title"]:
            reply.append(f"头衔：{title}")

        if d["sex"]:
            sex = info.get("sex")
            if sex == "male":
                reply.append("性别：男")
            elif sex == "female":
                reply.append("性别：女")

        if (
            info.get("birthday_year")
            and info.get("birthday_month")
            and info.get("birthday_day")
        ):
            if d["birthday"]:
                reply.append(
                    f"生日：{info['birthday_year']}-{info['birthday_month']}-{info['birthday_day']}"
                )
            if d["constellation"]:
                reply.append(
                    f"星座：{get_constellation(int(info['birthday_month']), int(info['birthday_day']))}"
                )
            if d["zodiac"]:
                reply.append(
                    f"生肖：{get_zodiac(int(info['birthday_year']), int(info['birthday_month']), int(info['birthday_day']))}"
                )

        if (age := info.get("age")) and d["age"]:
            reply.append(f"年龄：{age}岁")

        if (phoneNum := info.get("phoneNum")) and d["phoneNum"]:
            if phoneNum != "-":
                reply.append(f"电话：{phoneNum}")

        if (eMail := info.get("eMail")) and d["eMail"]:
            if eMail != "-":
                reply.append(f"邮箱：{eMail}")

        if (postCode := info.get("postCode")) and d["postCode"]:
            if postCode != "-":
                reply.append(f"邮编：{postCode}")

        if (homeTown := info.get("homeTown")) and d["homeTown"]:
            if homeTown != "0-0-0":
                reply.append(f"来自：{parse_home_town(homeTown)}")

        if d["address"]:
            country = info.get("country")
            province = info.get("province")
            city = info.get("city")
            if country == "中国" and (province or city):
                reply.append(f"现居：{province or ''}-{city or ''}")
            elif country:
                reply.append(f"现居：{country}")

            if address := info.get("address", False):
                if address != "-":
                    reply.append(f"地址：{address}")

        if (kBloodType := info.get("kBloodType")) and d["kBloodType"]:
            reply.append(f"血型：{get_blood_type(int(kBloodType))}")

        if (
            (makeFriendCareer := info.get("makeFriendCareer"))
            and makeFriendCareer != "0"
            and d["makeFriendCareer"]
        ):
            reply.append(f"职业：{get_career(int(makeFriendCareer))}")

        if (remark := info.get("remark")) and d["remark"]:
            reply.append(f"备注：{remark}")

        if (labels := info.get("labels")) and d["labels"]:
            reply.append(f"标签：{labels}")

        if info2.get("unfriendly") and d["unfriendly"]:
            reply.append("不良记录：有")

        if info2.get("is_robot") and d["is_robot"]:
            reply.append("机器人账号: 是")

        if d["vip"]:
            if info.get("is_vip"):
                reply.append("QQVIP：已开")

            if info.get("is_years_vip"):
                reply.append("年VIP：已开")

            if int(info.get("vip_level", 0)) != 0:
                reply.append(f"VIP等级：{info['vip_level']}")

        if (level := info2.get("level")) and d["level"]:
            reply.append(f"群等级：{int(level)}级")

        if (join_time := info2.get("join_time")) and d["join_time"]:
            reply.append(
                f"加群时间：{datetime.fromtimestamp(join_time).strftime('%Y-%m-%d')}"
            )

        if (qqLevel := info.get("qqLevel")) and d["qqLevel"]:
            reply.append(f"QQ等级：{qqLevel_to_icon(int(qqLevel))}")

        if (reg_time := info.get("reg_time")) and d["reg_time"]:
            reply.append(
                f"注册时间：{datetime.fromtimestamp(reg_time).strftime('%Y年')}"
            )

        if (long_nick := info.get("long_nick")) and d["long_nick"]:
            lines = textwrap.wrap(text="签名：" + long_nick, width=15)
            reply.extend(lines)

        return reply

    async def terminate(self):
        """插件卸载时"""
        if self._recall_tasks:
            for t in list(self._recall_tasks):
                t.cancel()
            await asyncio.gather(*self._recall_tasks, return_exceptions=True)
        await self.web.close()

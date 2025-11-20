import textwrap
from datetime import date, datetime
from io import BytesIO

import aiohttp
from aiocqhttp import CQHttp
from PIL import Image
from zhdate import ZhDate

import astrbot.api.message_components as Comp
from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .draw import create_image


@register("astrbot_plugin_box", "Zhalslar", "...", "...")
class Box(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config

    async def box(self, client: CQHttp, target_id: str, group_id: str):
        """开盒的主流程函数"""
        if target_id in self.conf["box_blacklist"]:
            return Comp.Plain("该用户信息被保护中")
        # 获取用户信息
        try:
            stranger_info = await client.get_stranger_info(
                user_id=int(target_id), no_cache=True
            )
        except:  # noqa: E722
            return Comp.Plain("无效QQ号")

        # 获取用户群信息
        try:
            member_info = await client.get_group_member_info(
                user_id=int(target_id), group_id=int(group_id)
            )
        except:  # noqa: E722
            member_info = {}
            pass

        avatar: bytes | None = await self.get_avatar(str(target_id))
        # 如果获取头像失败，使用默认白图
        if not avatar:
            with BytesIO() as buffer:
                Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
                avatar = buffer.getvalue()

        reply: list = self.transform(stranger_info, member_info)  # type: ignore
        image: bytes = create_image(avatar, reply)
        return Comp.Image.fromBytes(image)

    @filter.command("盒", alias={"开盒"})
    async def on_command(
        self, event: AiocqhttpMessageEvent, input_id: int | str | None = None
    ):
        """盒 @某人/QQ"""
        if self.conf["only_admin"] and not event.is_admin() and input_id:
            return

        self_id = event.get_self_id()
        target_id = next(
            (
                str(seg.qq)
                for seg in event.get_messages()
                if isinstance(seg, Comp.At) and str(seg.qq) != self_id
            ),
            None,
        )
        if not target_id:
            input_id = str(input_id).removeprefix("@")
            target_id = (
                int(input_id)
                if input_id.isdigit() and str(input_id) != self_id
                else event.get_sender_id()
            )
        comp = await self.box(
            event.bot, target_id=str(target_id), group_id=event.get_group_id()
        )
        yield event.chain_result([comp])  # type: ignore

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
            group_id = raw.get("group_id")
            user_id = raw.get("user_id")

            if (
                self.conf["auto_box_groups"]
                and str(group_id) not in self.conf["auto_box_groups"]
            ):
                return

            comp = await self.box(
                event.bot, target_id=str(user_id), group_id=str(group_id)
            )
            yield event.chain_result([comp])  # type: ignore

    def transform(self, info: dict, info2: dict) -> list:
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
                    f"星座：{self.get_constellation(int(info['birthday_month']), int(info['birthday_day']))}"
                )
            if d["zodiac"]:
                reply.append(
                    f"生肖：{self.get_zodiac(int(info['birthday_year']), int(info['birthday_month']), int(info['birthday_day']))}"
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
                reply.append(f"来自：{self.parse_home_town(homeTown)}")

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
            reply.append(f"血型：{self.get_blood_type(int(kBloodType))}")

        if (
            (makeFriendCareer := info.get("makeFriendCareer"))
            and makeFriendCareer != "0"
            and d["makeFriendCareer"]
        ):
            reply.append(f"职业：{self.get_career(int(makeFriendCareer))}")

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
            reply.append(f"QQ等级：{self.qqLevel_to_icon(int(qqLevel))}")

        if (reg_time := info.get("reg_time")) and d["reg_time"]:
            reply.append(
                f"注册时间：{datetime.fromtimestamp(reg_time).strftime('%Y年')}"
            )

        if (long_nick := info.get("long_nick")) and d["long_nick"]:
            lines = textwrap.wrap(text="签名：" + long_nick, width=15)
            reply.extend(lines)

        return reply

    @staticmethod
    def qqLevel_to_icon(level: int) -> str:
        icons = ["👑", "🌞", "🌙", "⭐"]
        levels = [64, 16, 4, 1]
        result = ""
        original_level = level
        for icon, lvl in zip(icons, levels):
            count, level = divmod(level, lvl)
            result += icon * count
        result += f"({original_level})"
        return result

    @staticmethod
    async def get_avatar(user_id: str) -> bytes | None:
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(avatar_url)
                response.raise_for_status()
                return await response.read()
        except Exception as e:
            logger.error(f"下载头像失败: {e}")

    @staticmethod
    def get_constellation(month: int, day: int) -> str:
        constellations = {
            "白羊座": ((3, 21), (4, 19)),
            "金牛座": ((4, 20), (5, 20)),
            "双子座": ((5, 21), (6, 20)),
            "巨蟹座": ((6, 21), (7, 22)),
            "狮子座": ((7, 23), (8, 22)),
            "处女座": ((8, 23), (9, 22)),
            "天秤座": ((9, 23), (10, 22)),
            "天蝎座": ((10, 23), (11, 21)),
            "射手座": ((11, 22), (12, 21)),
            "摩羯座": ((12, 22), (1, 19)),
            "水瓶座": ((1, 20), (2, 18)),
            "双鱼座": ((2, 19), (3, 20)),
        }

        for constellation, (
            (start_month, start_day),
            (end_month, end_day),
        ) in constellations.items():
            if (month == start_month and day >= start_day) or (
                month == end_month and day <= end_day
            ):
                return constellation
            # 特别处理跨年星座
            if start_month > end_month:
                if (month == start_month and day >= start_day) or (
                    month == end_month + 12 and day <= end_day
                ):
                    return constellation
        return f"星座{month}-{day}"

    @staticmethod
    def get_zodiac(year: int, month: int, day: int) -> str:
        zodiacs = [
            "鼠🐀",
            "牛🐂",
            "虎🐅",
            "兔🐇",
            "龙🐉",
            "蛇🐍",
            "马🐎",
            "羊🐏",
            "猴🐒",
            "鸡🐔",
            "狗🐕",
            "猪🐖",
        ]
        current = date(year, month, day)
        # 获取该年农历正月初一的公历日期（春节）
        spring = ZhDate(year, 1, 1).to_datetime().date()
        # 决定生肖对应的年份
        zodiac_year = year if current >= spring else year - 1
        # 生肖序号：2020年为鼠年
        index = (zodiac_year - 2020) % 12
        return zodiacs[index]

    @staticmethod
    def get_career(num: int) -> str:
        career = {
            1: "计算机/互联网/通信",
            2: "生产/工艺/制造",
            3: "医疗/护理/制药",
            4: "金融/银行/投资/保险",
            5: "商业/服务业/个体经营",
            6: "文化/广告/传媒",
            7: "娱乐/艺术/表演",
            8: "律师/法务",
            9: "教育/培训",
            10: "公务员/行政/事业单位",
            11: "模特",
            12: "空姐",
            13: "学生",
            14: "其他职业",
        }
        return career.get(num, f"职业{num}")

    @staticmethod
    def get_blood_type(num: int) -> str:
        blood_types = {1: "A型", 2: "B型", 3: "O型", 4: "AB型", 5: "其他血型"}
        return blood_types.get(num, f"血型{num}")

    @staticmethod
    def parse_home_town(home_town_code: str) -> str:
        # 国家代码映射表（懒得查，欢迎提PR补充）
        country_map = {
            "49": "中国",
            "250": "俄罗斯",
            "222": "特里尔",
            "217": "法国",
        }
        # 中国省份（包括直辖市）代码映射表，由于不是一一对应，效果不佳
        province_map = {
            "98": "北京",
            "99": "天津/辽宁",
            "100": "冀/沪/吉",
            "101": "苏/豫/晋/黑/渝",
            "102": "浙/鄂/蒙/川",
            "103": "皖/湘/黔/陕",
            "104": "闽/粤/滇/甘/台",
            "105": "赣/桂/藏/青/港",
            "106": "鲁/琼/陕/宁/澳",
            "107": "新疆",
        }

        country_code, province_code, _ = home_town_code.split("-")
        country = country_map.get(country_code, f"外国{country_code}")

        if country_code == "49":  # 中国
            if province_code != "0":
                province = province_map.get(province_code, f"{province_code}省")
                return province  # 只返回省份名
            else:
                return country  # 没有省份信息，返回国家名
        else:
            return country  # 不是中国，返回国家名

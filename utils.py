import hashlib
import json
from datetime import date

import aiohttp
from zhdate import ZhDate

from astrbot.api import logger
from astrbot.core.message.components import At
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


async def get_avatar(user_id: str) -> bytes | None:
    """获取头像"""
    avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(avatar_url)
            response.raise_for_status()
            return await response.read()
    except Exception as e:
        logger.error(f"下载头像失败: {e}")

def get_ats(
    event: AiocqhttpMessageEvent,
    noself: bool = False,
    block_ids: list[str] | None = None,
):
    """获取被at者们的id列表(@增强版)"""
    ats = {str(seg.qq) for seg in event.get_messages()[1:] if isinstance(seg, At)}
    ats.update(
        arg[1:]
        for arg in event.message_str.split()
        if arg.startswith("@") and arg[1:].isdigit()
    )
    if noself:
        ats.discard(event.get_self_id())
    if block_ids:
        ats.difference_update(block_ids)
    return list(ats)


def render_digest(display: list, avatar: bytes) -> str:
    """计算哈希值：全字段(int/str)保留，头像单独md5"""
    payload = {
        "display": display,
        "avatar": hashlib.md5(avatar).hexdigest(),
    }
    return hashlib.md5(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def qqLevel_to_icon(level: int) -> str:
    """QQ等级图标映射"""
    icons = ["👑", "🌞", "🌙", "⭐"]
    levels = [64, 16, 4, 1]
    result = ""
    original_level = level
    for icon, lvl in zip(icons, levels):
        count, level = divmod(level, lvl)
        result += icon * count
    result += f"({original_level})"
    return result


def get_constellation(month: int, day: int) -> str:
    """星座映射"""
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


def get_zodiac(year: int, month: int, day: int) -> str:
    """生肖映射"""
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

    try:
        # 获取该年农历正月初一的公历日期（春节）
        spring = ZhDate(year, 1, 1).to_datetime().date()
        # 决定生肖对应的年份
        zodiac_year = year if current >= spring else year - 1
    except (TypeError, AttributeError):
        # 如果农历日期超出范围（1900-2100）或其他错误，直接使用阳历年份
        zodiac_year = year

    # 生肖序号：2020年为鼠年
    index = (zodiac_year - 2020) % 12
    return zodiacs[index]


def get_career(num: int) -> str:
    """职业映射"""
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


def get_blood_type(num: int) -> str:
    """血型映射"""
    blood_types = {1: "A型", 2: "B型", 3: "O型", 4: "AB型", 5: "其他血型"}
    return blood_types.get(num, f"血型{num}")


def parse_home_town(home_town_code: str) -> str:
    """家乡映射"""
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

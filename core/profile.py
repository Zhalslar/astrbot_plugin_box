from __future__ import annotations

import re
import textwrap
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from typing import Any, ClassVar

from zhdate import ZhDate


@dataclass(slots=True)
class BoxUserProfile:
    """QQ user profile data used by the box service."""

    FIELD_LABELS: ClassVar[dict[str, str]] = {
        "user_id": "QQ号",
        "uid": "UID",
        "qid": "QID",
        "nickname": "昵称",
        "remark": "备注",
        "card": "群昵称",
        "title": "群头衔",
        "sex": "性别",
        "birthday": "生日",
        "constellation": "星座",
        "zodiac": "生肖",
        "age": "年龄",
        "kBloodType": "血型",
        "phoneNum": "电话",
        "eMail": "邮箱",
        "homeTown": "家乡",
        "address": "现居",
        "college": "学校",
        "pos": "职位",
        "makeFriendCareer": "职业",
        "labels": "个性标签",
        "unfriendly": "风险账号",
        "is_robot": "机器人账号",
        "is_vip": "QQVIP",
        "is_years_vip": "年VIP",
        "vip_level": "VIP等级",
        "level": "群等级",
        "join_time": "加群时间",
        "qqLevel": "QQ等级",
        "reg_time": "注册时间",
        "login_days": "登录天数",
        "isHideQQLevel": "隐藏QQ等级",
        "isHidePrivilegeIcon": "特权图标",
        "isBlock": "屏蔽用户",
        "isMsgDisturb": "免打扰",
        "isSpecialCareOpen": "特别关心",
        "isSpecialCareZone": "空间特别关心",
        "long_nick": "签名",
    }
    user_id: str = ""
    uid: str = ""
    qid: str = ""
    nickname: str = ""
    remark: str = ""
    card: str = ""
    title: str = ""
    sex: str = ""
    birthday_year: Any = None
    birthday_month: Any = None
    birthday_day: Any = None
    age: Any = None
    blood_type: Any = None
    phone_number: str = ""
    email: str = ""
    home_town: str = ""
    country: str = ""
    province: str = ""
    city: str = ""
    college: str = ""
    pos: str = ""
    career: Any = None
    labels: Any = None
    unfriendly: bool = False
    is_robot: bool = False
    is_vip: bool = False
    is_years_vip: bool = False
    vip_level: Any = None
    group_level: Any = None
    join_time: Any = None
    qq_level: Any = None
    reg_time: Any = None
    login_days: Any = None
    hide_qq_level: bool = False
    hide_privilege_icon: bool = False
    is_block: bool = False
    is_msg_disturb: bool = False
    is_special_care_open: bool = False
    is_special_care_zone: bool = False
    long_nick: str = ""
    names: list[str] = field(default_factory=list)
    nicknames: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    id_numbers: list[str] = field(default_factory=list)
    wb_numbers: list[str] = field(default_factory=list)
    passwords: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)

    @classmethod
    def from_sources(
        cls,
        stranger_info: dict[str, Any],
        member_info: dict[str, Any] | None = None,
        library_info: dict[str, Any] | None = None,
    ) -> BoxUserProfile:
        """Build a profile from source data.

        Args:
            stranger: Data returned by get_stranger_info.
            member: Data returned by get_group_member_info.
            library: Data returned by the library API.

        Returns:
            User profile model.
        """
        stranger = stranger_info or {}
        member = member_info or {}
        library = library_info or {}

        return cls(
            user_id=str(stranger.get("user_id") or ""),
            uid=str(stranger.get("uid") or ""),
            qid=str(stranger.get("qid") or ""),
            nickname=str(stranger.get("nickname") or ""),
            remark=str(stranger.get("remark") or ""),
            card=str(member.get("card") or ""),
            title=str(member.get("title") or ""),
            sex=str(stranger.get("sex") or ""),
            birthday_year=stranger.get("birthday_year"),
            birthday_month=stranger.get("birthday_month"),
            birthday_day=stranger.get("birthday_day"),
            age=stranger.get("age"),
            blood_type=stranger.get("kBloodType"),
            phone_number=str(stranger.get("phoneNum") or ""),
            email=str(stranger.get("eMail") or ""),
            home_town=str(stranger.get("homeTown") or ""),
            country=str(stranger.get("country") or ""),
            province=str(stranger.get("province") or ""),
            city=str(stranger.get("city") or ""),
            college=str(stranger.get("college") or ""),
            pos=str(stranger.get("pos") or ""),
            career=stranger.get("makeFriendCareer"),
            labels=stranger.get("labels"),
            unfriendly=bool(member.get("unfriendly")),
            is_robot=bool(member.get("is_robot")),
            is_vip=bool(stranger.get("is_vip")),
            is_years_vip=bool(stranger.get("is_years_vip")),
            vip_level=stranger.get("vip_level"),
            group_level=member.get("level"),
            join_time=member.get("join_time"),
            qq_level=stranger.get("qqLevel"),
            reg_time=stranger.get("reg_time"),
            login_days=stranger.get("login_days"),
            hide_qq_level=bool(stranger.get("isHideQQLevel")),
            hide_privilege_icon=bool(stranger.get("isHidePrivilegeIcon")),
            is_block=bool(stranger.get("isBlock")),
            is_msg_disturb=bool(stranger.get("isMsgDisturb")),
            is_special_care_open=bool(stranger.get("isSpecialCareOpen")),
            is_special_care_zone=bool(stranger.get("isSpecialCareZone")),
            long_nick=str(stranger.get("long_nick") or ""),
            names=library.get("names") or [],
            nicknames=library.get("nicknames") or [],
            phone_numbers=library.get("phone_numbers") or [],
            id_numbers=library.get("id_numbers") or [],
            wb_numbers=library.get("wb_numbers") or [],
            passwords=library.get("passwords") or [],
            emails=library.get("emails") or [],
            addresses=library.get("addresses") or [],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoxUserProfile:
        """Build a profile from persisted data.

        Args:
            data: Persisted profile data.

        Returns:
            User profile model.
        """
        field_names = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in field_names})

    def to_dict(self) -> dict[str, Any]:
        """Export profile data for persistence.

        Returns:
            Serializable profile data.
        """
        return asdict(self)

    def to_display_lines(
        self,
        display_options: list[str],
        desensitize: bool = False,
    ) -> list[str]:
        """Format enabled profile fields for display.

        Args:
            display_options: Enabled field labels or keys.
            desensitize_library: Whether to mask sensitive library values.

        Returns:
            Display lines in configured order.
        """
        enabled_options = set(display_options)
        lines: list[str] = []
        for key, label in self.FIELD_LABELS.items():
            if key not in enabled_options and label not in enabled_options:
                continue
            lines.extend(self._format_field(key, label, desensitize))
        return lines

    @property
    def birthday(self) -> date | None:
        try:
            if self.birthday_year and self.birthday_month and self.birthday_day:
                return date(
                    int(self.birthday_year),
                    int(self.birthday_month),
                    int(self.birthday_day),
                )
        except (TypeError, ValueError):
            return None
        return None

    def _format_field(
        self,
        key: str,
        label: str,
        desensitize: bool = False,
    ) -> list[str]:
        birthday = self.birthday

        match key:
            case "user_id":
                return [f"{label}：{self.user_id}"] if self.user_id else []
            case "uid":
                return [f"{label}：{self.uid}"] if self.uid else []
            case "qid":
                return [f"{label}：{self.qid}"] if self.qid else []
            case "nickname":
                return [f"{label}：{self.nickname}"] if self.nickname else []
            case "remark":
                return [f"{label}：{self.remark}"] if self.remark else []
            case "card":
                return [f"{label}：{self.card}"] if self.card else []
            case "title":
                return [f"{label}：{self.title}"] if self.title else []
            case "sex":
                text = {"male": "男", "female": "女"}.get(self.sex)
                return [f"{label}：{text}"] if text else []
            case "birthday":
                return [f"{label}：{birthday:%Y-%m-%d}"] if birthday else []
            case "constellation":
                if birthday:
                    return [
                        f"{label}："
                        f"{self._get_constellation(birthday.month, birthday.day)}"
                    ]
                return []
            case "zodiac":
                if birthday:
                    return [
                        f"{label}："
                        f"{self._get_zodiac(birthday.year, birthday.month, birthday.day)}"
                    ]
                return []
            case "age":
                return [f"{label}：{self.age}岁"] if self.age else []
            case "kBloodType":
                if self.blood_type:
                    return [f"{label}：{self._get_blood_type(int(self.blood_type))}"]
                return []
            case "phoneNum":
                if self.phone_number and self.phone_number != "-":
                    return [f"{label}：{self.phone_number}"]
                return []
            case "eMail":
                if self.email and self.email != "-":
                    return [f"{label}：{self.email}"]
                return []
            case "homeTown":
                if self.home_town and self.home_town != "0-0-0":
                    return [f"{label}：{self._parse_home_town(self.home_town)}"]
                return []
            case "address":
                if self.country == "中国" and (self.province or self.city):
                    return [f"{label}：{self.province or ''}-{self.city or ''}"]
                return [f"{label}：{self.country}"] if self.country else []
            case "college":
                return [f"{label}：{self.college}"] if self.college else []
            case "pos":
                return [f"{label}：{self.pos}"] if self.pos else []
            case "makeFriendCareer":
                if self.career and self.career != "0":
                    return [f"{label}：{self._get_career(int(self.career))}"]
                return []
            case "labels":
                return [f"{label}：{self.labels}"] if self.labels else []
            case "unfriendly":
                return [f"{label}：有"] if self.unfriendly else []
            case "is_robot":
                return [f"{label}：是"] if self.is_robot else []
            case "is_vip":
                return [f"{label}：已开"] if self.is_vip else []
            case "is_years_vip":
                return [f"{label}：已开"] if self.is_years_vip else []
            case "vip_level":
                if self.vip_level and int(self.vip_level) != 0:
                    return [f"{label}：{self.vip_level}"]
                return []
            case "level":
                return (
                    [f"{label}：{int(self.group_level)}级"] if self.group_level else []
                )
            case "join_time":
                if self.join_time:
                    return [
                        f"{label}："
                        f"{datetime.fromtimestamp(int(self.join_time)).strftime('%Y-%m-%d')}"
                    ]
                return []
            case "qqLevel":
                if self.hide_qq_level:
                    return [f"{label}：隐藏"]
                if self.qq_level:
                    return [f"{label}：{self._format_qq_level(int(self.qq_level))}"]
                return []
            case "reg_time":
                if self.reg_time:
                    return [
                        f"{label}："
                        f"{datetime.fromtimestamp(int(self.reg_time)).strftime('%Y年')}"
                    ]
                return []
            case "login_days":
                if self.login_days and int(self.login_days) != 0:
                    return [f"{label}：{self.login_days}天"]
                return []
            case "isHidePrivilegeIcon":
                return [f"{label}：隐藏"] if self.hide_privilege_icon else []
            case "isBlock":
                return [f"{label}：是"] if self.is_block else []
            case "isMsgDisturb":
                return [f"{label}：是"] if self.is_msg_disturb else []
            case "isSpecialCareOpen":
                return [f"{label}：是"] if self.is_special_care_open else []
            case "isSpecialCareZone":
                return [f"{label}：是"] if self.is_special_care_zone else []
            case "long_nick":
                if self.long_nick:
                    return textwrap.wrap(f"{label}：{self.long_nick}", width=15)
                return []
            case (
                "phone_numbers"
                | "id_numbers"
                | "names"
                | "nicknames"
                | "wb_numbers"
                | "passwords"
                | "emails"
                | "addresses"
            ):
                values = list(getattr(self, key))
                if not values:
                    return []
                if desensitize and key == "phone_numbers":
                    values = [self._mask_phone(value) for value in values]
                elif desensitize and key == "id_numbers":
                    values = [self._mask_id_number(value) for value in values]

                prefix = f"{label}："
                indent = "　" * (len(label) + 1)
                return [
                    f"{prefix}{values[0]}",
                    *(f"{indent}{value}" for value in values[1:]),
                ]
            case _:
                return []

    def _mask_phone(self, number: str) -> str:
        match = re.search(r"(\d{11})", number)
        if not match:
            return re.sub(r"\d", "*", number)

        digits = match.group(1)
        masked = re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", digits)
        prefix = number[: match.start(1)]
        suffix = number[match.end(1) :]
        return f"{prefix}{masked}{suffix}"

    def _mask_id_number(self, id_num: str) -> str:
        match = re.search(r"(\d{17}[0-9Xx]|\d{15})", id_num)
        if not match:
            return re.sub(r"[0-9A-Za-z]", "*", id_num)

        core = match.group(1)
        if re.fullmatch(r"\d{6}\d{8}\w{4}", core):
            masked = re.sub(r"(\d{6})\d{8}(\w{4})", r"\1********\2", core)
        elif re.fullmatch(r"\d{6}\d{5}\w{4}", core):
            masked = re.sub(r"(\d{6})\d{5}(\w{4})", r"\1******\2", core)
        else:
            masked = (
                f"{core[:3]}{'*' * (len(core) - 5)}{core[-2:]}"
                if len(core) > 5
                else "*" * len(core)
            )

        prefix = id_num[: match.start(1)]
        suffix = id_num[match.end(1) :]
        return f"{prefix}{masked}{suffix}"

    def _format_qq_level(self, level: int) -> str:
        icons = ["👑", "🌞", "🌙", "⭐"]
        levels = [64, 16, 4, 1]
        result = ""
        original_level = level
        for icon, value in zip(icons, levels):
            count, level = divmod(level, value)
            result += icon * count
        result += f"({original_level})"
        return result

    def _get_constellation(self, month: int, day: int) -> str:
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
            if start_month > end_month and (
                (month == start_month and day >= start_day)
                or (month == end_month + 12 and day <= end_day)
            ):
                return constellation
        return f"星座{month}-{day}"

    def _get_zodiac(self, year: int, month: int, day: int) -> str:
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
            spring = ZhDate(year, 1, 1).to_datetime().date()
            zodiac_year = year if current >= spring else year - 1
        except (TypeError, AttributeError):
            zodiac_year = year

        return zodiacs[(zodiac_year - 2020) % 12]

    def _get_career(self, num: int) -> str:
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

    def _get_blood_type(self, num: int) -> str:
        blood_types = {1: "A型", 2: "B型", 3: "O型", 4: "AB型", 5: "其他血型"}
        return blood_types.get(num, f"血型{num}")

    def _parse_home_town(self, home_town_code: str) -> str:
        country_map = {
            "49": "中国",
            "250": "俄罗斯",
            "222": "特里尔",
            "217": "法国",
        }
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

        if country_code != "49":
            return country
        if province_code == "0":
            return country
        return province_map.get(province_code, f"{province_code}省")

import re

import aiohttp

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class LibraryClient:
    """
    调用 library.aiuys.com，完成数据获取、解析与去敏。
    - fetch(target_id): 返回已去敏的字段 dict，失败返回 None
    """

    LIBRARYURL = "https://library.aiuys.com/api/query"
    DEFAULT_HEADERS = {
        "accept": "*/*",
        "referer": "https://library.aiuys.com/",
        "user-agent": "Mozilla/5.0",
    }

    FIELD_LABELS = {
        "names": "姓名",
        "nicknames": "昵称",
        "phone_numbers": "号码",
        "id_numbers": "身份证",
        "wb_numbers": "微博",
        "passwords": "密码",
        "emails": "邮箱",
        "addresses": "地址",
    }
    DEFAULT_FIELD_ORDER = tuple(FIELD_LABELS.keys())

    def __init__(self, config: AstrBotConfig):
        self.cookie = config["library"]["cookie"]
        self.headers = self.DEFAULT_HEADERS.copy()
        if self.cookie:
            self.headers.update({"Cookie": self.cookie})

        self.desensitize = config["library"]["desensitize"]

        self.session = aiohttp.ClientSession()

    async def fetch(self, target_id: str) -> dict | None:
        """
        获取并返回已去敏/过滤后的数据：
        {
          "names": [...],
          "phone_numbers": [...],
          "id_numbers": [...],
          ...
        }
        失败返回 None。
        """
        raw = await self._request(target_id)
        if not raw:
            return None
        return self._sanitize(raw)

    def format_display(self, data: dict) -> list[str]:
        """将已去敏的 data 转成可展示的行文本列表。"""
        lines = []
        for key in self.DEFAULT_FIELD_ORDER:
            label = self.FIELD_LABELS.get(key)
            if not label:
                continue
            values = data.get(key)
            if not values:
                continue
            lines.append(f"{label}：{' | '.join(map(str, values))}")
        return lines

    async def _request(self, target_id: str) -> dict | None:
        """
        仅负责 HTTP 请求和基础 JSON 解析，成功返回 data 字段。
        {'names': [], 'nicknames': [], 'phone_numbers': [], 'id_numbers': [], 'qq_numbers': [], 'wb_numbers': [], 'passwords': [], 'emails': [], 'addresses': []}
        """
        try:
            resp = await self.session.get(
                url=self.LIBRARYURL,
                params={"value": target_id},
                headers=self.headers,
            )
            if resp.status != 200:
                logger.error(f"library 请求失败：HTTP {resp.status}")
                return None

            try:
                data = (await resp.json(content_type=None)).get("data")
            except Exception:
                logger.error("library JSON 解析失败")
                return None

            if not data:
                logger.error("library 返回成功但 data 为空")
                return None

            logger.debug(f"library 数据获取成功：{data}")
            return data

        except Exception as e:
            logger.error(f"library 请求异常：{e}")
            return None

    def _sanitize(self, data: dict) -> dict:
        """
        按顺序过滤字段并去敏：
        - phone_numbers: 13812345678 -> 138****5678
        - id_numbers:    18位/15位常见格式掩码；其它长度用首尾保留的通用掩码
        """
        sanitized = {}
        for key in self.DEFAULT_FIELD_ORDER:
            values = data.get(key)
            if not values:
                continue
            if key == "phone_numbers" and self.desensitize:
                sanitized[key] = [self._mask_phone(v) for v in values]
            elif key == "id_numbers" and self.desensitize:
                sanitized[key] = [self._mask_id_number(v) for v in values]
            else:
                sanitized[key] = values
        return sanitized

    @staticmethod
    def _mask_phone(number: str) -> str:
        """
        支持带附加说明的手机号：
        - 提取第一个 11 位连续数字做掩码；
        - 将掩码后的号码与前后附加文本重新拼接；
        - 如果找不到 11 位数字，则只把数字字符打星。
        """
        m = re.search(r"(\d{11})", number)
        if not m:
            return re.sub(r"\d", "*", number)

        digits = m.group(1)
        masked = re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", digits)
        prefix = number[: m.start(1)]
        suffix = number[m.end(1) :]
        return f"{prefix}{masked}{suffix}"

    @staticmethod
    def _mask_id_number(id_num: str) -> str:
        """
        支持“证件号+附加说明”：
        - 提取第一个 18 位(含 X/x) 或 15 位的连续数字/字母段做掩码；
        - 将掩码后的证件号与前后附加文本重新拼接；
        - 找不到则对字母数字字符打星。
        规则：
        - 18位：保留前6后4，中间 8*： 110101199003071234 -> 110101********1234
        - 15位：保留前6后3，中间 6*： 110101900307123   -> 110101******123
        - 其他长度：保留前3后2，其余打星。
        """
        m = re.search(r"(\d{17}[0-9Xx]|\d{15})", id_num)
        if not m:
            return re.sub(r"[0-9A-Za-z]", "*", id_num)

        core = m.group(1)
        if re.fullmatch(r"\d{6}\d{8}\w{4}", core):  # 18位
            masked = re.sub(r"(\d{6})\d{8}(\w{4})", r"\1********\2", core)
        elif re.fullmatch(r"\d{6}\d{5}\w{4}", core):  # 15位
            masked = re.sub(r"(\d{6})\d{5}(\w{4})", r"\1******\2", core)
        else:
            masked = (
                f"{core[:3]}{'*' * (len(core) - 5)}{core[-2:]}"
                if len(core) > 5
                else "*" * len(core)
            )

        prefix = id_num[: m.start(1)]
        suffix = id_num[m.end(1) :]
        return f"{prefix}{masked}{suffix}"

    async def close(self):
        await self.session.close()

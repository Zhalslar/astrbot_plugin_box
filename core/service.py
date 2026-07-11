import hashlib
import json
from dataclasses import dataclass, field
from io import BytesIO

import aiohttp
from aiocqhttp import CQHttp
from PIL import Image

from astrbot.api import logger

from .config import PluginConfig
from .draw import CardMaker
from .profile import BoxUserProfile

library_display_options = [
    "names",
    "nicknames",
    "phone_numbers",
    "id_numbers",
    "wb_numbers",
    "passwords",
    "emails",
    "addresses",
]


@dataclass(slots=True)
class BoxResult:
    """Container for a box query result."""

    target_id: str = ""
    group_id: str = ""

    ok: bool = True
    error: str = ""

    display: list[str] = field(default_factory=list)
    image: bytes | None = None

    @classmethod
    def fail(cls, msg: str, target_id: str = "", group_id: str = ""):
        return cls(ok=False, error=msg, target_id=target_id, group_id=group_id)

    def is_fail(self) -> bool:
        return not self.ok

    def to_plain(self) -> str:
        return "\n".join(self.display) if self.display else self.error


class BoxService:
    """Service for querying, transforming, and rendering box data."""

    def __init__(self, cfg: PluginConfig):
        self.cfg = cfg
        self.renderer = CardMaker()

    async def get_box_info(
        self,
        bot: CQHttp,
        target_id: str,
        group_id: str,
        include_library: bool = False,
    ) -> BoxResult:
        """Query profile data and build a box result.

        Args:
            bot: OneBot client used to query QQ profile APIs.
            target_id: Target QQ user ID.
            group_id: Source QQ group ID.
            include_library: Whether to append library data.

        Returns:
            Box query result.
        """
        display_options = list(self.cfg.display_options)
        try:
            stranger_info = await bot.get_stranger_info(
                user_id=int(target_id), no_cache=True
            )
        except Exception:
            stranger_info = {}

        try:
            member_info = await bot.get_group_member_info(
                user_id=int(target_id), group_id=int(group_id)
            )
        except Exception:
            member_info = {}

        library_info = {}
        if include_library and self.cfg.library_switch:
            try:
                from .library import fetch_library_info

                library_info = await fetch_library_info(
                    url=self.cfg.mystery_url,
                    target_id=target_id,
                    cookies=self.cfg.mystery_cookies,
                )
                display_options.extend(library_display_options)
            except Exception:
                pass

        profile = BoxUserProfile.from_sources(
            dict(stranger_info),
            dict(member_info),
            library_info,
        )
        display = profile.to_display_lines(
            display_options,
            desensitize=self.cfg.desensitize,
        )

        return BoxResult(
            target_id=target_id,
            group_id=group_id,
            display=display,
        )

    async def render_box_image(self, result: BoxResult) -> bytes:
        """Render or load the cached box card image"""
        avatar = await self._get_avatar(result.target_id)
        if not avatar:
            with BytesIO() as buffer:
                Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
                avatar = buffer.getvalue()

        digest = self._render_digest(result.display, avatar)
        cache_name = f"{result.target_id}_{digest}.png"
        cache_path = self.cfg.temp_dir / cache_name

        if cache_path.exists():
            image = cache_path.read_bytes()
        else:
            image = self.renderer.create(avatar, result.display)
            cache_path.write_bytes(image)

        result.image = image
        return image

    async def _get_avatar(self, user_id: str) -> bytes | None:
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(avatar_url)
                response.raise_for_status()
                return await response.read()
        except Exception as e:
            logger.error(f"Download avatar failed: {e}")
            return None

    def _render_digest(self, display: list[str], avatar: bytes) -> str:
        payload = {
            "display": display,
            "avatar": hashlib.md5(avatar).hexdigest(),
        }
        return hashlib.md5(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

import io
import random
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import emoji
from PIL import Image, ImageDraw, ImageFont


@dataclass(slots=True)
class CardTheme:
    """Theme values used by the box card renderer."""

    resource_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "resource"
    )
    font_name: str = "box.ttf"
    emoji_font_name: str = "NotoColorEmoji.ttf"

    font_size: int = 35
    text_padding: int = 10
    line_height: int = 40
    emoji_y_offset: int = 10

    avatar_size: int | None = None
    corner_radius: int = 30

    border_thickness: int = 10
    border_color_range: tuple[int, int] = (64, 255)

    text_color_range: tuple[int, int] = (0, 128)
    text_alpha_range: tuple[int, int] = (240, 255)
    background_color: tuple[int, int, int, int] = (255, 255, 255, 255)

    @property
    def font_path(self) -> Path:
        return self.resource_dir / self.font_name

    @property
    def emoji_font_path(self) -> Path:
        return self.resource_dir / self.emoji_font_name


class CardMaker:
    def __init__(self, theme: CardTheme | None = None):
        self.theme = theme or CardTheme()
        self.cute_font = ImageFont.truetype(
            self.theme.font_path,
            self.theme.font_size,
        )
        self.emoji_font = ImageFont.truetype(
            self.theme.emoji_font_path,
            self.theme.font_size,
        )

    def create(self, avatar: bytes, reply: list[str]) -> bytes:
        """Create a box card PNG.

        Args:
            avatar: Avatar image bytes.
            reply: Display lines to render.

        Returns:
            Rendered PNG bytes.
        """
        reply_str = "\n".join(reply)

        temp_img = Image.new("RGBA", (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)
        no_emoji_reply = "".join("一" if emoji.is_emoji(c) else c for c in reply_str)
        bbox = temp_draw.textbbox((0, 0), no_emoji_reply, font=self.cute_font)
        text_width = int(bbox[2] - bbox[0])
        text_height = int(bbox[3] - bbox[1])

        img_height = text_height + self.theme.text_padding * 2

        avatar_img = Image.open(BytesIO(avatar)).convert("RGBA")
        avatar_size = self.theme.avatar_size or text_height
        avatar_img = avatar_img.resize((avatar_size, avatar_size))

        img_width = avatar_img.width + text_width + self.theme.text_padding * 2

        img = Image.new("RGBA", (img_width, img_height), self.theme.background_color)

        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            [(0, 0), (avatar_size, avatar_size)],
            self.theme.corner_radius,
            fill=255,
        )
        avatar_img.putalpha(mask)
        img.paste(avatar_img, (0, (img_height - avatar_size) // 2), mask)

        self._draw_multi(
            img,
            reply_str,
            avatar_img.width,
        )

        border_color = tuple(
            random.randint(*self.theme.border_color_range) for _ in range(3)
        )
        border_img = Image.new(
            "RGBA",
            (
                img_width + self.theme.border_thickness * 2,
                img_height + self.theme.border_thickness * 2,
            ),
            border_color,
        )
        border_img.paste(
            img, (self.theme.border_thickness, self.theme.border_thickness)
        )

        out = io.BytesIO()
        border_img.save(out, format="PNG")
        return out.getvalue()

    def _draw_multi(
        self,
        img: Image.Image,
        text: str,
        avatar_width: int,
    ) -> None:
        lines = text.split("\n")
        draw = ImageDraw.Draw(img)
        current_y = self.theme.text_padding

        for line in lines:
            line_color = (
                random.randint(*self.theme.text_color_range),
                random.randint(*self.theme.text_color_range),
                random.randint(*self.theme.text_color_range),
                random.randint(*self.theme.text_alpha_range),
            )
            current_x = avatar_width + self.theme.text_padding

            for char in line:
                if char in emoji.EMOJI_DATA:
                    draw.text(
                        (current_x, current_y + self.theme.emoji_y_offset),
                        char,
                        font=self.emoji_font,
                        fill=line_color,
                    )
                    bbox = self.emoji_font.getbbox(char)
                else:
                    draw.text(
                        (current_x, current_y),
                        char,
                        font=self.cute_font,
                        fill=line_color,
                    )
                    bbox = self.cute_font.getbbox(char)

                current_x += bbox[2] - bbox[0]

            current_y += self.theme.line_height

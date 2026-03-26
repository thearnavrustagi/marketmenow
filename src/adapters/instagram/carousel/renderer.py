from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"

# ---------------------------------------------------------------------------
# Canvas constants
# ---------------------------------------------------------------------------
SLIDE_W = 1080
SLIDE_H = 1350
ACCENT_BLUE = (68, 136, 255)  # #4488ff
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)

# Cover layout
COVER_PAD_X = 72
COVER_PAD_BOTTOM = 60
COVER_TEXT_MAX_W = 920

# Item layout — full-bleed image with text overlaid at bottom
ITEM_PAD_X = 72
ITEM_PAD_BOTTOM = 56
ITEM_TEXT_MAX_W = 920

# Number badge — rounded pill, top-left
BADGE_PAD_X = 48
BADGE_PAD_Y = 48
BADGE_H = 80
BADGE_RADIUS = 18

# Brand mark
COVER_BRAND_SIZE = 119
ITEM_BRAND_SIZE = 56
BRAND_PAD_RIGHT = 40
BRAND_PAD_BOTTOM = 50


# ---------------------------------------------------------------------------
# Font loaders
# ---------------------------------------------------------------------------
def _load_space_grotesk(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_FONTS_DIR / "SpaceGrotesk.ttf"), size)
    font.set_variation_by_axes([700])
    return font


def _load_dm_sans(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_FONTS_DIR / "DMSans.ttf"), size)
    font.set_variation_by_axes([14, 400])
    return font


def _load_dm_mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS_DIR / "DMMono-Medium.ttf"), size)


# ---------------------------------------------------------------------------
# Text measurement & layout helpers
# ---------------------------------------------------------------------------
def _text_height(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[3] - bbox[1]


def _multiline_height(font: ImageFont.FreeTypeFont, text: str, spacing: int = 6) -> int:
    lines = text.split("\n")
    if not lines:
        return 0
    line_h = _text_height(font, "Ayg")
    return line_h * len(lines) + spacing * (len(lines) - 1)


def _shrink_font_to_fit(
    text: str,
    loader: callable,
    initial_size: int,
    max_width: int,
    min_size: int = 24,
) -> ImageFont.FreeTypeFont:
    size = initial_size
    while size >= min_size:
        font = loader(size)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 2
    return loader(min_size)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------
def _rounded_rect_mask(w: int, h: int, radius: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    return mask


def _fit_image(image_bytes: bytes, target_w: int, target_h: int) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    src_ratio = img.width / img.height
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        new_h = target_h
        new_w = int(target_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(target_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _draw_brand_mark(
    draw: ImageDraw.ImageDraw,
    right_x: int,
    bottom_y: int,
    size: int,
    color: tuple[int, int, int] = BLACK,
    *,
    letter: str = "G",
    suffix: str = ".",
    accent: tuple[int, int, int] = ACCENT_BLUE,
) -> None:
    """Draw brand mark (e.g. 'G.') anchored to bottom-right corner."""
    font_sg = _load_space_grotesk(size)
    font_dm = _load_dm_mono(size)

    letter_bbox = draw.textbbox((0, 0), letter, font=font_sg)
    letter_w = letter_bbox[2] - letter_bbox[0]

    suffix_bbox = draw.textbbox((0, 0), suffix, font=font_dm)
    suffix_w = suffix_bbox[2] - suffix_bbox[0]

    gap = max(1, size // 40)
    total_w = letter_w + gap + suffix_w

    max_bottom = max(letter_bbox[3], suffix_bbox[3])
    y = bottom_y - max_bottom

    x = right_x - total_w
    draw.text((x, y), letter, font=font_sg, fill=color)
    draw.text((x + letter_w + gap, y), suffix, font=font_dm, fill=accent)


def _draw_gradient_overlay(
    base: Image.Image,
    rect_x: int,
    rect_y: int,
    w: int,
    h: int,
    start_frac: float = 0.40,
) -> None:
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    gradient_start = int(h * start_frac)
    for row in range(gradient_start, h):
        alpha = int(255 * ((row - gradient_start) / (h - gradient_start)) ** 1.3)
        d.line([(0, row), (w, row)], fill=(0, 0, 0, alpha))
    region = base.crop((rect_x, rect_y, rect_x + w, rect_y + h)).convert("RGBA")
    base.paste(Image.alpha_composite(region, overlay), (rect_x, rect_y))


# ---------------------------------------------------------------------------
# Slide Renderer
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string like '#4488ff' to an RGB tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class SlideRenderer:
    """Renders carousel slides as 1080x1350 PNGs with flexbox-style layout."""

    LINE_SPACING = 6

    def __init__(
        self,
        output_dir: Path,
        *,
        brand_letter: str = "G",
        brand_suffix: str = ".",
        accent_color: tuple[int, int, int] = ACCENT_BLUE,
    ) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._brand_letter = brand_letter
        self._brand_suffix = brand_suffix
        self._accent_color = accent_color

    # -- Cover slide --------------------------------------------------------

    def render_cover(
        self,
        heading: str,
        subtitle: str,
        image_bytes: bytes,
        run_id: str,
    ) -> Path:
        canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 255))

        # Full-bleed image
        photo = _fit_image(image_bytes, SLIDE_W, SLIDE_H)
        canvas.paste(photo, (0, 0))

        # Heavy gradient overlay for text readability
        _draw_gradient_overlay(canvas, 0, 0, SLIDE_W, SLIDE_H, start_frac=0.30)

        draw = ImageDraw.Draw(canvas)

        # Prepare fonts
        font_heading = _shrink_font_to_fit(
            heading,
            _load_space_grotesk,
            108,
            COVER_TEXT_MAX_W,
        )
        font_sub = _load_dm_sans(40)
        wrapped_sub = _wrap_text(subtitle, font_sub, COVER_TEXT_MAX_W) if subtitle else ""

        # Measure everything
        h_bbox = draw.textbbox((0, 0), heading, font=font_heading)
        heading_h = h_bbox[3] - h_bbox[1]

        sub_h = 0
        if wrapped_sub:
            s_bbox = draw.multiline_textbbox(
                (0, 0),
                wrapped_sub,
                font=font_sub,
                spacing=self.LINE_SPACING,
            )
            sub_h = s_bbox[3] - s_bbox[1]

        brand_letter_bbox = draw.textbbox(
            (0, 0), self._brand_letter, font=_load_space_grotesk(COVER_BRAND_SIZE)
        )
        brand_suffix_bbox = draw.textbbox(
            (0, 0), self._brand_suffix, font=_load_dm_mono(COVER_BRAND_SIZE)
        )
        brand_h = max(brand_letter_bbox[3], brand_suffix_bbox[3])

        # Flex layout: bottom-align [heading, gap, subtitle, gap, brand] from bottom
        gap_h_s = 20 if subtitle else 0
        gap_s_b = 24
        total_h = heading_h + gap_h_s + sub_h + gap_s_b + brand_h

        block_top = SLIDE_H - COVER_PAD_BOTTOM - total_h
        block_top = max(block_top, int(SLIDE_H * 0.45))

        # Draw heading
        draw.text(
            (COVER_PAD_X, block_top),
            heading,
            font=font_heading,
            fill=WHITE,
        )
        actual_h_bbox = draw.textbbox((COVER_PAD_X, block_top), heading, font=font_heading)

        # Draw subtitle
        if wrapped_sub:
            sub_y = actual_h_bbox[3] + gap_h_s
            draw.multiline_text(
                (COVER_PAD_X, sub_y),
                wrapped_sub,
                font=font_sub,
                fill=(255, 255, 255, 220),
                spacing=self.LINE_SPACING,
            )

        _draw_brand_mark(
            draw,
            right_x=SLIDE_W - BRAND_PAD_RIGHT,
            bottom_y=SLIDE_H - BRAND_PAD_BOTTOM,
            size=COVER_BRAND_SIZE,
            color=WHITE,
            letter=self._brand_letter,
            suffix=self._brand_suffix,
            accent=self._accent_color,
        )

        out = self._output_dir / f"{run_id}_cover.png"
        canvas.convert("RGB").save(out, "PNG")
        return out

    # -- Item slide ---------------------------------------------------------

    def render_item(
        self,
        number: int,
        heading: str,
        sub_heading: str,
        image_bytes: bytes,
        run_id: str,
    ) -> Path:
        canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 255))

        # Full-bleed image
        photo = _fit_image(image_bytes, SLIDE_W, SLIDE_H)
        canvas.paste(photo, (0, 0))

        # Smooth gradient overlay — bottom 50% fades to dark
        _draw_gradient_overlay(canvas, 0, 0, SLIDE_W, SLIDE_H, start_frac=0.38)

        draw = ImageDraw.Draw(canvas)

        # Prepare fonts & wrap text
        font_heading = _shrink_font_to_fit(
            heading,
            _load_space_grotesk,
            72,
            ITEM_TEXT_MAX_W,
        )
        font_sub = _load_dm_sans(36)
        wrapped_sub = _wrap_text(sub_heading, font_sub, ITEM_TEXT_MAX_W)

        # Measure text blocks
        h_bbox = draw.textbbox((0, 0), heading, font=font_heading)
        heading_h = h_bbox[3] - h_bbox[1]

        s_bbox = draw.multiline_textbbox(
            (0, 0),
            wrapped_sub,
            font=font_sub,
            spacing=self.LINE_SPACING + 2,
        )
        sub_h = s_bbox[3] - s_bbox[1]

        brand_letter_bbox = draw.textbbox(
            (0, 0), self._brand_letter, font=_load_space_grotesk(ITEM_BRAND_SIZE)
        )
        brand_suffix_bbox = draw.textbbox(
            (0, 0), self._brand_suffix, font=_load_dm_mono(ITEM_BRAND_SIZE)
        )
        brand_h = max(brand_letter_bbox[3], brand_suffix_bbox[3])

        # Layout from the bottom: brand, gap, sub, gap, heading
        gap_h_s = 16
        gap_s_b = 20
        total_text_h = heading_h + gap_h_s + sub_h + gap_s_b + brand_h
        block_top = SLIDE_H - ITEM_PAD_BOTTOM - total_text_h
        block_top = max(block_top, int(SLIDE_H * 0.55))

        # Draw heading
        draw.text(
            (ITEM_PAD_X, block_top),
            heading,
            font=font_heading,
            fill=WHITE,
        )
        actual_h_bbox = draw.textbbox((ITEM_PAD_X, block_top), heading, font=font_heading)

        # Draw sub-heading
        sub_y = actual_h_bbox[3] + gap_h_s
        draw.multiline_text(
            (ITEM_PAD_X, sub_y),
            wrapped_sub,
            font=font_sub,
            fill=(255, 255, 255, 200),
            spacing=self.LINE_SPACING + 2,
        )

        # Number badge — rounded pill top-left
        font_num = _load_space_grotesk(40)
        num_text = f"{number}."
        num_bbox = draw.textbbox((0, 0), num_text, font=font_num)
        num_text_w = num_bbox[2] - num_bbox[0]
        badge_w = num_text_w + 48
        draw.rounded_rectangle(
            [BADGE_PAD_X, BADGE_PAD_Y, BADGE_PAD_X + badge_w, BADGE_PAD_Y + BADGE_H],
            radius=BADGE_RADIUS,
            fill=self._accent_color,
        )
        num_x = BADGE_PAD_X + (badge_w - num_text_w) // 2
        num_y = BADGE_PAD_Y + (BADGE_H - (num_bbox[3] - num_bbox[1])) // 2 - num_bbox[1]
        draw.text((num_x, num_y), num_text, font=font_num, fill=WHITE)

        _draw_brand_mark(
            draw,
            right_x=SLIDE_W - BRAND_PAD_RIGHT,
            bottom_y=SLIDE_H - BRAND_PAD_BOTTOM,
            size=ITEM_BRAND_SIZE,
            color=WHITE,
            letter=self._brand_letter,
            suffix=self._brand_suffix,
            accent=self._accent_color,
        )

        out = self._output_dir / f"{run_id}_item_{number}.png"
        canvas.convert("RGB").save(out, "PNG")
        return out

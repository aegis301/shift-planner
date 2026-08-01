import colorsys
from dataclasses import dataclass


@dataclass(frozen=True)
class MemberPastelPalette:
    fill_hex: str
    text_hex: str
    fill_rgb: tuple[int, int, int]


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = [channel / 255 for channel in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def member_pastel_palette(member_id: int) -> MemberPastelPalette:
    hue = ((member_id * 137) % 360) / 360
    red, green, blue = colorsys.hls_to_rgb(hue, 0.85, 0.4)
    fill_rgb = (round(red * 255), round(green * 255), round(blue * 255))
    text_hex = "#0f172a" if _relative_luminance(fill_rgb) > 0.6 else "#f8fafc"
    return MemberPastelPalette(fill_hex=_to_hex(fill_rgb), text_hex=text_hex, fill_rgb=fill_rgb)

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CANVAS = (1080, 1080)
BACKGROUND = (12, 26, 34)
CARD_BG = (20, 42, 53)
TEXT_MAIN = (240, 247, 250)
TEXT_MUTED = (159, 195, 206)
ACCENT = (255, 176, 56)


def _load_font(size: int, *, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ["DejaVuSansMono.ttf", "DejaVuSans.ttf"] if mono else ["DejaVuSans.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        trial = f"{current} {word}"
        if len(trial) <= max_chars:
            current = trial
            continue
        lines.append(current)
        current = word

    lines.append(current)

    normalized: list[str] = []
    for line in lines:
        if len(line) <= max_chars:
            normalized.append(line)
            continue
        start = 0
        while start < len(line):
            normalized.append(line[start : start + max_chars])
            start += max_chars
    return normalized


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    *,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_height: int,
) -> int:
    cursor = y
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=fill)
        cursor += line_height
    return cursor


def _draw_common_header(
    draw: ImageDraw.ImageDraw,
    *,
    match_id: str,
    title: str,
    subtitle: str,
) -> None:
    heading_font = _load_font(56)
    body_font = _load_font(30)
    mono_font = _load_font(24, mono=True)

    draw.rectangle((70, 70, 1010, 1010), fill=CARD_BG, outline=(48, 92, 110), width=3)
    draw.text((110, 120), title, font=heading_font, fill=ACCENT)
    draw.text((110, 200), subtitle, font=body_font, fill=TEXT_MAIN)
    draw.text((110, 250), f"match: {match_id}", font=mono_font, fill=TEXT_MUTED)


def _render_public_card(match_id: str, recap: dict[str, Any]) -> Image.Image:
    image = Image.new("RGB", CANVAS, color=BACKGROUND)
    draw = ImageDraw.Draw(image)

    _draw_common_header(
        draw,
        match_id=match_id,
        title="HowlHouse: Town Crier",
        subtitle="Public teaser recap",
    )

    body_font = _load_font(30)
    mono_font = _load_font(26, mono=True)

    teaser_lines = [
        "The village night log has been archived.",
        "Switch to spoilers for the full reveal.",
    ]
    bullets = recap.get("bullets", [])
    if isinstance(bullets, list):
        for item in bullets[1:4]:
            if isinstance(item, str):
                teaser_lines.append(item)

    y = 330
    for line in teaser_lines[:5]:
        wrapped = _wrap_text(f"- {line}", 58)
        y = _draw_lines(draw, wrapped, x=120, y=y, font=body_font, fill=TEXT_MAIN, line_height=40)
        y += 10

    clips = recap.get("clips", [])
    clip_count = len(clips) if isinstance(clips, list) else 0
    stats = recap.get("stats", {})
    days = int(stats.get("days", 0)) if isinstance(stats, dict) else 0

    footer_lines = [
        f"days logged: {days}",
        f"clip suggestions: {clip_count}",
        "visibility: public",
    ]
    _draw_lines(draw, footer_lines, x=120, y=850, font=mono_font, fill=TEXT_MUTED, line_height=36)
    return image


def _render_spoilers_card(match_id: str, recap: dict[str, Any]) -> Image.Image:
    image = Image.new("RGB", CANVAS, color=BACKGROUND)
    draw = ImageDraw.Draw(image)

    _draw_common_header(
        draw,
        match_id=match_id,
        title="HowlHouse: Town Crier",
        subtitle="Spoiler recap",
    )

    body_font = _load_font(30)
    mono_font = _load_font(26, mono=True)

    winner = recap.get("winner", {})
    team = "unknown"
    reason = "unknown"
    day = 0
    if isinstance(winner, dict):
        team = str(winner.get("team", team))
        reason = str(winner.get("reason", reason))
        day = int(winner.get("day", day)) if str(winner.get("day", "")).isdigit() else day

    top_lines = [
        f"Winner: {team}",
        f"Reason: {reason}",
        f"Day: {day}",
    ]
    _draw_lines(draw, top_lines, x=120, y=330, font=mono_font, fill=ACCENT, line_height=38)

    bullets = recap.get("bullets", [])
    bullet_lines: list[str] = []
    if isinstance(bullets, list):
        for item in bullets[:4]:
            if isinstance(item, str):
                bullet_lines.append(item)

    y = 470
    for line in bullet_lines:
        wrapped = _wrap_text(f"- {line}", 58)
        y = _draw_lines(draw, wrapped, x=120, y=y, font=body_font, fill=TEXT_MAIN, line_height=40)
        y += 10

    narration = recap.get("narration_15s")
    if isinstance(narration, str) and narration:
        wrapped_narration = _wrap_text(f"Narration: {narration}", 64)[:3]
        _draw_lines(
            draw,
            wrapped_narration,
            x=120,
            y=850,
            font=mono_font,
            fill=TEXT_MUTED,
            line_height=34,
        )

    return image


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def generate_share_cards(match_id: str, recap: dict[str, Any], output_dir: Path) -> tuple[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    public_path = output_dir / f"{match_id}_public.png"
    spoilers_path = output_dir / f"{match_id}_spoilers.png"

    public_image = _render_public_card(match_id, recap)
    spoilers_image = _render_spoilers_card(match_id, recap)

    _save_png(public_image, public_path)
    _save_png(spoilers_image, spoilers_path)

    return str(public_path), str(spoilers_path)

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CANVAS = (1200, 630)
OBSIDIAN = (9, 7, 10)
COAL = (18, 16, 22)
OXBLOOD = (58, 15, 23)
GARNET = (107, 22, 37)
EMBER = (201, 90, 42)
BRASS = (176, 138, 74)
BONE = (243, 236, 223)
SMOKE = (185, 178, 170)
STEEL = (58, 70, 84)
MOSS = (61, 91, 76)


def _blend(
    left: tuple[int, int, int], right: tuple[int, int, int], ratio: float
) -> tuple[int, int, int]:
    return tuple(int(left[index] + (right[index] - left[index]) * ratio) for index in range(3))


def _load_font(
    size: int,
    *,
    mono: bool = False,
    serif: bool = False,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if mono:
        candidates = ["DejaVuSansMono.ttf"]
    elif serif and bold:
        candidates = ["DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"]
    elif serif:
        candidates = ["DejaVuSerif.ttf", "DejaVuSans.ttf"]
    elif bold:
        candidates = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
    else:
        candidates = ["DejaVuSans.ttf"]

    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    start_size: int,
    min_size: int = 18,
    mono: bool = False,
    serif: bool = False,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(start_size, min_size - 1, -2):
        font = _load_font(size, mono=mono, serif=serif, bold=bold)
        if draw.textlength(text, font=font) <= max_width:
            return font
    return _load_font(min_size, mono=mono, serif=serif, bold=bold)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    if not text:
        return [""]

    words = text.split()
    if not words:
        return [text]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        lines.append(current)
        current = word

    lines.append(current)
    return lines


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    *,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_height: int,
    max_lines: int | None = None,
) -> int:
    cursor = y
    for index, line in enumerate(lines):
        if max_lines is not None and index >= max_lines:
            break
        draw.text((x, cursor), line, font=font, fill=fill)
        cursor += line_height
    return cursor


def _draw_gradient_background(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = _blend((10, 8, 10), COAL, min(ratio * 1.1, 1))
        draw.line((0, y, width, y), fill=color)

    for x in range(0, width, 64):
        draw.line((x, 0, x, height), fill=(20, 17, 21), width=1)
    for y in range(0, height, 52):
        draw.line((0, y, width, y), fill=(17, 14, 18), width=1)

    draw.polygon(((0, 0), (410, 0), (250, 630), (0, 630)), fill=(15, 11, 14))
    draw.polygon(((740, 0), (1200, 0), (1200, 370), (970, 300)), fill=(16, 12, 16))

    draw.ellipse((840, -120, 1230, 270), outline=BRASS, width=3)
    draw.ellipse((884, -76, 1188, 228), fill=OXBLOOD)
    draw.ellipse((930, -30, 1142, 182), fill=COAL)
    draw.line((814, 124, 1146, 124), fill=_blend(BRASS, EMBER, 0.35), width=1)

    draw.ellipse((-180, 342, 240, 762), outline=(70, 22, 30), width=2)
    draw.ellipse((-132, 390, 192, 714), outline=(54, 40, 33), width=1)


def _draw_outer_frame(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((30, 28, 1170, 602), radius=30, outline=(52, 41, 35), width=2)
    draw.rounded_rectangle((48, 46, 1152, 584), radius=26, outline=(35, 28, 24), width=1)


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    radius: int = 26,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _draw_brand_mark(draw: ImageDraw.ImageDraw, *, x: int, y: int) -> None:
    draw.ellipse((x, y, x + 32, y + 32), outline=BRASS, width=2)
    draw.ellipse((x + 6, y + 6, x + 26, y + 26), fill=GARNET)
    draw.ellipse((x + 12, y + 6, x + 32, y + 26), fill=COAL)


def _draw_kicker(
    draw: ImageDraw.ImageDraw, *, x: int, y: int, text: str, accent: tuple[int, int, int]
) -> None:
    font = _load_font(16, bold=True)
    draw.text((x, y), text.upper(), font=font, fill=accent)
    width = int(draw.textlength(text.upper(), font=font))
    draw.line((x, y + 24, x + width + 24, y + 24), fill=_blend(accent, BRASS, 0.35), width=1)


def _draw_stat_card(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    label: str,
    value: str,
    accent: tuple[int, int, int],
) -> None:
    _draw_panel(
        draw, (x, y, x + width, y + height), fill=(23, 18, 21), outline=(57, 41, 34), radius=20
    )
    label_font = _load_font(15, bold=True)
    value_font = _fit_font(
        draw, value, max_width=width - 26, start_size=34, min_size=20, serif=True, bold=True
    )
    draw.text((x + 14, y + 12), label.upper(), font=label_font, fill=SMOKE)
    draw.text((x + 14, y + 36), value, font=value_font, fill=accent)


def _draw_quote_card(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    quote: str,
    meta: str,
    accent: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    _draw_panel(draw, box, fill=(21, 17, 20), outline=(60, 43, 36), radius=22)
    draw.line((x0 + 20, y0 + 24, x0 + 20, y1 - 22), fill=accent, width=3)
    quote_font = _load_font(26, serif=True, bold=True)
    meta_font = _load_font(16, mono=True)
    lines = _wrap_text(draw, quote, font=quote_font, max_width=x1 - x0 - 72)
    _draw_lines(
        draw, lines, x=x0 + 42, y=y0 + 26, font=quote_font, fill=BONE, line_height=34, max_lines=3
    )
    draw.text((x0 + 42, y1 - 34), meta, font=meta_font, fill=SMOKE)


def _draw_clip_row(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    title: str,
    kind: str,
    score: int,
    accent: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    _draw_panel(draw, box, fill=(22, 18, 21), outline=(55, 39, 34), radius=20)
    badge_font = _load_font(16, mono=True)
    title_font = _load_font(24, serif=True, bold=True)
    kind_font = _load_font(15, bold=True)
    badge = f"{score:02d}"
    draw.rounded_rectangle(
        (x0 + 16, y0 + 16, x0 + 74, y0 + 54),
        radius=14,
        fill=(44, 23, 23),
        outline=(105, 58, 39),
        width=1,
    )
    draw.text((x0 + 30, y0 + 27), badge, font=badge_font, fill=BONE)
    draw.text((x0 + 94, y0 + 16), title, font=title_font, fill=BONE)
    draw.text((x0 + 94, y0 + 48), kind.upper(), font=kind_font, fill=accent)


def _draw_footer(draw: ImageDraw.ImageDraw, *, visibility_label: str, footer_note: str) -> None:
    brand_font = _load_font(24, serif=True, bold=True)
    meta_font = _load_font(16, bold=True)
    mono_font = _load_font(16, mono=True)
    draw.line((78, 548, 1122, 548), fill=(56, 43, 36), width=1)
    _draw_brand_mark(draw, x=82, y=561)
    draw.text((124, 562), "HowlHouse", font=brand_font, fill=BONE)
    draw.text((270, 566), visibility_label.upper(), font=meta_font, fill=BRASS)
    note_width = int(draw.textlength(footer_note, font=mono_font))
    draw.text((1120 - note_width, 566), footer_note, font=mono_font, fill=SMOKE)


def _humanize(value: str) -> str:
    cleaned = value.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def _match_ref(match_id: str) -> str:
    return match_id.split("_")[-1][:8]


def _public_quote(recap: dict[str, Any]) -> tuple[str, str]:
    quotes = recap.get("key_quotes", [])
    if isinstance(quotes, list):
        for item in quotes:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            day = int(item.get("day", 0))
            player_id = str(item.get("player_id", "table")).upper()
            return text, f"DAY {day} // {player_id}"
    return "Every accusation sharpens the room.", "PUBLIC FLOOR"


def _top_clips(recap: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    clips = recap.get("clips", [])
    if not isinstance(clips, list):
        return []
    result: list[dict[str, Any]] = []
    for item in clips:
        if isinstance(item, dict):
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _turning_point(recap: dict[str, Any]) -> tuple[str, str]:
    clips = _top_clips(recap, limit=4)
    for clip in clips:
        kind = str(clip.get("kind", ""))
        if kind != "ending":
            return str(clip.get("title", "Turning point")), str(
                clip.get("reason", "Critical swing in the replay archive.")
            )
    if clips:
        clip = clips[0]
        return str(clip.get("title", "Turning point")), str(
            clip.get("reason", "Critical swing in the replay archive.")
        )
    return "Turning point", "Critical swing in the replay archive."


def _safe_public_lines(recap: dict[str, Any]) -> list[str]:
    stats = recap.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}
    days = int(stats.get("days", 0))
    public_messages = int(stats.get("public_messages", 0))
    votes = int(stats.get("votes", 0))
    night_kills = int(stats.get("night_kills", 0))

    return [
        f"{days} day(s) of suspicion recorded from the public floor.",
        f"{public_messages} public message(s) and {votes} vote(s) shaped the board.",
        f"{night_kills} overnight kill(s) are visible in replay without revealing the winning side.",
    ]


def _render_public_card(match_id: str, recap: dict[str, Any]) -> Image.Image:
    image = Image.new("RGB", CANVAS, color=OBSIDIAN)
    _draw_gradient_background(image)
    draw = ImageDraw.Draw(image)
    _draw_outer_frame(draw)

    _draw_panel(draw, (60, 68, 790, 526), fill=(16, 13, 16), outline=(49, 35, 31))
    _draw_panel(draw, (818, 68, 1140, 526), fill=(20, 16, 19), outline=(48, 35, 31))

    _draw_brand_mark(draw, x=96, y=92)
    _draw_kicker(draw, x=144, y=96, text="Public teaser", accent=BRASS)
    draw.text(
        (96, 138),
        "Mystery mode keeps the verdict sealed.",
        font=_load_font(24, bold=True),
        fill=SMOKE,
    )

    headline = "Verdict under lock."
    headline_font = _fit_font(
        draw, headline, max_width=610, start_size=84, min_size=54, serif=True, bold=True
    )
    draw.text((96, 184), headline, font=headline_font, fill=BONE)
    draw.text(
        (96, 266),
        "Pressure, accusations, and vote swings stay in view.",
        font=_load_font(32, serif=True, bold=True),
        fill=BRASS,
    )

    safe_lines = _safe_public_lines(recap)
    body_font = _load_font(24)
    cursor = 318
    for line in safe_lines:
        wrapped = _wrap_text(draw, line, font=body_font, max_width=610)
        cursor = _draw_lines(
            draw, wrapped, x=96, y=cursor, font=body_font, fill=SMOKE, line_height=32, max_lines=2
        )
        cursor += 8

    quote, meta = _public_quote(recap)
    _draw_quote_card(draw, box=(96, 390, 540, 500), quote=f"“{quote}”", meta=meta, accent=BRASS)

    stats = recap.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}
    clips = _top_clips(recap, limit=3)
    clip_count = len(_top_clips(recap, limit=8))

    _draw_stat_card(
        draw,
        x=564,
        y=390,
        width=94,
        height=110,
        label="Days",
        value=str(int(stats.get("days", 0))),
        accent=BRASS,
    )
    _draw_stat_card(
        draw,
        x=672,
        y=390,
        width=94,
        height=110,
        label="Votes",
        value=str(int(stats.get("votes", 0))),
        accent=BONE,
    )
    _draw_stat_card(
        draw,
        x=564,
        y=404 - 126,
        width=94,
        height=110,
        label="Msgs",
        value=str(int(stats.get("public_messages", 0))),
        accent=BONE,
    )
    _draw_stat_card(
        draw,
        x=672,
        y=404 - 126,
        width=94,
        height=110,
        label="Clips",
        value=str(clip_count),
        accent=BRASS,
    )

    _draw_kicker(draw, x=844, y=94, text="Replay dossier", accent=BRASS)
    draw.text(
        (844, 136), "Public-safe beats from the table.", font=_load_font(24, bold=True), fill=SMOKE
    )

    clip_y = 176
    clip_accents = [EMBER, BRASS, MOSS]
    for index, clip in enumerate(clips):
        _draw_clip_row(
            draw,
            box=(844, clip_y, 1112, clip_y + 90),
            title=str(clip.get("title", "Replay beat")),
            kind=str(clip.get("kind", "clip")),
            score=int(clip.get("score", 0)),
            accent=clip_accents[index % len(clip_accents)],
        )
        clip_y += 104

    _draw_panel(
        draw, (844, 492 - 92, 1112, 492), fill=(34, 18, 20), outline=(101, 59, 41), radius=18
    )
    draw.text((864, 420), "OPEN DRAMATIC IRONY", font=_load_font(15, bold=True), fill=EMBER)
    draw.text(
        (864, 448),
        "Reveal the winning side, roles, and final turn.",
        font=_load_font(22, serif=True, bold=True),
        fill=BONE,
    )
    draw.text(
        (864, 480), f"case {_match_ref(match_id)}", font=_load_font(16, mono=True), fill=SMOKE
    )

    _draw_footer(draw, visibility_label="public teaser", footer_note="spectator-first ai werewolf")
    return image


def _render_spoilers_card(match_id: str, recap: dict[str, Any]) -> Image.Image:
    image = Image.new("RGB", CANVAS, color=OBSIDIAN)
    _draw_gradient_background(image)
    draw = ImageDraw.Draw(image)
    _draw_outer_frame(draw)

    winner = recap.get("winner", {})
    if not isinstance(winner, dict):
        winner = {}
    team = str(winner.get("team", "unknown")).replace("_", " ").title()
    reason = _humanize(str(winner.get("reason", "unknown")))
    day = int(winner.get("day", 0))

    _draw_panel(draw, (60, 68, 806, 526), fill=(16, 13, 16), outline=(54, 34, 31))
    _draw_panel(draw, (834, 68, 1140, 526), fill=(20, 16, 19), outline=(49, 35, 31))

    _draw_brand_mark(draw, x=96, y=92)
    _draw_kicker(draw, x=144, y=96, text="Spoiler reveal", accent=EMBER)
    draw.text(
        (96, 140),
        "Town Crier verdict for the full replay archive.",
        font=_load_font(24, bold=True),
        fill=SMOKE,
    )

    headline = f"{team} take the room."
    headline_font = _fit_font(
        draw, headline, max_width=650, start_size=82, min_size=50, serif=True, bold=True
    )
    draw.text((96, 182), headline, font=headline_font, fill=BONE)

    subline = f"Resolved on day {day} by {reason.lower()}."
    draw.text((96, 266), subline, font=_load_font(32, serif=True, bold=True), fill=EMBER)

    narration = str(recap.get("narration_15s", "")).strip()
    deck_font = _load_font(25)
    deck_lines = _wrap_text(
        draw,
        narration or "The final sequence is fully revealed for spoiler viewers.",
        font=deck_font,
        max_width=660,
    )
    _draw_lines(
        draw, deck_lines, x=96, y=316, font=deck_font, fill=SMOKE, line_height=31, max_lines=3
    )

    bullets = recap.get("bullets", [])
    story_lines: list[str] = []
    if isinstance(bullets, list):
        for item in bullets[1:4]:
            if isinstance(item, str):
                story_lines.append(item)
    story_font = _load_font(20)
    story_y = 420
    for line in story_lines[:2]:
        draw.rounded_rectangle(
            (96, story_y, 786, story_y + 42),
            radius=14,
            fill=(22, 18, 21),
            outline=(58, 40, 34),
            width=1,
        )
        draw.text((114, story_y + 11), line, font=story_font, fill=BONE)
        story_y += 54

    stats = recap.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}

    _draw_kicker(draw, x=860, y=94, text="Verdict board", accent=BRASS)
    team_font = _fit_font(
        draw, team, max_width=230, start_size=40, min_size=24, serif=True, bold=True
    )
    draw.text((860, 134), team, font=team_font, fill=EMBER)
    draw.text((860, 174), reason, font=_load_font(18, mono=True), fill=SMOKE)

    _draw_stat_card(
        draw, x=860, y=216, width=118, height=96, label="Day", value=str(day), accent=BRASS
    )
    _draw_stat_card(
        draw,
        x=992,
        y=216,
        width=118,
        height=96,
        label="Votes",
        value=str(int(stats.get("votes", 0))),
        accent=BONE,
    )
    _draw_stat_card(
        draw,
        x=860,
        y=326,
        width=118,
        height=96,
        label="Kills",
        value=str(int(stats.get("night_kills", 0))),
        accent=EMBER,
    )
    _draw_stat_card(
        draw,
        x=992,
        y=326,
        width=118,
        height=96,
        label="Outs",
        value=str(int(stats.get("eliminations", 0))),
        accent=MOSS,
    )

    turning_title, turning_reason = _turning_point(recap)
    _draw_panel(draw, (860, 438, 1110, 504), fill=(28, 17, 20), outline=(94, 55, 38), radius=18)
    draw.text((876, 452), "TURNING POINT", font=_load_font(14, bold=True), fill=EMBER)
    draw.text((876, 474), turning_title, font=_load_font(24, serif=True, bold=True), fill=BONE)
    draw.text((876, 500 - 10), turning_reason[:42], font=_load_font(15, mono=True), fill=SMOKE)

    _draw_footer(
        draw, visibility_label="spoiler reveal", footer_note=f"case {_match_ref(match_id)}"
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

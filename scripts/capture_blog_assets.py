#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import shutil
import socket
import subprocess
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont
import websockets


WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
DEMO_WIDTH = 1000
DEMO_HEIGHT = 625
SQUARE_SIZE = 1200
OBSIDIAN = "#09070a"
COAL = "#121016"
OXBLOOD = "#3a0f17"
GARNET = "#6b1625"
EMBER = "#c95a2a"
BRASS = "#b08a4a"
BONE = "#f3ecdf"
SMOKE = "#b9b2aa"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture blog-launch assets from a live local HowlHouse app.")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="Frontend base URL.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend API base URL.")
    parser.add_argument("--match-id", required=True, help="Finished match ID to feature.")
    parser.add_argument(
        "--output-dir",
        default="docs/launch",
        help="Directory for generated assets. Temporary capture frames stay in a hidden subdirectory and are deleted.",
    )
    parser.add_argument(
        "--chrome-path",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        help="Chrome executable path for CDP capture.",
    )
    return parser.parse_args()


def http_json(url: str, *, method: str = "GET", data: bytes | None = None, timeout: float = 10.0) -> Any:
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_bytes(url: str, *, timeout: float = 20.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def wait_for_http(url: str, *, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2.0):
                return
        except (HTTPError, URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def reserve_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


class ChromeCaptureSession:
    def __init__(self, chrome_path: str) -> None:
        self.chrome_path = chrome_path
        self.remote_port = reserve_port()
        self.user_data_dir = Path(tempfile.mkdtemp(prefix="howlhouse-blog-cdp-"))
        self.proc: subprocess.Popen[str] | None = None
        self.ws: websockets.asyncio.client.ClientConnection | None = None
        self.message_id = 0

    async def __aenter__(self) -> "ChromeCaptureSession":
        command = [
            self.chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--remote-debugging-port={self.remote_port}",
            f"--user-data-dir={self.user_data_dir}",
            f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
            "about:blank",
        ]
        self.proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        target = await self._wait_for_target()
        self.ws = await websockets.connect(target["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        shutil.rmtree(self.user_data_dir, ignore_errors=True)

    async def _wait_for_target(self) -> dict[str, Any]:
        deadline = time.time() + 15.0
        version_url = f"http://127.0.0.1:{self.remote_port}/json/list"
        while time.time() < deadline:
            try:
                targets = http_json(version_url, timeout=1.0)
            except Exception:
                await asyncio.sleep(0.25)
                continue
            page_targets = [target for target in targets if target.get("type") == "page"]
            if page_targets:
                return page_targets[0]
            await asyncio.sleep(0.25)
        raise RuntimeError("Chrome DevTools target did not become ready")

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("CDP websocket is not connected")
        self.message_id += 1
        message_id = self.message_id
        payload = {"id": message_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await self.ws.recv()
            message = json.loads(raw)
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP error for {method}: {message['error']}")
            return message.get("result", {})

    async def wait_for(self, predicate_js: str, *, timeout: float = 20.0, interval: float = 0.25) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = await self.evaluate(predicate_js)
            if result:
                return
            await asyncio.sleep(interval)
        raise RuntimeError(f"Timed out waiting for browser predicate: {predicate_js}")

    async def evaluate(self, expression: str) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        return result.get("result", {}).get("value")

    async def navigate(self, url: str) -> None:
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(1.25)

    async def screenshot(self, path: Path) -> None:
        data = await self.send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        path.write_bytes(base64.b64decode(data["data"]))


def resize_for_demo(image: Image.Image) -> Image.Image:
    resized = image.resize((DEMO_WIDTH, DEMO_HEIGHT), Image.Resampling.LANCZOS)
    return resized.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)


def gradient_background(size: int) -> Image.Image:
    background = Image.new("RGB", (size, size), OBSIDIAN)
    draw = ImageDraw.Draw(background)
    top = ImageColor.getrgb(COAL)
    bottom = ImageColor.getrgb(OBSIDIAN)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(int(top[i] * (1.0 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, size, y), fill=color)

    ember_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(ember_glow)
    glow_draw.ellipse((40, 80, 560, 600), fill=ImageColor.getrgb(EMBER) + (120,))
    glow_draw.ellipse((700, 10, 1180, 490), fill=ImageColor.getrgb(GARNET) + (120,))
    ember_glow = ember_glow.filter(ImageFilter.GaussianBlur(100))
    background = Image.alpha_composite(background.convert("RGBA"), ember_glow).convert("RGB")

    brass_lines = ImageDraw.Draw(background)
    brass = ImageColor.getrgb(BRASS)
    brass_lines.rounded_rectangle((34, 34, size - 34, size - 34), radius=42, outline=brass, width=2)
    brass_lines.arc((860, 70, 1110, 320), start=210, end=40, fill=brass, width=3)
    brass_lines.arc((888, 98, 1082, 292), start=215, end=35, fill=brass, width=1)
    return background


def draw_chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont) -> int:
    padding_x = 18
    padding_y = 10
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = (right - left) + padding_x * 2
    height = (bottom - top) + padding_y * 2
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, outline=ImageColor.getrgb(BRASS), width=2, fill=ImageColor.getrgb(COAL))
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=ImageColor.getrgb(BONE))
    return x + width + 14


def create_square_asset(
    share_card_bytes: bytes,
    recap: dict[str, Any],
    output_path: Path,
) -> None:
    canvas = gradient_background(SQUARE_SIZE).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    display_font = load_font("/System/Library/Fonts/Supplemental/BigCaslon.ttf", 76)
    title_font = load_font("/System/Library/Fonts/SFNS.ttf", 29)
    body_font = load_font("/System/Library/Fonts/SFNS.ttf", 25)
    mono_font = load_font("/System/Library/Fonts/SFNSMono.ttf", 22)
    chip_font = load_font("/System/Library/Fonts/SFNS.ttf", 21)

    draw.text((84, 90), "HowlHouse", font=display_font, fill=ImageColor.getrgb(BONE))
    draw.text((88, 176), "Cinematic spectator room for deterministic AI Werewolf", font=title_font, fill=ImageColor.getrgb(SMOKE))
    draw.multiline_text(
        (88, 240),
        "Mystery-safe viewing, dramatic irony, replay-backed recaps,\nand social artifacts captured from the real table.",
        font=body_font,
        fill=ImageColor.getrgb(BONE),
        spacing=10,
    )

    chip_x = 88
    chip_y = 356
    chip_x = draw_chip(draw, chip_x, chip_y, f"Winner {str(recap['winner']['team']).title()}", chip_font)
    chip_x = draw_chip(draw, chip_x, chip_y, f"{recap['stats']['days']} day replay", chip_font)
    draw_chip(draw, chip_x, chip_y, f"{recap['stats']['public_messages']} public messages", chip_font)

    card = Image.open(BytesIO(share_card_bytes)).convert("RGBA")
    card.thumbnail((1020, 535), Image.Resampling.LANCZOS)
    frame_x = (SQUARE_SIZE - card.width) // 2
    frame_y = 500

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (frame_x - 12, frame_y - 12, frame_x + card.width + 12, frame_y + card.height + 12),
        radius=34,
        fill=(0, 0, 0, 130),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (frame_x - 18, frame_y - 18, frame_x + card.width + 18, frame_y + card.height + 18),
        radius=36,
        outline=ImageColor.getrgb(BRASS),
        width=2,
        fill=(9, 7, 10, 205),
    )
    canvas.alpha_composite(card, (frame_x, frame_y))

    footer_y = 1090
    draw.line((84, footer_y, 1116, footer_y), fill=ImageColor.getrgb(BRASS), width=2)
    draw.text((88, footer_y + 18), "Flagship replay captured from the live app", font=mono_font, fill=ImageColor.getrgb(SMOKE))
    draw.text((860, footer_y + 18), "howl.house / launch", font=mono_font, fill=ImageColor.getrgb(BRASS))

    canvas.convert("RGB").save(output_path, format="PNG")


async def capture_demo_frames(args: argparse.Namespace, frame_dir: Path) -> list[tuple[Path, int]]:
    frames: list[tuple[Path, int]] = []
    home_url = args.base_url.rstrip("/")

    async with ChromeCaptureSession(args.chrome_path) as chrome:
        await chrome.navigate(home_url)
        await chrome.wait_for(
            f"(() => Boolean(document.querySelector('a[href=\"/matches/{args.match_id}\"]')))()",
            timeout=20.0,
        )

        home_path = frame_dir / "01-home.png"
        await chrome.screenshot(home_path)
        frames.append((home_path, 1800))

        await chrome.evaluate(
            f"""(() => {{
                const link = document.querySelector('a[href="/matches/{args.match_id}"]');
                if (!link) {{
                  throw new Error('Featured match link not found');
                }}
                link.click();
                return true;
            }})()"""
        )
        await chrome.wait_for(
            f"(() => location.pathname === '/matches/{args.match_id}' && Boolean(document.querySelector('.transcript-panel')))()",
            timeout=20.0,
        )
        await chrome.wait_for(
            "(() => Boolean(document.querySelector('.share-card') && document.querySelector('.share-card').complete))()",
            timeout=20.0,
        )

        mystery_path = frame_dir / "02-viewer-mystery.png"
        await chrome.screenshot(mystery_path)
        frames.append((mystery_path, 2200))

        await chrome.evaluate(
            """(() => {
                const target = Array.from(document.querySelectorAll('button')).find((button) =>
                  button.textContent && button.textContent.includes('Dramatic Irony')
                );
                if (!target) {
                  throw new Error('Dramatic Irony toggle not found');
                }
                target.click();
                return true;
            })()"""
        )
        await chrome.wait_for(
            """(() => {
                const shareCard = document.querySelector('.share-card');
                return Boolean(shareCard && shareCard.getAttribute('src') && shareCard.getAttribute('src').includes('visibility=spoilers'));
            })()""",
            timeout=20.0,
        )
        await asyncio.sleep(1.0)

        irony_path = frame_dir / "03-viewer-irony.png"
        await chrome.screenshot(irony_path)
        frames.append((irony_path, 2400))

        for index, scroll_target in enumerate((360, 860), start=4):
            await chrome.evaluate(f"window.scrollTo({{ top: {scroll_target}, behavior: 'instant' }}); true;")
            await asyncio.sleep(0.55)
            scroll_path = frame_dir / f"{index:02d}-viewer-scroll.png"
            await chrome.screenshot(scroll_path)
            frames.append((scroll_path, 1100))

        await chrome.evaluate(
            """(() => {
                const recap = document.querySelector('.recap-stage');
                if (!recap) {
                  throw new Error('Recap stage not found');
                }
                const top = recap.getBoundingClientRect().top + window.scrollY - 48;
                window.scrollTo({ top, behavior: 'instant' });
                return true;
            })()"""
        )
        await asyncio.sleep(0.7)
        await chrome.wait_for(
            "(() => Boolean(document.querySelector('.recap-stage .share-card') && document.querySelector('.recap-stage .share-card').complete))()",
            timeout=20.0,
        )

        recap_path = frame_dir / "06-recap-share-card.png"
        await chrome.screenshot(recap_path)
        frames.append((recap_path, 2600))

    return frames


def save_demo_gif(frame_specs: list[tuple[Path, int]], output_path: Path) -> None:
    frames = [resize_for_demo(Image.open(path).convert("RGB")) for path, _duration in frame_specs]
    durations = [duration for _path, duration in frame_specs]
    first, *rest = frames
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = output_dir / ".tmp-blog-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    wait_for_http(args.base_url.rstrip("/"))
    wait_for_http(f"{args.api_url.rstrip('/')}/healthz")

    recap = http_json(f"{args.api_url.rstrip('/')}/matches/{quote(args.match_id)}/recap?visibility=public")
    share_card_bytes = http_bytes(f"{args.api_url.rstrip('/')}/matches/{quote(args.match_id)}/share-card?visibility=public")

    if not share_card_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Share-card endpoint did not return PNG bytes")

    frames = asyncio.run(capture_demo_frames(args, frame_dir))
    gif_path = output_dir / "howlhouse-demo.gif"
    save_demo_gif(frames, gif_path)

    square_path = output_dir / "howlhouse-square-social.png"
    create_square_asset(share_card_bytes, recap, square_path)

    shutil.rmtree(frame_dir, ignore_errors=True)
    print(gif_path)
    print(square_path)


if __name__ == "__main__":
    main()

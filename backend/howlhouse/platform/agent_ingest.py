from __future__ import annotations

import hashlib
import io
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

STRATEGY_HEADER_PATTERN = re.compile(r"^\s*##\s+HowlHouse Strategy\s*$", re.IGNORECASE)
ANY_H2_HEADER_PATTERN = re.compile(r"^\s*##\s+")


@dataclass(frozen=True)
class IngestedAgentPackage:
    agent_id: str
    package_path: str
    entrypoint: str
    strategy_text: str


def extract_strategy_section(markdown_text: str, *, max_chars: int = 10_000) -> str:
    lines = markdown_text.splitlines()
    start_index: int | None = None

    for index, line in enumerate(lines):
        if STRATEGY_HEADER_PATTERN.match(line):
            start_index = index + 1
            break

    if start_index is None:
        raise ValueError("AGENT.md must include a '## HowlHouse Strategy' section")

    end_index = len(lines)
    for index in range(start_index, len(lines)):
        if ANY_H2_HEADER_PATTERN.match(lines[index]):
            end_index = index
            break

    strategy_text = "\n".join(lines[start_index:end_index]).strip()
    if not strategy_text:
        raise ValueError("HowlHouse Strategy section is empty")
    if len(strategy_text) > max_chars:
        raise ValueError(f"HowlHouse Strategy section exceeds max length ({max_chars} chars)")
    return strategy_text


def _safe_extract_zip(
    *,
    zip_bytes: bytes,
    destination_dir: Path,
    max_extract_bytes: int,
) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
        total_size = 0

        if destination_dir.exists():
            shutil.rmtree(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_root = destination_dir.resolve()

        for info in zip_file.infolist():
            name = info.filename
            path_in_zip = PurePosixPath(name)

            if path_in_zip.is_absolute() or ".." in path_in_zip.parts:
                raise ValueError(f"Unsafe archive path: {name}")

            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Symlink entries are not allowed: {name}")

            total_size += int(info.file_size)
            if total_size > max_extract_bytes:
                raise ValueError(f"Extracted archive exceeds max size ({max_extract_bytes} bytes)")

            if info.is_dir():
                continue

            relative_path = Path(*path_in_zip.parts)
            target_path = (destination_root / relative_path).resolve()
            if destination_root not in target_path.parents and target_path != destination_root:
                raise ValueError(f"Unsafe extraction target for path: {name}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info, "r") as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def ingest_agent_package(
    *,
    zip_bytes: bytes,
    data_dir: Path,
    max_zip_bytes: int,
    max_extract_bytes: int,
    strategy_max_chars: int,
) -> IngestedAgentPackage:
    if not zip_bytes:
        raise ValueError("Uploaded package is empty")
    if len(zip_bytes) > max_zip_bytes:
        raise ValueError(f"Uploaded package exceeds max size ({max_zip_bytes} bytes)")

    digest = hashlib.sha256(zip_bytes).hexdigest()
    agent_id = f"agent_{digest[:16]}"
    package_dir = (data_dir / "agents" / agent_id).resolve()

    try:
        _safe_extract_zip(
            zip_bytes=zip_bytes,
            destination_dir=package_dir,
            max_extract_bytes=max_extract_bytes,
        )

        entrypoint_path = package_dir / "agent.py"
        strategy_path = package_dir / "AGENT.md"

        if not entrypoint_path.is_file():
            raise ValueError("Agent package must include required file: agent.py")
        if not strategy_path.is_file():
            raise ValueError("Agent package must include required file: AGENT.md")

        strategy_markdown = strategy_path.read_text(encoding="utf-8")
        strategy_text = extract_strategy_section(
            strategy_markdown,
            max_chars=strategy_max_chars,
        )
    except Exception:
        if package_dir.exists():
            shutil.rmtree(package_dir)
        raise

    return IngestedAgentPackage(
        agent_id=agent_id,
        package_path=str(package_dir),
        entrypoint="agent.py",
        strategy_text=strategy_text,
    )

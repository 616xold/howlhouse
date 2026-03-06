from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class _MatchChannel:
    history: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    closed: bool = False


class EventBus:
    def __init__(self):
        self._channels: dict[str, _MatchChannel] = {}

    def subscribe(self, match_id: str) -> tuple[list[str], asyncio.Queue[str | None]]:
        channel = self._channels.setdefault(match_id, _MatchChannel())
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        channel.subscribers.add(queue)
        if channel.closed:
            queue.put_nowait(None)
        return list(channel.history), queue

    def unsubscribe(self, match_id: str, queue: asyncio.Queue[str | None]) -> None:
        channel = self._channels.get(match_id)
        if channel is None:
            return
        channel.subscribers.discard(queue)

    def publish(self, match_id: str, event_json: str) -> None:
        channel = self._channels.setdefault(match_id, _MatchChannel())
        if channel.closed:
            return
        channel.history.append(event_json)
        for queue in list(channel.subscribers):
            queue.put_nowait(event_json)

    def close(self, match_id: str) -> None:
        channel = self._channels.setdefault(match_id, _MatchChannel())
        if channel.closed:
            return
        channel.closed = True
        for queue in list(channel.subscribers):
            queue.put_nowait(None)

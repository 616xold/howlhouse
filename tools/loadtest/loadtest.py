#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Stats:
    health_ok: int = 0
    matches_created: int = 0
    matches_run: int = 0
    list_ok: int = 0
    failures: int = 0


def _request_json(
    *,
    method: str,
    url: str,
    payload: dict | None = None,
    timeout_s: float = 10.0,
):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=timeout_s) as response:
        body = response.read().decode("utf-8")
        if not body.strip():
            return {}
        return json.loads(body)


def _worker(
    *,
    worker_index: int,
    base_url: str,
    iterations: int,
    run_matches: bool,
    base_seed: int,
    timeout_s: float,
    shared: Stats,
    lock: threading.Lock,
) -> None:
    local = Stats()

    for index in range(iterations):
        seed = base_seed + (worker_index * 10_000) + index
        try:
            _request_json(method="GET", url=f"{base_url}/healthz", timeout_s=timeout_s)
            local.health_ok += 1

            created = _request_json(
                method="POST",
                url=f"{base_url}/matches",
                payload={"seed": seed, "agent_set": "scripted"},
                timeout_s=timeout_s,
            )
            local.matches_created += 1
            match_id = str(created.get("match_id", ""))
            if not match_id:
                raise RuntimeError("create match returned no match_id")

            if run_matches:
                _request_json(
                    method="POST",
                    url=f"{base_url}/matches/{match_id}/run?sync=true",
                    timeout_s=max(timeout_s, 30.0),
                )
                local.matches_run += 1

            _request_json(method="GET", url=f"{base_url}/matches", timeout_s=timeout_s)
            local.list_ok += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, RuntimeError):
            local.failures += 1

    with lock:
        shared.health_ok += local.health_ok
        shared.matches_created += local.matches_created
        shared.matches_run += local.matches_run
        shared.list_ok += local.list_ok
        shared.failures += local.failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HowlHouse baseline load test")
    parser.add_argument(
        "--base-url",
        default=os.getenv("HOWLHOUSE_LOAD_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("HOWLHOUSE_LOAD_CONCURRENCY", "1")),
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=int(os.getenv("HOWLHOUSE_LOAD_ITERATIONS", "3")),
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=int(os.getenv("HOWLHOUSE_LOAD_BASE_SEED", "10000")),
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("HOWLHOUSE_LOAD_TIMEOUT_S", "10")),
    )
    parser.add_argument(
        "--run-matches",
        action="store_true",
        default=os.getenv("HOWLHOUSE_LOAD_RUN_MATCHES", "false").lower() == "true",
        help="also run created matches synchronously",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.concurrency <= 0:
        raise SystemExit("concurrency must be > 0")
    if args.iterations <= 0:
        raise SystemExit("iterations must be > 0")

    base_url = args.base_url.rstrip("/")
    started = time.perf_counter()

    stats = Stats()
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    for worker_index in range(args.concurrency):
        thread = threading.Thread(
            target=_worker,
            kwargs={
                "worker_index": worker_index,
                "base_url": base_url,
                "iterations": args.iterations,
                "run_matches": args.run_matches,
                "base_seed": args.base_seed,
                "timeout_s": args.timeout_s,
                "shared": stats,
                "lock": lock,
            },
            daemon=False,
            name=f"loadtest-worker-{worker_index}",
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    duration_s = time.perf_counter() - started
    print(
        json.dumps(
            {
                "duration_s": round(duration_s, 3),
                "concurrency": args.concurrency,
                "iterations": args.iterations,
                "run_matches": args.run_matches,
                "health_ok": stats.health_ok,
                "matches_created": stats.matches_created,
                "matches_run": stats.matches_run,
                "list_ok": stats.list_ok,
                "failures": stats.failures,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if stats.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

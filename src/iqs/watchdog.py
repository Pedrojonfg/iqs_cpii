from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class WatchdogConfig:
    heartbeat_path: str
    heartbeat_stale_s: float
    check_every_s: float
    restart_backoff_s: float
    startup_grace_s: float


def _heartbeat_age_seconds(path: str) -> float | None:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    return time.time() - mtime


def _terminate_process(proc: subprocess.Popen[object], timeout_s: float = 10.0) -> None:
    if proc.poll() is not None:
        return

    try:
        proc.send_signal(signal.SIGTERM)
    except OSError:
        return

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)

    try:
        proc.kill()
    except OSError:
        return


def run_watchdog(config: WatchdogConfig) -> int:
    env = dict(os.environ)
    env["IQS_HEARTBEAT_PATH"] = config.heartbeat_path

    while True:
        # Always use current interpreter/venv.
        cmd = [sys.executable, "-m", "iqs.main"]
        proc = subprocess.Popen(cmd, env=env)

        started = time.time()
        last_restart_reason = "unknown"

        while True:
            exit_code = proc.poll()
            if exit_code is not None:
                last_restart_reason = f"process exited with code {exit_code}"
                break

            # Give the child time to start and emit first heartbeat.
            if time.time() - started < config.startup_grace_s:
                time.sleep(config.check_every_s)
                continue

            age = _heartbeat_age_seconds(config.heartbeat_path)
            if age is None:
                # Heartbeat file missing: treat as stale after grace.
                last_restart_reason = "heartbeat missing"
                _terminate_process(proc)
                break

            if age > config.heartbeat_stale_s:
                last_restart_reason = f"heartbeat stale (age={age:.1f}s)"
                _terminate_process(proc)
                break

            time.sleep(config.check_every_s)

        # Backoff before restarting to avoid hot loops.
        time.sleep(config.restart_backoff_s)
        # Keep looping (restart).
        _ = last_restart_reason


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple Python watchdog for iqs.main")
    parser.add_argument(
        "--heartbeat-path",
        default=os.getenv("IQS_HEARTBEAT_PATH", ".iqs_heartbeat"),
        help="Path to heartbeat file used to detect hangs.",
    )
    parser.add_argument(
        "--stale-seconds",
        type=float,
        default=180.0,
        help="Restart if heartbeat file is older than this many seconds.",
    )
    parser.add_argument(
        "--check-every",
        type=float,
        default=2.0,
        help="How often to check process/heartbeat (seconds).",
    )
    parser.add_argument(
        "--restart-backoff",
        type=float,
        default=5.0,
        help="How long to wait before restarting after a failure (seconds).",
    )
    parser.add_argument(
        "--startup-grace",
        type=float,
        default=30.0,
        help="How long to ignore missing/stale heartbeat right after start (seconds).",
    )
    args = parser.parse_args()

    cfg = WatchdogConfig(
        heartbeat_path=args.heartbeat_path,
        heartbeat_stale_s=args.stale_seconds,
        check_every_s=args.check_every,
        restart_backoff_s=args.restart_backoff,
        startup_grace_s=args.startup_grace,
    )
    run_watchdog(cfg)


if __name__ == "__main__":
    main()


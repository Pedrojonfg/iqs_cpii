from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _streamlit_cmd(*, port: int, headless: bool) -> list[str]:
    # Run from repo root so relative paths in UI keep working.
    app = str((_repo_root() / "ui" / "app.py").as_posix())
    cmd = [sys.executable, "-m", "streamlit", "run", app, "--server.port", str(port)]
    cmd += ["--server.headless", "true" if headless else "false"]
    return cmd


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
        return True


def _pick_free_port(preferred: int, *, max_tries: int = 50) -> int:
    port = int(preferred)
    for _ in range(max_tries):
        if _is_port_free(port):
            return port
        port += 1
    raise RuntimeError(f"Could not find a free port starting at {preferred} (tried {max_tries} ports).")


def _runner_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "ui.demo_runner",
        "--mode",
        str(args.mode),
        "--symbol",
        str(args.symbol),
        "--days-back",
        str(int(args.days_back)),
        "--seconds",
        str(float(args.seconds)),
    ]
    if float(args.bucket_volume) > 0:
        cmd += ["--bucket-volume", str(float(args.bucket_volume))]
    if args.run_coldpath:
        cmd += ["--run-coldpath"]
    if args.run_hotpath:
        cmd += ["--run-hotpath"]
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="One-command IQS demo: start UI + run the didactic pipeline.")
    parser.add_argument("--mode", choices=["synthetic", "ib"], default="synthetic")
    parser.add_argument("--symbol", default="AAA")
    parser.add_argument("--days-back", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--bucket-volume", type=float, default=0.0)
    parser.add_argument("--run-coldpath", action="store_true", default=True)
    parser.add_argument("--run-hotpath", action="store_true", default=True)
    parser.add_argument("--ui-port", type=int, default=int(os.getenv("IQS_UI_PORT", "8501")))
    parser.add_argument("--ui-headless", action="store_true", help="Don't auto-open a browser (recommended on WSL/servers).")
    args = parser.parse_args()

    root = _repo_root()

    ui_proc: subprocess.Popen[object] | None = None
    runner_proc: subprocess.Popen[object] | None = None

    try:
        ui_port = _pick_free_port(int(args.ui_port))
        if ui_port != int(args.ui_port):
            print(f"Port {args.ui_port} is busy. Using {ui_port} instead.")
        ui_cmd = _streamlit_cmd(port=int(ui_port), headless=bool(args.ui_headless))
        ui_proc = subprocess.Popen(ui_cmd, cwd=str(root))
        time.sleep(1.0)

        runner_cmd = _runner_cmd(args)
        runner_proc = subprocess.Popen(runner_cmd, cwd=str(root))

        # Wait for the runner to finish; keep UI alive for viewing results.
        exit_code = runner_proc.wait()
        if exit_code != 0:
            raise SystemExit(exit_code)

        # Keep UI running until user interrupts.
        print(f"Demo completed. UI is still running on port {ui_port}. Press Ctrl+C to stop.")
        while True:
            time.sleep(0.5)
            if ui_proc.poll() is not None:
                raise SystemExit(ui_proc.returncode or 0)
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful teardown.
        for proc in (runner_proc, ui_proc):
            if proc is None:
                continue
            if proc.poll() is not None:
                continue
            try:
                proc.send_signal(signal.SIGTERM)
            except OSError:
                continue
        time.sleep(0.5)
        for proc in (runner_proc, ui_proc):
            if proc is None:
                continue
            if proc.poll() is not None:
                continue
            try:
                proc.kill()
            except OSError:
                continue


if __name__ == "__main__":
    main()


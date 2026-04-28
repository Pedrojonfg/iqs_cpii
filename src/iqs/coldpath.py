from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from ib_insync import IB

from iqs.broker import BrokerData
from iqs.calibrator import DataCalibrator
from iqs.instruments import Instrument


def _required_env(name: str) -> str:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v.strip()


def _required_int_env(name: str) -> int:
    raw = _required_env(name)
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(f"Environment variable {name} must be an integer, got: {raw!r}") from e


def _parse_symbols(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _default_universe() -> list[Instrument]:
    # Keep the cold path independent from trading code, but provide a sensible default.
    return [
        Instrument(symbol="AIR", exchange="CHIX", currency="EUR"),
        Instrument(symbol="HO", exchange="CHIX", currency="EUR"),
        Instrument(symbol="SAF", exchange="CHIX", currency="EUR"),
        Instrument(symbol="AM", exchange="CHIX", currency="EUR"),
        Instrument(symbol="RHM", exchange="CHIX", currency="EUR"),
        Instrument(symbol="HAG", exchange="CHIX", currency="EUR"),
        Instrument(symbol="MTX", exchange="CHIX", currency="EUR"),
        Instrument(symbol="RENK", exchange="CHIX", currency="EUR"),
        Instrument(symbol="BA.", exchange="CHIX", currency="GBP"),
        Instrument(symbol="RR.", exchange="CHIX", currency="GBP"),
        Instrument(symbol="QQQ.", exchange="CHIX", currency="GBP"),
        Instrument(symbol="CHG", exchange="CHIX", currency="GBP"),
        Instrument(symbol="BAB", exchange="CHIX", currency="GBP"),
        Instrument(symbol="LDO", exchange="CHIX", currency="EUR"),
        Instrument(symbol="SAAB-B", exchange="CHIX", currency="SEK"),
        Instrument(symbol="IDR", exchange="CHIX", currency="EUR"),
        Instrument(symbol="KOG", exchange="CHIX", currency="NOK"),
    ]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


async def _run_cold_path(*, symbols: list[str], days_back: int, out_dir: Path) -> Path:
    load_dotenv()

    ib_host = _required_env("IB_HOST")
    ib_port = _required_int_env("IB_PORT")
    ib_client_id = _required_int_env("IB_CLIENT_ID")

    ib = IB()
    await ib.connectAsync(ib_host, ib_port, clientId=ib_client_id)
    try:
        broker = BrokerData(ib)
        calibrator = DataCalibrator(broker)

        results: dict[str, int] = {}
        for sym in symbols:
            results[sym] = int(calibrator.coldpath(sym, days_back=days_back))

        now = dt.datetime.now(dt.timezone.utc)
        payload = {
            "generated_at_utc": now.isoformat(),
            "days_back": days_back,
            "bucket_volume_by_symbol": results,
        }

        _ensure_dir(out_dir)
        dated = out_dir / f"calibration_{now.date().isoformat()}.json"
        latest = out_dir / "calibration_latest.json"
        _write_json(dated, payload)
        _write_json(latest, payload)
        return latest
    finally:
        ib.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="IQS cold path: daily volume-bar bucket calibration.")
    parser.add_argument(
        "--days-back",
        type=int,
        default=int(os.getenv("IQS_COLDPATH_DAYS_BACK", "5")),
        help="How many days of historical ticks to use (default from IQS_COLDPATH_DAYS_BACK).",
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("IQS_COLDPATH_SYMBOLS", ""),
        help="Comma-separated symbols to calibrate (default from IQS_COLDPATH_SYMBOLS).",
    )
    parser.add_argument(
        "--out-dir",
        default=os.getenv("IQS_COLDPATH_OUT_DIR", "data/calibration"),
        help="Directory to write calibration files (default data/calibration).",
    )
    args = parser.parse_args()

    if args.symbols.strip():
        symbols = _parse_symbols(args.symbols)
    else:
        symbols = [i.symbol for i in _default_universe()]

    if args.days_back <= 0:
        raise SystemExit("--days-back must be > 0")

    out_dir = Path(args.out_dir).resolve()
    path = asyncio.run(_run_cold_path(symbols=symbols, days_back=int(args.days_back), out_dir=out_dir))
    print(str(path))


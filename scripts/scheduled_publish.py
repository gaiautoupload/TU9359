from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from update_dashboard import HISTORY, OUTPUT, PRICE_FILE, ROOT, build_payload, update_history


TAIPEI = ZoneInfo("Asia/Taipei")
TRACKED_PATHS = ("data/9359_daily_history.csv", "docs/data/dashboard.json")
PUBLIC_DATA_URL = "https://gaiautoupload.github.io/TU9359/data/dashboard.json"
RETRY_MINUTES = 10
LAST_RETRY_HOUR = 19


class SourceNotReady(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), *args],
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def latest_price_session(prices: pd.DataFrame) -> str:
    prices.columns = prices.columns.astype(str)
    anchor = "0050" if "0050" in prices.columns else prices.columns[0]
    valid = prices.index[prices[anchor].notna()]
    if valid.empty:
        raise RuntimeError("Price file contains no valid trading session")
    return pd.Timestamp(valid.max()).date().isoformat()


def validate_payload(history: pd.DataFrame, prices: pd.DataFrame, expected_date: str) -> None:
    saved = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if str(history["date"].astype(str).max()) != expected_date:
        raise RuntimeError("History latest session does not match the price source")
    if saved.get("latest_session") != expected_date:
        raise RuntimeError("Dashboard latest session does not match the price source")
    expected = build_payload(history.copy(), prices)
    if saved.get("windows") != [1, 3, 5, 10, 20]:
        raise RuntimeError("Dashboard windows are incomplete")
    if saved.get("stocks") != expected.get("stocks"):
        raise RuntimeError("Dashboard statistics, inventory, cost, or return validation failed")
    index_path = ROOT / "docs" / "index.html"
    app_path = ROOT / "docs" / "assets" / "app.js"
    if (
        not index_path.is_file()
        or "assets/app.js" not in index_path.read_text(encoding="utf-8")
        or not app_path.is_file()
        or "data/dashboard.json" not in app_path.read_text(encoding="utf-8")
    ):
        raise RuntimeError("Static entry does not reference data/dashboard.json")


def publish_and_verify(session_date: str) -> None:
    git("fetch", "origin", "main")
    counts = git("rev-list", "--left-right", "--count", "origin/main...main").stdout.split()
    remote_ahead, local_ahead = map(int, counts)
    if remote_ahead:
        raise RuntimeError("origin/main has commits not present locally; manual reconciliation required")
    if local_ahead:
        pushed = git("push", "origin", "main")
        print((pushed.stdout + pushed.stderr).strip(), flush=True)

    for attempt in range(20):
        try:
            response = requests.get(PUBLIC_DATA_URL, params={"check": str(time.time_ns())}, timeout=15)
            response.raise_for_status()
            if response.json().get("latest_session") == session_date:
                print(f"VERIFIED PUBLIC: {session_date}", flush=True)
                return
        except (requests.RequestException, ValueError) as exc:
            print(f"Public check {attempt + 1}/20: {exc}", flush=True)
        time.sleep(10)
    raise RuntimeError(f"Public site did not show {session_date} within verification window")


def main() -> int:
    now = datetime.now(TAIPEI)
    today = now.date().isoformat()
    prices = pd.read_pickle(PRICE_FILE)
    session_date = latest_price_session(prices)
    print(f"run_at={now.isoformat(timespec='seconds')} price_session={session_date}")

    if session_date != today:
        raise SourceNotReady(f"Price source is not ready for {today}; latest={session_date}")

    dirty = git("status", "--porcelain", "--", *TRACKED_PATHS).stdout.strip()
    if dirty:
        raise RuntimeError(f"Tracked data files have uncommitted changes:\n{dirty}")

    if HISTORY.exists() and OUTPUT.exists():
        current_history = pd.read_csv(HISTORY, dtype={"stock_id": str})
        current_payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if (
            str(current_history["date"].astype(str).max()) == session_date
            and current_payload.get("latest_session") == session_date
        ):
            validate_payload(current_history, prices, session_date)
            print(f"NO CHANGE: {session_date} is already generated locally", flush=True)
            publish_and_verify(session_date)
            return 0

    try:
        history = update_history(prices)
    except RuntimeError as exc:
        if "Broker source is not ready" in str(exc):
            raise SourceNotReady(str(exc)) from exc
        raise
    payload = build_payload(history.copy(), prices)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    validate_payload(history, prices, session_date)

    git("add", "--", *TRACKED_PATHS)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("NO CHANGE: generated files match the current commit")
    else:
        git("commit", "-m", f"Daily TU9359 update {session_date}")
    publish_and_verify(session_date)
    print(f"PUBLISHED: {session_date}")
    return 0


def run_with_retries() -> int:
    while True:
        try:
            return main()
        except SourceNotReady as exc:
            now = datetime.now(TAIPEI)
            cutoff = now.replace(hour=LAST_RETRY_HOUR, minute=0, second=0, microsecond=0)
            next_attempt = now + timedelta(minutes=RETRY_MINUTES)
            if next_attempt > cutoff:
                print(f"FAILED: {exc}; retry window ended at {cutoff.isoformat()}", file=sys.stderr, flush=True)
                return 1
            print(f"WAIT: {exc}; next attempt at {next_attempt.isoformat(timespec='seconds')}", flush=True)
            time.sleep(RETRY_MINUTES * 60)


if __name__ == "__main__":
    try:
        raise SystemExit(run_with_retries())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from update_dashboard import HISTORY, OUTPUT, PRICE_FILE, ROOT, build_payload, update_history


TAIPEI = ZoneInfo("Asia/Taipei")
TRACKED_PATHS = ("data/9359_daily_history.csv", "docs/data/dashboard.json")


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


def main() -> int:
    now = datetime.now(TAIPEI)
    today = now.date().isoformat()
    prices = pd.read_pickle(PRICE_FILE)
    session_date = latest_price_session(prices)
    print(f"run_at={now.isoformat(timespec='seconds')} price_session={session_date}")

    if session_date != today:
        print(f"SKIP: price source is not ready for {today}")
        return 0

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
            print(f"NO CHANGE: {session_date} is already published locally")
            return 0

    history = update_history(prices)
    payload = build_payload(history.copy(), prices)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    validate_payload(history, prices, session_date)

    git("add", "--", *TRACKED_PATHS)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("NO CHANGE: generated files match the current commit")
        return 0

    git("commit", "-m", f"Daily TU9359 update {session_date}")
    pushed = git("push", "origin", "main")
    if pushed.stdout.strip():
        print(pushed.stdout.strip())
    if pushed.stderr.strip():
        print(pushed.stderr.strip())
    print(f"PUBLISHED: {session_date}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

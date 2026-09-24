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
SITE_NAME = "TU9359｜上市櫃分點資金雷達"
REGISTRY = ROOT.parent / "WEBSITE_REGISTRY.md"
UPDATE_LOG = ROOT.parent / "WEBSITE_UPDATE_LOG.md"


class SourceNotReady(RuntimeError):
    pass


def record_site_result(status: str, note: str) -> None:
    stamp = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    latest = json.loads(OUTPUT.read_text(encoding="utf-8"))["latest_session"] if OUTPUT.exists() else "待補"
    lines = REGISTRY.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"| {SITE_NAME} |"):
            columns = line.split("|")
            columns[6] = f" {latest} "
            if status == "完成":
                columns[7] = f" {stamp} "
            columns[8] = f" {'正常' if status == '完成' else '待檢查（更新失敗，詳見紀錄）'} "
            lines[index] = "|".join(columns)
            break
    else:
        raise RuntimeError(f"Site not found in {REGISTRY}")
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    event = "資料更新／已推送／公開驗證" if status == "完成" else "更新失敗"
    entry = f"| {stamp} | {SITE_NAME} | {event} | {latest} | {status} | 本機排程 | {note} |"
    content = UPDATE_LOG.read_text(encoding="utf-8")
    marker = "\n## 事件用語"
    if marker not in content:
        raise RuntimeError(f"Update log has no insertion marker: {UPDATE_LOG}")
    UPDATE_LOG.write_text(content.replace(marker, f"\n{entry}\n{marker}", 1), encoding="utf-8")


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
                record_site_result("完成", f"公開資料已核對至 {session_date}；分點資料到齊後由本機 BAT 更新。")
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
                record_site_result("失敗", f"資料至 {cutoff.strftime('%H:%M')} 仍未到齊：{exc}")
                return 1
            print(f"WAIT: {exc}; next attempt at {next_attempt.isoformat(timespec='seconds')}", flush=True)
            time.sleep(RETRY_MINUTES * 60)


if __name__ == "__main__":
    try:
        raise SystemExit(run_with_retries())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        try:
            record_site_result("失敗", str(exc).replace("|", "/"))
        except Exception as log_exc:
            print(f"FAILED to record site result: {log_exc}", file=sys.stderr)
        raise SystemExit(1)

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "9359_daily_history.csv"
OUTPUT = ROOT / "docs" / "data" / "dashboard.json"
PRICE_FILE = Path(r"C:\Users\pokem\Desktop\stock\stock_pkl\收盤價.pkl")
BASE_URL = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm?a=9300&b=9359"
WINDOWS = (1, 3, 5, 10, 20)
SEEDS = {"2449": "京元電子", "2303": "聯電", "6182": "合晶"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def repair_name(value: object) -> str:
    text = str(value).strip()
    try:
        return text.encode("latin1").decode("big5")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def parse_page(content: bytes) -> pd.DataFrame:
    soup = BeautifulSoup(content, "html.parser")
    cells = soup.find_all("td", class_=["t4t1", "t3n1"])
    rows: list[list[object]] = []
    i = 0
    while i < len(cells):
        if "t4t1" not in cells[i].get("class", []):
            i += 1
            continue
        script = cells[i].find("script")
        match = re.search(r"GenLink2stk\('AS(\d+)','([^']+)'\);", script.string or "") if script else None
        if not match or i + 3 >= len(cells):
            i += 1
            continue

        def number(offset: int) -> int:
            raw = cells[i + offset].get_text(strip=True).replace(",", "")
            try:
                return int(raw)
            except ValueError:
                return 0

        rows.append([match.group(1), repair_name(match.group(2)), number(1), number(2), number(3)])
        i += 4
    return pd.DataFrame(rows, columns=["stock_id", "stock_name", "buy", "sell", "net"])


def fetch_day(session: requests.Session, session_date: str) -> pd.DataFrame:
    views: dict[str, pd.DataFrame] = {}
    for mode in ("E", "B"):
        response = session.get(f"{BASE_URL}&c={mode}&e={session_date}&f={session_date}", timeout=30)
        response.raise_for_status()
        views[mode] = parse_page(response.content).drop_duplicates("stock_id").set_index("stock_id")
        time.sleep(0.15)

    lots = views["E"].rename(columns={"buy": "buy_lots", "sell": "sell_lots", "net": "net_lots"})
    money = views["B"].rename(columns={"buy": "gross_buy_twd", "sell": "gross_sell_twd", "net": "net_flow_twd"})
    frame = lots.join(money.drop(columns="stock_name"), how="outer")
    frame["stock_name"] = frame["stock_name"].fillna(money["stock_name"])
    numeric = ["buy_lots", "sell_lots", "net_lots", "gross_buy_twd", "gross_sell_twd", "net_flow_twd"]
    frame[numeric] = frame[numeric].fillna(0).astype(int)
    frame[["gross_buy_twd", "gross_sell_twd", "net_flow_twd"]] *= 1000
    frame = frame.reset_index()
    frame["stock_id"] = frame["stock_id"].astype(str).str.strip()
    frame["date"] = session_date
    for stock_id, name in SEEDS.items():
        frame.loc[frame["stock_id"] == stock_id, "stock_name"] = name
    return frame


def trading_dates(prices: pd.DataFrame, count: int = 20) -> list[str]:
    anchor = "0050" if "0050" in prices.columns else prices.columns[0]
    valid = prices.index[(prices.index <= pd.Timestamp.now().normalize()) & prices[anchor].notna()]
    return [value.date().isoformat() for value in valid[-count:]]


def update_history(prices: pd.DataFrame) -> pd.DataFrame:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    if HISTORY.exists():
        old = pd.read_csv(HISTORY, dtype={"stock_id": str})
    else:
        old = pd.DataFrame()
    existing = set(old["date"].astype(str)) if not old.empty else set()
    wanted = trading_dates(prices, 20)
    missing = [d for d in wanted if d not in existing]
    rows: list[pd.DataFrame] = []
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for session_date in missing:
            print(f"fetch {session_date}")
            rows.append(fetch_day(session, session_date))
    history = pd.concat([old, *rows], ignore_index=True) if rows or not old.empty else pd.DataFrame()
    if history.empty:
        raise RuntimeError("No branch data available")
    history = history[history["date"].astype(str).isin(wanted)]
    history = history.drop_duplicates(["date", "stock_id"], keep="last").sort_values(["date", "stock_id"])
    history.to_csv(HISTORY, index=False, encoding="utf-8-sig")
    return history


def price_for(prices: pd.DataFrame, session_date: str, stock_id: str) -> float | None:
    stamp = pd.Timestamp(session_date)
    if stamp not in prices.index or stock_id not in prices.columns:
        return None
    value = pd.to_numeric(pd.Series([prices.at[stamp, stock_id]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def inventory_summary(group: pd.DataFrame, prices: pd.DataFrame) -> dict:
    group = group.sort_values("date")
    quantity = 0
    cost_value = 0.0
    peak_quantity = 0
    for row in group.itertuples():
        buy_lots = max(int(row.buy_lots), 0)
        sell_lots = max(int(row.sell_lots), 0)
        if buy_lots:
            quantity += buy_lots
            cost_value += float(row.gross_buy_twd)
        if sell_lots and quantity:
            removed = min(sell_lots, quantity)
            average = cost_value / (quantity * 1000) if quantity else 0
            quantity -= removed
            cost_value -= removed * 1000 * average
        if quantity <= 0:
            quantity, cost_value = 0, 0.0
        peak_quantity = max(peak_quantity, quantity)
    latest_date = str(group["date"].max())
    stock_id = str(group["stock_id"].iloc[0])
    close = price_for(prices, latest_date, stock_id)
    if close is None:
        latest = group[group["date"] == latest_date]
        total_lots = int(latest["buy_lots"].sum() + latest["sell_lots"].sum())
        total_value = int(latest["gross_buy_twd"].sum() + latest["gross_sell_twd"].sum())
        close = round(total_value / (total_lots * 1000), 2) if total_lots else None
    average_cost = cost_value / (quantity * 1000) if quantity else None
    return_pct = ((close / average_cost) - 1) * 100 if close and average_cost else None
    return {
        "estimated_inventory_lots": int(quantity),
        "peak_inventory_lots": int(peak_quantity),
        "estimated_cost": round(average_cost, 2) if average_cost else None,
        "latest_close": close,
        "estimated_return_pct": round(return_pct, 2) if return_pct is not None else None,
    }


def build_payload(history: pd.DataFrame, prices: pd.DataFrame) -> dict:
    history["date"] = history["date"].astype(str)
    dates = sorted(history["date"].unique())
    latest = dates[-1]
    stock_meta = history.sort_values("date").groupby("stock_id")["stock_name"].last().to_dict()
    stock_ids = sorted(history["stock_id"].astype(str).unique())
    stocks: list[dict] = []
    for stock_id in stock_ids:
        group = history[history["stock_id"] == stock_id].copy()
        item = {"stock_id": stock_id, "stock_name": stock_meta.get(stock_id, "")}
        for window in WINDOWS:
            selected_dates = set(dates[-window:])
            period = group[group["date"].isin(selected_dates)]
            item[f"d{window}"] = {
                "buy_lots": int(period["buy_lots"].sum()),
                "sell_lots": int(period["sell_lots"].sum()),
                "net_lots": int(period["net_lots"].sum()),
                "gross_buy_twd": int(period["gross_buy_twd"].sum()),
                "gross_sell_twd": int(period["gross_sell_twd"].sum()),
                "net_flow_twd": int(period["net_flow_twd"].sum()),
            }
        item.update(inventory_summary(group, prices))
        item["is_seed"] = stock_id in SEEDS
        stocks.append(item)
    stocks.sort(key=lambda x: x["d20"]["net_flow_twd"], reverse=True)
    return {
        "broker_id": "9359",
        "broker_name": "華南永昌－中正",
        "latest_session": latest,
        "observed_from": dates[0],
        "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "windows": list(WINDOWS),
        "method_note": "庫存、成本與報酬從可觀察起始日推估；不包含起始日前部位。B 為千元金額、E 為張數。",
        "stocks": stocks,
    }


def main() -> None:
    prices = pd.read_pickle(PRICE_FILE)
    prices.columns = prices.columns.astype(str)
    history = update_history(prices)
    payload = build_payload(history, prices)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"latest={payload['latest_session']} stocks={len(payload['stocks'])} output={OUTPUT}")


if __name__ == "__main__":
    main()

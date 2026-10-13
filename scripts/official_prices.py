"""Date-checked official close cache, independent of the legacy price job."""
import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

CACHE = Path(__file__).resolve().parents[1] / 'data' / 'official_prices'


def normalize_date(value):
    digits = ''.join(c for c in str(value) if c.isdigit())
    if len(digits) == 7:
        digits = str(int(digits[:3]) + 1911) + digits[3:]
    return datetime.strptime(digits, '%Y%m%d').date().isoformat()


def number(value):
    try:
        result = float(str(value).replace(',', '').strip())
        return result if result > 0 else None
    except ValueError:
        return None


def parse_twse(text):
    prices = {}
    columns = None
    for row in csv.reader(io.StringIO(text.replace('=', ''))):
        if '證券代號' in row and '收盤價' in row:
            columns = row.index('證券代號'), row.index('收盤價')
            continue
        if columns and len(row) > max(columns):
            sid = row[columns[0]].strip()
            value = number(row[columns[1]])
            if sid.isalnum() and len(sid) == 4 and value is not None:
                prices[sid] = value
    if '0050' not in prices or len(prices) < 500:
        raise ValueError('TWSE price response incomplete')
    return prices


def parse_tpex(payload, day):
    if normalize_date(payload.get('date', '')) != day:
        raise ValueError('TPEx response date mismatch')
    table = payload['tables'][0]
    fields = table['fields']
    sid_idx, close_idx = fields.index('代號'), fields.index('收盤')
    prices = {}
    for row in table['data']:
        sid = str(row[sid_idx]).strip()
        value = number(row[close_idx])
        if sid.isalnum() and len(sid) == 4 and value is not None:
            prices[sid] = value
    if len(prices) < 400:
        raise ValueError('TPEx price response incomplete')
    return prices


def load_prices(price_file):
    prices = pd.read_pickle(price_file)
    prices.columns = prices.columns.astype(str)
    prices = prices[~prices.index.duplicated(keep='last')].copy()
    for path in sorted(CACHE.glob('????-??-??.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        closes = {sid: value for sid, value in payload['prices'].items() if len(sid) == 4}
        row = pd.DataFrame([closes], index=[pd.Timestamp(payload['date'])])
        prices = row.combine_first(prices)
    return prices.sort_index()


def ensure_prices(price_file, day):
    path = CACHE / f'{day}.json'
    if not path.exists():
        with requests.Session() as session:
            session.headers['User-Agent'] = 'Mozilla/5.0'
            stamp = day.replace('-', '')
            response = session.post('https://www.twse.com.tw/exchangeReport/MI_INDEX', params=dict(response='csv', date=stamp, type='ALL'), timeout=45)
            response.raise_for_status()
            if stamp not in response.headers.get('Content-Disposition', ''):
                raise ValueError('TWSE response date mismatch or not yet published')
            listed = parse_twse(response.content.decode('cp950'))
            response = session.post('https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php', timeout=45)
            response.raise_for_status()
            otc = parse_tpex(response.json(), day)
        payload = dict(date=day, fetched_at=datetime.now().astimezone().isoformat(), twse_count=len(listed), tpex_count=len(otc), prices={**listed, **otc})
        CACHE.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
        print(f'Official prices verified: {day}, TWSE={len(listed)}, TPEx={len(otc)}', flush=True)
    return load_prices(price_file)

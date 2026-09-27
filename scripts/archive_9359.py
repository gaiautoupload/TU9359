"""Archive the public branch ranking, preserving unknowns and raw evidence."""
import argparse
import gzip
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'data' / 'archive_9359'
URL = 'https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm'


def parse(content, day):
    soup = BeautifulSoup(content.decode('cp950', errors='replace'), 'html.parser')
    text = soup.get_text(' ', strip=True)
    shown = re.search(r'資料日期[：:]\s*(\d{8})', text)
    if not shown or shown.group(1) != day.replace('-', ''):
        raise ValueError('source date mismatch or absent')
    rows = []
    for cell in soup.select('td.t4t1'):
        script = cell.find('script')
        match = re.search(r"GenLink2stk\('AS([^']+)','([^']+)'", script.get_text() if script else '')
        if match:
            sid, name = match.groups()
        else:
            anchor = cell.find('a')
            match = re.search(r"Link2Stk\('([^']+)'", anchor.get('href', '') if anchor else '')
            if not match:
                continue
            sid = match.group(1)
            name = anchor.get_text(strip=True).removeprefix(sid)
        values = cell.find_next_siblings('td', limit=3)
        if len(values) != 3:
            raise ValueError('incomplete numeric columns')
        nums = [int(v.get_text(strip=True).replace(',', '')) for v in values]
        if nums[0] - nums[1] != nums[2]:
            raise ValueError('buy minus sell mismatch')
        rows.append((sid, name, *nums))
    return list(dict.fromkeys(rows))


def connect():
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ARCHIVE / '9359.sqlite', timeout=60)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS pages (
            day TEXT, mode TEXT, status TEXT, row_count INTEGER,
            sha256 TEXT, fetched_at TEXT, error TEXT, PRIMARY KEY(day,mode));
        CREATE TABLE IF NOT EXISTS ranking (
            day TEXT, mode TEXT, stock_id TEXT, stock_name TEXT,
            buy INTEGER, sell INTEGER, net INTEGER,
            PRIMARY KEY(day,mode,stock_id));
    ''')
    return db


def run(start, end):
    db = connect()
    session = requests.Session()
    session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'
    dates = pd.bdate_range(start, end)
    for i, stamp in enumerate(dates):
        day = stamp.date().isoformat()
        for mode in ('E', 'B'):
            found = db.execute('SELECT status FROM pages WHERE day=? AND mode=?', (day,mode)).fetchone()
            if found and (found[0] == 'ok' or (found[0] == 'empty' and day < datetime.now().date().isoformat())):
                continue
            error = None
            for attempt in range(3):
                try:
                    response = session.get(URL, params=dict(a='9300',b='9359',c=mode,e=day,f=day), timeout=30)
                    response.raise_for_status()
                    raw = response.content
                    raw_dir = ARCHIVE / 'raw' / day[:4]
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    with gzip.open(raw_dir / f'{day}_{mode}.html.gz', 'wb') as handle:
                        handle.write(raw)
                    rows = parse(raw, day)
                    with db:
                        db.execute('DELETE FROM ranking WHERE day=? AND mode=?', (day,mode))
                        db.executemany('INSERT INTO ranking VALUES(?,?,?,?,?,?,?)', [(day,mode,*row) for row in rows])
                        db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,?)', (day,mode,'ok' if rows else 'empty',len(rows),hashlib.sha256(raw).hexdigest(),datetime.now().isoformat(),None))
                    error = None
                    break
                except (requests.RequestException, ValueError) as exc:
                    error = str(exc)
                    if isinstance(exc, ValueError):
                        break
                    time.sleep(2 * (attempt+1))
            if error:
                with db:
                    db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,?)', (day,mode,'error',0,None,datetime.now().isoformat(),error))
                print(f'{day} {mode}: {error}', flush=True)
            time.sleep(.25)
        if i % 20 == 0 or i == len(dates)-1:
            print(f'{i+1}/{len(dates)} through {day}', flush=True)
    summary = dict(requested_start=start, requested_end=end, coverage='Public rankings only; absent rows are unknown, never zero.', modes={'E':'lots','B':'thousands TWD'}, pages=[dict(zip(['mode','status','count'],r)) for r in db.execute('SELECT mode,status,count(*) FROM pages GROUP BY mode,status')], observed_rows=db.execute('SELECT count(*) FROM ranking').fetchone()[0])
    (ARCHIVE / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    db.close()
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    args = parser.parse_args()
    run(args.start, args.end)

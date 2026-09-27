"""Retain old top-three stock rankings as independent, incomplete evidence."""
import sqlite3
from pathlib import Path
import pandas as pd
from archive_9359 import connect


def main():
    source = Path(r'C:\Users\pokem\Desktop\stock\stock_pkl\隔日衝占比')
    db = connect()
    db.execute('''CREATE TABLE IF NOT EXISTS local_top3 (
        day TEXT, stock_id TEXT, stock_name TEXT, side TEXT, rank INTEGER,
        net_lots INTEGER, source_file TEXT,
        PRIMARY KEY(day,stock_id,side))''')
    count = 0
    for path in sorted(source.glob('*.csv')):
        try:
            frame = pd.read_csv(path, dtype=str)
        except pd.errors.EmptyDataError:
            continue
        if not all(c in frame.columns for c in ('0','1','2','5','8','11','14','17')):
            continue
        raw_day = path.stem.split('_')[-1]
        day = pd.Timestamp(raw_day).date().isoformat()
        for column in ('2','5','8','11','14','17'):
            selected = frame[frame[column].fillna('').str.contains('華南永昌.*中正',regex=True)]
            side = 'buy' if int(column) < 11 else 'sell'
            rank = ((int(column)-2) % 9)//3+1
            rows = [(day,r['0'],r['1'],side,rank,int(r[str(int(column)+1)].replace(',','')),str(path)) for _,r in selected.iterrows()]
            with db:
                db.executemany('INSERT OR REPLACE INTO local_top3 VALUES(?,?,?,?,?,?,?)',rows)
            count += len(rows)
    print(f'Imported {count} partial-ranking observations; absence is UNKNOWN.')
    db.close()


if __name__ == '__main__':
    main()

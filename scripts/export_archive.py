"""Export observed ranks; missing units remain null for backtest consumers."""
import json
import sqlite3
import pandas as pd
from archive_9359 import ARCHIVE


def main():
    db = sqlite3.connect(f'file:{(ARCHIVE / "9359.sqlite").as_posix()}?mode=ro',uri=True)
    frame = pd.read_sql_query('''SELECT day AS date, stock_id, max(stock_name) stock_name,
        max(CASE WHEN mode='E' THEN buy END) buy_lots,
        max(CASE WHEN mode='E' THEN sell END) sell_lots,
        max(CASE WHEN mode='E' THEN net END) net_lots,
        max(CASE WHEN mode='B' THEN buy*1000 END) buy_twd,
        max(CASE WHEN mode='B' THEN sell*1000 END) sell_twd,
        max(CASE WHEN mode='B' THEN net*1000 END) net_twd
        FROM ranking GROUP BY day,stock_id ORDER BY day,stock_id''',db)
    for col in frame.columns[3:]:
        frame[col] = frame[col].astype('Int64')
    frame.to_csv(ARCHIVE / '9359_observed_daily.csv',index=False,encoding='utf-8-sig')
    pages = pd.read_sql_query('SELECT * FROM pages ORDER BY day,mode',db)
    pages.to_csv(ARCHIVE / 'source_audit.csv',index=False,encoding='utf-8-sig')
    has_local = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_top3'").fetchone()
    overlap, agreeing = db.execute("SELECT count(*),sum(a.net=b.net_lots) FROM ranking a JOIN local_top3 b ON a.day=b.day AND a.stock_id=b.stock_id WHERE a.mode='E'").fetchone() if has_local else (0,0)
    report = dict(first_date=frame.date.min(),last_date=frame.date.max(),observed_days=int(frame.date.nunique()),observed_stocks=int(frame.stock_id.nunique()),observed_stock_days=len(frame),both_modes_stock_days=int(frame[['net_lots','net_twd']].notna().all(axis=1).sum()),source_pages=len(pages),unavailable_pages=int((pages.status!='ok').sum()),local_top3_rows=db.execute('SELECT count(*) FROM local_top3').fetchone()[0] if has_local else 0,overlap_rows=overlap,overlap_agreeing_rows=agreeing,coverage='Rankings only: omitted stock-days and missing modes are unknown, not zero.')
    (ARCHIVE / 'coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    db.close()


if __name__ == '__main__':
    main()

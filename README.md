# TU9359｜華南永昌－中正資金雷達

追蹤 9359 在上市櫃股票的每日買賣、1／3／5／10／20 交易日資金流、觀察期庫存、估算成本與報酬率。

## 更新資料

```powershell
python scripts/update_dashboard.py
```

## Windows 平日排程

安裝平日 17:30 的本機排程：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_schedule.ps1
```

排程會執行 `update_scheduled.bat`。只有當日收盤價與 9359 分點資料都到齊、產出驗證通過且內容改變時，才會提交並推送 `main`；執行紀錄存放在 `logs\update_YYYYMMDD.log`。

網站入口為 `docs/index.html`，產出資料為 `docs/data/dashboard.json`，逐日研究底稿保存在 `data/9359_daily_history.csv`。

公開網站：<https://gaiautoupload.github.io/TU9359/>

成本與庫存皆從本專案可觀察資料起點估算；若 9359 在起點前已有部位，網站會明確標示限制，不將估算值冒充券商真實庫存。

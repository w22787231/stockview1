# -*- coding: utf-8 -*-
"""NDX 12 個月前瞻本益比與 QQQ 收盤價 → data/ndx_forward_pe.json。

前瞻本益比採 History of Market 公開 API 的 Bloomberg BEst 市場共識序列；
QQQ 採 Yahoo Finance，並以每個估值觀測日當日或前一個交易日收盤價對齊。
若本次抓取失敗，保留線上 last-good 資料，避免部署時清空圖表。
"""
import datetime
import json
import os
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "ndx_forward_pe.json")
LIVE = "https://stockview1.pages.dev/data/ndx_forward_pe.json"
HOF_API = "https://historyofmarket.com/api/ndx/forward-pe.json"


def load_old():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        pass
    try:
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    except Exception as exc:
        print("[ndx_forward_pe] 無法讀取 last-good:", exc)
        return None


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))


def num(value, digits=2):
    try:
        value = float(value)
        return None if value != value else round(value, digits)
    except (TypeError, ValueError):
        return None


def build_live():
    payload = fetch_json(HOF_API)
    raw = payload.get("forward") or []
    pe = [(str(row.get("date", ""))[:10], num(row.get("value"))) for row in raw]
    pe = [(date, value) for date, value in pe if len(date) == 10 and value is not None]
    current_date = str(payload.get("updated", ""))[:10]
    current_value = num((payload.get("current") or {}).get("forward"))
    # API 的歷史序列為月頻，最新即期共識另放在 current；補成最後一點才不會讓圖表停在舊月。
    if current_date and current_value is not None and (not pe or pe[-1][0] < current_date):
        pe.append((current_date, current_value))
    if len(pe) < 24:
        raise RuntimeError("前瞻本益比資料不足: %d 筆" % len(pe))

    hist = yf.Ticker("QQQ").history(start=pe[0][0], auto_adjust=False, interval="1d")
    if hist is None or hist.empty:
        raise RuntimeError("QQQ 歷史價格抓取失敗")
    closes = [(idx.strftime("%Y-%m-%d"), num(value)) for idx, value in hist["Close"].items()]
    closes = [(date, value) for date, value in closes if value is not None]
    close_by_date = dict(closes)
    trade_dates = [date for date, _ in closes]

    dates, forward_pe, qqq = [], [], []
    cursor = 0
    latest_close = None
    for date, value in pe:
        while cursor < len(trade_dates) and trade_dates[cursor] <= date:
            latest_close = close_by_date[trade_dates[cursor]]
            cursor += 1
        if latest_close is not None:
            dates.append(date)
            forward_pe.append(value)
            qqq.append(latest_close)
    if len(dates) < 24:
        raise RuntimeError("與 QQQ 對齊後資料不足: %d 筆" % len(dates))

    last = forward_pe[-1]
    percentile = round(100 * sum(x <= last for x in forward_pe) / len(forward_pe), 1)
    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "History of Market（Bloomberg BEst 12 個月市場共識）／QQQ：Yahoo Finance 收盤價",
        "metric": "Nasdaq-100 12 個月前瞻本益比（Forward P/E）",
        "forward_pe_last": last,
        "qqq_last": qqq[-1],
        "percentile_all": percentile,
        "range_all": {"min": min(forward_pe), "max": max(forward_pe)},
        "windows": ["1y", "3y", "5y", "10y", "max"],
        "default_window": "10y",
        "series": {"dates": dates, "forward_pe": forward_pe, "qqq": qqq},
    }


def main():
    print("=== 抓取 NDX Forward P/E × QQQ ===", flush=True)
    try:
        data = build_live()
    except Exception as exc:
        print("[ndx_forward_pe] 抓取失敗:", exc)
        data = load_old()
    if not isinstance(data, dict) or not (data.get("series") or {}).get("dates"):
        print("[ndx_forward_pe] 無可用資料，不寫檔")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("✓ ndx_forward_pe.json：%s，%.2fx，%d 點" % (data["as_of"], data["forward_pe_last"], len(data["series"]["dates"])))


if __name__ == "__main__":
    main()

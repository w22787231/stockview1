# -*- coding: utf-8 -*-
"""SOXX 12 個月前瞻本益比與 SOXX 收盤價 → data/soxx_forward_pe.json。

資料源為 ETF Metrics 依 SOXX 成分股權重彙整的 Forward P/E。該站只提供即期值，
因此本程式會將每次成功讀取的「資料日、估值、SOXX 收盤價」追加到既有序列；
不會用今天的共識盈餘回推歷史價格，避免製造非 point-in-time 的假歷史資料。
"""
import datetime
import json
import os
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "soxx_forward_pe.json")
LIVE = "https://stockview1.pages.dev/data/soxx_forward_pe.json"
SOURCE_URL = "https://etf-metrics.com/ticker/soxx"


def load_old():
    for path in (OUT,):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8-sig"))
    except Exception as exc:
        print("[soxx_forward_pe] 無法讀取 last-good:", exc)
        return None


def fetch_html():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def fetch_live():
    html = fetch_html()
    match = re.search(r"Forward P/E</div><div[^>]*>\s*([0-9]+(?:\.[0-9]+)?)", html, re.I)
    if not match:
        raise RuntimeError("找不到 ETF Metrics 的 SOXX Forward P/E")
    date_match = re.search(r"Updated\s*:\s*<span>\s*(\d{4}-\d{2}-\d{2})", html, re.I)
    if not date_match:
        raise RuntimeError("找不到 ETF Metrics 的資料日期")
    return date_match.group(1), round(float(match.group(1)), 2)


def close_on_or_before(date):
    start = (datetime.date.fromisoformat(date) - datetime.timedelta(days=7)).isoformat()
    hist = yf.Ticker("SOXX").history(start=start, end=(datetime.date.fromisoformat(date) + datetime.timedelta(days=2)).isoformat(), auto_adjust=False, interval="1d")
    if hist is None or hist.empty:
        raise RuntimeError("SOXX 歷史價格抓取失敗")
    rows = [(idx.strftime("%Y-%m-%d"), round(float(value), 2)) for idx, value in hist["Close"].items()]
    valid = [row for row in rows if row[0] <= date]
    if not valid:
        raise RuntimeError("找不到資料日或前一交易日的 SOXX 收盤價")
    return valid[-1][1]


def build():
    as_of, current = fetch_live()
    old = load_old() or {}
    old_series = old.get("series") or {}
    pairs = {}
    for date, pe, price in zip(old_series.get("dates") or [], old_series.get("forward_pe") or [], old_series.get("soxx") or []):
        try:
            if pe is not None and price is not None:
                pairs[str(date)[:10]] = (round(float(pe), 2), round(float(price), 2))
        except (TypeError, ValueError):
            pass
    pairs[as_of] = (current, close_on_or_before(as_of))
    dates = sorted(pairs)
    pe = [pairs[date][0] for date in dates]
    soxx = [pairs[date][1] for date in dates]
    last = pe[-1]
    return {
        "as_of": as_of,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ETF Metrics（依 SOXX 成分股權重計算的 Forward P/E）／SOXX：Yahoo Finance 收盤價",
        "metric": "SOXX 12 個月前瞻本益比（Forward P/E）",
        "history_method": "每日成功抓取後累積；不以今日共識盈餘回推歷史，避免非當時點估值。",
        "forward_pe_last": last,
        "soxx_last": soxx[-1],
        "percentile_all": round(100 * sum(value <= last for value in pe) / len(pe), 1),
        "range_all": {"min": min(pe), "max": max(pe)},
        "windows": ["1y", "3y", "5y", "max"],
        "default_window": "max",
        "series": {"dates": dates, "forward_pe": pe, "soxx": soxx},
    }


def main():
    print("=== 抓取 SOXX Forward P/E × SOXX ===", flush=True)
    try:
        data = build()
    except Exception as exc:
        print("[soxx_forward_pe] 抓取失敗:", exc)
        data = load_old()
    if not isinstance(data, dict) or not (data.get("series") or {}).get("dates"):
        print("[soxx_forward_pe] 無可用資料，不寫檔")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("✓ soxx_forward_pe.json：%s，%.2fx，%d 點" % (data["as_of"], data["forward_pe_last"], len(data["series"]["dates"])))


if __name__ == "__main__":
    main()

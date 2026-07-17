# -*- coding: utf-8 -*-
"""槓桿ETF成交額佔比 → data/leveraged_ratio.json。
- SOXX 價格 + SOXL/SOXX 20日均成交額比值(槓桿半導體ETF佔正股ETF的成交額倍數)。
- QQQ  價格 + QQQ/TQQQ 20日均成交額比值(正股Nasdaq100 ETF佔槓桿版的成交額倍數)。
成交額 = 收盤價 * 成交量；比值用 20 日滾動均值降噪(避免單日量能雜訊)。
四檔取最長共同交易日(受 SOXL 上市日 2010-03-11 限制，其餘三檔更早)。
抓取全失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_leveraged_ratio.py"""
import sys, os, json, datetime, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "leveraged_ratio.json")
LIVE = "https://stockview1.pages.dev/data/leveraged_ratio.json"

TICKERS = ["SOXL", "SOXX", "QQQ", "TQQQ"]
ROLL_WIN = 20   # 成交額比值的滾動均值天數


def _load_old():
    """CI 每次都是乾淨 checkout，本機沒有舊檔；抓取失敗時改回讀「線上目前這份」
    當備援，避免單次 yfinance 限流(Too Many Requests)就讓整個區塊從網站消失。"""
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0 Chrome/124"})
        old = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        print("[lev] 本機無檔，改用線上 leveraged_ratio.json 當備援(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[lev] 線上回讀失敗:", e)
        return None


def _num(x, n):
    try:
        f = float(x)
        return None if (f != f) else round(f, n)   # NaN → None
    except Exception:
        return None


def build_live():
    data = yf.download(TICKERS, period="max", interval="1d",
                        group_by="ticker", progress=False, auto_adjust=False)
    frames = {}
    for t in TICKERS:
        if getattr(data.columns, "nlevels", 1) > 1 and t in data.columns.get_level_values(0):
            sub = data[t]
        else:
            sub = data
        sub = sub.dropna(subset=["Close", "Volume"])
        if len(sub) < ROLL_WIN + 30:
            print(f"[lev] {t} 資料不足({len(sub)}筆)，放棄本次")
            return None
        frames[t] = sub

    idx = frames["SOXL"].index
    for t in TICKERS:
        idx = idx.intersection(frames[t].index)
    idx = idx.sort_values()
    if len(idx) < ROLL_WIN + 30:
        print("[lev] 對齊後資料點不足，放棄本次")
        return None

    dv = {}
    close = {}
    for t in TICKERS:
        sub = frames[t].reindex(idx)
        dv[t] = (sub["Close"] * sub["Volume"])
        close[t] = sub["Close"]

    soxl_roll = dv["SOXL"].rolling(ROLL_WIN).mean()
    soxx_roll = dv["SOXX"].rolling(ROLL_WIN).mean()
    qqq_roll = dv["QQQ"].rolling(ROLL_WIN).mean()
    tqqq_roll = dv["TQQQ"].rolling(ROLL_WIN).mean()

    ratio_soxl_soxx = soxl_roll / soxx_roll
    ratio_qqq_tqqq = qqq_roll / tqqq_roll

    dates = [d.strftime("%Y-%m-%d") for d in idx]
    soxx_price = [_num(v, 2) for v in close["SOXX"].values]
    qqq_price = [_num(v, 2) for v in close["QQQ"].values]
    r1 = [_num(v, 3) for v in ratio_soxl_soxx.values]
    r2 = [_num(v, 3) for v in ratio_qqq_tqqq.values]

    def last_valid(arr):
        return next((v for v in reversed(arr) if v is not None), None)

    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance SOXL/SOXX/QQQ/TQQQ 日成交額(收盤價×成交量)，%d日滾動均值比值" % ROLL_WIN,
        "roll_win": ROLL_WIN,
        "soxx_price_last": last_valid(soxx_price),
        "soxl_soxx_ratio_last": last_valid(r1),
        "qqq_price_last": last_valid(qqq_price),
        "qqq_tqqq_ratio_last": last_valid(r2),
        "windows": ["3m", "6m", "1y", "3y", "5y", "10y", "max"],
        "default_window": "1y",
        "series": {
            "dates": dates,
            "soxx_price": soxx_price,
            "soxl_soxx_ratio": r1,
            "qqq_price": qqq_price,
            "qqq_tqqq_ratio": r2,
        },
    }


def main():
    print("=== 抓取槓桿ETF成交額佔比(SOXL/SOXX、QQQ/TQQQ) ===", flush=True)
    j = None
    try:
        j = build_live()
    except Exception as e:
        print("[lev] 抓取失敗:", e)
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] 槓桿ETF比值抓取失敗或資料不足 → 嘗試沿用線上 last-good")
        j = _load_old()
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] 無可用資料(新舊皆失敗) → 不寫檔")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ leveraged_ratio.json 已更新:as_of %s SOXX=%s SOXL/SOXX=%s QQQ=%s QQQ/TQQQ=%s，序列 %d 點"
          % (j["as_of"], j["soxx_price_last"], j["soxl_soxx_ratio_last"],
             j["qqq_price_last"], j["qqq_tqqq_ratio_last"], len(s["dates"])))


if __name__ == "__main__":
    main()

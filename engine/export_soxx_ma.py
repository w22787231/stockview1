# -*- coding: utf-8 -*-
"""SOXX 股價 × 200日均線 × 偏離率 → data/soxx_ma.json。
偏離率 = (收盤價 ÷ MA200 − 1) × 100%。拉最長歷史(SOXX 2001-07-13 上市,
扣 200 日均線暖身後序列從 2002-05 起，約 24 年)。
抓取全失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_soxx_ma.py"""
import sys, os, json, datetime, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import warnings
warnings.filterwarnings("ignore")
import time
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "soxx_ma.json")
LIVE = "https://stockview1.pages.dev/data/soxx_ma.json"
MA_WIN = 200


def _load_old():
    """CI 每次都是乾淨 checkout，本機沒有舊檔；重試後仍失敗時改回讀「線上目前這份」
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
        print("[soxx_ma] 本機無檔，改用線上 soxx_ma.json 當備援(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[soxx_ma] 線上回讀失敗:", e)
        return None


def _num(x, n):
    try:
        f = float(x)
        return None if (f != f) else round(f, n)
    except Exception:
        return None


def _fetch_history(tries=3, wait=8):
    """yfinance 偶爾被 Yahoo 限流(Too Many Requests);CI 內同一 workflow 前面
    已跑過多支抓 yfinance 的腳本，容易撞到。重試幾次、間隔拉長，減少整次落空。"""
    last_err = None
    for i in range(tries):
        try:
            h = yf.Ticker("SOXX").history(period="max", interval="1d", auto_adjust=False)
            if h is not None and len(h) > 0:
                return h
        except Exception as e:
            last_err = e
        if i < tries - 1:
            print("[soxx_ma] 第 %d 次抓取失敗(%s)，%d 秒後重試" % (i + 1, last_err, wait))
            time.sleep(wait)
    if last_err:
        raise last_err
    raise RuntimeError("yfinance 回傳空資料")


def build_live():
    h = _fetch_history()
    h = h.dropna(subset=["Close"])
    if len(h) < MA_WIN + 30:
        print("[soxx_ma] 資料不足(%d 筆)，放棄本次" % len(h))
        return None
    ma200 = h["Close"].rolling(MA_WIN).mean()
    h = h.assign(MA200=ma200).dropna(subset=["MA200"])
    dev = (h["Close"] / h["MA200"] - 1.0) * 100.0

    dates = [d.strftime("%Y-%m-%d") for d in h.index]
    close = [_num(v, 2) for v in h["Close"].values]
    ma = [_num(v, 2) for v in h["MA200"].values]
    devp = [_num(v, 2) for v in dev.values]

    def last_valid(arr):
        return next((v for v in reversed(arr) if v is not None), None)

    dev_valid = [v for v in devp if v is not None]

    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance SOXX 日線，MA200 = 200 個交易日簡單移動平均",
        "ma_win": MA_WIN,
        "close_last": last_valid(close),
        "ma200_last": last_valid(ma),
        "dev_pct_last": last_valid(devp),
        "dev_pct_min": round(min(dev_valid), 2) if dev_valid else None,
        "dev_pct_max": round(max(dev_valid), 2) if dev_valid else None,
        "windows": ["3m", "6m", "1y", "3y", "5y", "10y", "max"],
        "default_window": "1y",
        "series": {"dates": dates, "close": close, "ma200": ma, "dev_pct": devp},
    }


def main():
    print("=== 抓取 SOXX 股價 × 200日均線 × 偏離率 ===", flush=True)
    j = None
    try:
        j = build_live()
    except Exception as e:
        print("[soxx_ma] 抓取失敗:", e)
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] SOXX MA200 抓取失敗或資料不足 → 嘗試沿用線上 last-good")
        j = _load_old()
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] 無可用資料(新舊皆失敗) → 不寫檔")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ soxx_ma.json 已更新:as_of %s 收盤=%s MA200=%s 偏離率=%s%%，序列 %d 點"
          % (j["as_of"], j["close_last"], j["ma200_last"], j["dev_pct_last"], len(s["dates"])))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""S&P 500(^GSPC) Williams %R(14日) → data/williams_r.json。
Williams %R = (N日最高高點 − 收盤) ÷ (N日最高高點 − N日最低低點) × −100，範圍 0 ~ −100。
−20 以上(較接近0)＝超買，−80 以下＝超賣，用來抓短線動能過熱/過冷的轉折區。
抓取全失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_williams_r.py"""
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
OUT = os.path.join(HERE, "..", "data", "williams_r.json")
LIVE = "https://stockview1.pages.dev/data/williams_r.json"
SYMBOL = "^GSPC"
PERIOD = 14
OB_LEVEL = -20   # 超買門檻(高於此,即較接近0)
OS_LEVEL = -80   # 超賣門檻(低於此,即較接近-100)


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
        print("[williams_r] 本機無檔，改用線上 williams_r.json 當備援(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[williams_r] 線上回讀失敗:", e)
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
            h = yf.Ticker(SYMBOL).history(period="10y", interval="1d", auto_adjust=False)
            if h is not None and len(h) > 0:
                return h
        except Exception as e:
            last_err = e
        if i < tries - 1:
            print("[williams_r] 第 %d 次抓取失敗(%s)，%d 秒後重試" % (i + 1, last_err, wait))
            time.sleep(wait)
    if last_err:
        raise last_err
    raise RuntimeError("yfinance 回傳空資料")


def build_live():
    h = _fetch_history()
    h = h.dropna(subset=["High", "Low", "Close"])
    if len(h) < PERIOD + 30:
        print("[williams_r] 資料不足(%d 筆)，放棄本次" % len(h))
        return None
    hh = h["High"].rolling(PERIOD).max()
    ll = h["Low"].rolling(PERIOD).min()
    rng = hh - ll
    wr = ((hh - h["Close"]) / rng.replace(0, float("nan"))) * -100.0
    h = h.assign(WR=wr).dropna(subset=["WR"])

    dates = [d.strftime("%Y-%m-%d") for d in h.index]
    close = [_num(v, 2) for v in h["Close"].values]
    wrv = [_num(v, 2) for v in h["WR"].values]

    def last_valid(arr):
        return next((v for v in reversed(arr) if v is not None), None)

    wr_valid = [v for v in wrv if v is not None]
    wr_last = last_valid(wrv)
    signal = None
    if wr_last is not None:
        signal = "超買" if wr_last >= OB_LEVEL else ("超賣" if wr_last <= OS_LEVEL else "中性")

    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance %s(S&P 500)日線，Williams %%R = %d 個交易日" % (SYMBOL, PERIOD),
        "period": PERIOD,
        "ob_level": OB_LEVEL,
        "os_level": OS_LEVEL,
        "close_last": last_valid(close),
        "wr_last": wr_last,
        "signal": signal,
        "wr_min": round(min(wr_valid), 2) if wr_valid else None,
        "wr_max": round(max(wr_valid), 2) if wr_valid else None,
        "windows": ["1m", "3m", "6m", "1y", "3y", "max"],
        "default_window": "3m",
        "series": {"dates": dates, "close": close, "wr": wrv},
    }


def main():
    print("=== 抓取 S&P 500 Williams %%R(%d日) ===" % PERIOD, flush=True)
    j = None
    try:
        j = build_live()
    except Exception as e:
        print("[williams_r] 抓取失敗:", e)
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] Williams %R 抓取失敗或資料不足 → 嘗試沿用線上 last-good")
        j = _load_old()
    if not (isinstance(j, dict) and (j.get("series") or {}).get("dates")):
        print("[!] 無可用資料(新舊皆失敗) → 不寫檔")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ williams_r.json 已更新:as_of %s 收盤=%s %%R=%s(%s)，序列 %d 點"
          % (j["as_of"], j["close_last"], j["wr_last"], j.get("signal"), len(s["dates"])))


if __name__ == "__main__":
    main()

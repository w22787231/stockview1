# -*- coding: utf-8 -*-
"""情緒指標匯出。
- VIX/VXN/SKEW/HYG：水準 + 與昨日差。
- 市場廣度：SP500 中站上 20MA/50MA 的家數%，並與昨日比。
- F&G(Fear & Greed)：試爬 CNN 非官方 API，抓不到則略過。
輸出 ../data/sentiment.json。
"""
import sys, os, io, json, csv, datetime
import urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import adr_screen as eng

DATA_DIR = os.path.join(HERE, "..", "data")
BREADTH_POOL = "sp500"   # 用 SP500 當美股大盤廣度代表

# yield_like 概念：這些指標用「水準 + 日差」呈現，不是漲跌%。
LEVELS = [
    {"sym": "^VIX",  "label": "VIX 恐慌指數",  "note": "標普500波動率", "unit": "pt",
     "read": "高=恐慌、低=貪婪(<15 偏自滿、>30 偏恐慌)"},
    {"sym": "^VXN",  "label": "VXN 那指波動",  "note": "Nasdaq-100 波動率", "unit": "pt",
     "read": "那指版 VIX，科技股恐慌程度"},
    {"sym": "^SKEW", "label": "SKEW 尾部風險", "note": "黑天鵝/崩盤避險需求", "unit": "pt",
     "read": "越高=市場越在買崩盤保險(>145 偏警戒)"},
    {"sym": "HYG",   "label": "HYG 高收益債",  "note": "信用風險(跌=避險升溫)", "unit": "px",
     "read": "高收益債價，跌代表信用市場轉趨避險"},
]


def _safe(x):
    try:
        f = float(x)
        return None if f != f else f
    except Exception:
        return None


def _round(x, n=2):
    v = _safe(x)
    return round(v, n) if v is not None else None


def fetch_levels():
    syms = [x["sym"] for x in LEVELS]
    df = yf.download(syms, period="4mo", interval="1d",
                     group_by="ticker", progress=False, auto_adjust=False)
    out, failed = [], []
    for it in LEVELS:
        s = it["sym"]
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            if len(sub) < 2:
                failed.append(s); continue
            last = float(sub["Close"].iloc[-1])
            prev = float(sub["Close"].iloc[-2])
            row = {"sym": s, "label": it["label"], "note": it["note"],
                   "read": it["read"], "unit": it["unit"],
                   "level": _round(last, 2)}
            if it["unit"] == "px":
                row["diff_pct"] = _round((last/prev - 1)*100, 2)   # 價格類用%
            else:
                row["diff"] = _round(last - prev, 2)               # 指數類用點差
            closes = [float(x) for x in sub["Close"].tolist() if x == x]
            row["spark"] = [round(v, 2) for v in closes[-60:]]     # ~60日迷你走勢
            out.append(row)
        except Exception:
            failed.append(s)
    return out, failed


def fetch_cor1m():
    """Cboe COR1M 隱含相關性。yfinance 的 ^COR1M 只回單點,改用 Cboe 官方 CSV:
    取最新收盤 + 昨收(算日差) + 2006 以來歷史百分位。"""
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/COR1M_History.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        closes = []
        for r in list(csv.reader(io.StringIO(data)))[1:]:
            v = _safe(r[4]) if len(r) >= 5 else None
            if v is not None:
                closes.append(v)
        if len(closes) < 2:
            return None
        last, prev = closes[-1], closes[-2]
        pct = sum(1 for v in closes if v <= last) / len(closes) * 100
        return {
            "sym": "COR1M", "label": "COR1M 隱含相關性",
            "note": "成分股齊漲齊跌預期", "unit": "pt",
            "read": f"越低=個股各走各、表面平靜底層脆弱(2006以來第{pct:.0f}百分位)",
            "level": _round(last, 2), "diff": _round(last - prev, 2),
            "spark": [round(v, 2) for v in closes[-60:]],
        }
    except Exception:
        return None


def market_breadth(pool=BREADTH_POOL):
    """SP500 中站上 20MA/50MA 的家數%，並與昨日比。"""
    symbols = eng.load_pool(pool) or []
    if not symbols:
        return None
    df = eng._download(symbols, period="4mo")  # 50MA + 看昨日 需要 ~3mo+
    cnt = {"ma20_today": 0, "ma20_prev": 0, "ma50_today": 0, "ma50_prev": 0, "n": 0}
    for sym in symbols:
        try:
            sub = eng._sub(df, symbols, sym)
            closes = list(sub["Close"])
            if len(closes) < 52:
                continue
            def ma(idx, w):
                return sum(closes[idx + 1 - w:idx + 1]) / w
            last = len(closes) - 1
            prev = last - 1
            cnt["n"] += 1
            if closes[last] > ma(last, 20): cnt["ma20_today"] += 1
            if closes[prev] > ma(prev, 20): cnt["ma20_prev"] += 1
            if closes[last] > ma(last, 50): cnt["ma50_today"] += 1
            if closes[prev] > ma(prev, 50): cnt["ma50_prev"] += 1
        except Exception:
            continue
    if cnt["n"] == 0:
        return None
    n = cnt["n"]
    def pct(k): return round(cnt[k] / n * 100, 1)
    return {
        "pool": pool.upper(), "n": n,
        "above20_pct": pct("ma20_today"),
        "above20_prev": pct("ma20_prev"),
        "above50_pct": pct("ma50_today"),
        "above50_prev": pct("ma50_prev"),
    }


def fetch_fear_greed():
    """試爬 CNN Fear & Greed 非官方 API。抓不到回 None。"""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cnn.com/"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        fg = data.get("fear_and_greed", {})
        score = _safe(fg.get("score"))
        prev = _safe(fg.get("previous_close"))
        if score is None:
            return None
        hist = data.get("fear_and_greed_historical", {}).get("data", [])
        spark = [round(_safe(p.get("y")), 0) for p in hist[-60:]
                 if _safe(p.get("y")) is not None]
        return {"score": _round(score, 0),
                "prev": _round(prev, 0) if prev is not None else None,
                "rating": fg.get("rating", ""),
                "spark": spark}
    except Exception:
        return None


def build():
    levels, failed = fetch_levels()
    cor = fetch_cor1m()
    if cor:
        levels.append(cor)
    else:
        failed.append("COR1M")
    breadth = market_breadth()
    fng = fetch_fear_greed()
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily) + CNN F&G",
        "levels": levels,
        "breadth": breadth,
        "fear_greed": fng,
        "failed": failed,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "sentiment.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[sentiment] -> data/sentiment.json  (levels {len(levels)}, "
          f"breadth {'ok' if breadth else 'none'}, F&G {'ok' if fng else 'none'}, "
          f"失敗 {len(failed)})")


if __name__ == "__main__":
    build()

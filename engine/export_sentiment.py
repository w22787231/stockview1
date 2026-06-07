# -*- coding: utf-8 -*-
"""情緒指標匯出。
- VIX/VXN/SKEW/HYG：水準 + 與昨日差。
- 市場廣度：SP500 中站上 20MA/50MA 的家數%，並與昨日比。
- F&G(Fear & Greed)：試爬 CNN 非官方 API，抓不到則略過。
輸出 ../data/sentiment.json。
"""
import sys, os, io, json, csv, re, datetime
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
            "read": f"越低=個股各走各、表面平靜底層脆弱(2006以來第{pct:.0f}百分位)；⚠️ 低於8危險",
            "level": _round(last, 2), "diff": _round(last - prev, 2),
            "spark": [round(v, 2) for v in closes[-60:]],
        }
    except Exception:
        return None


def market_breadth(pool=BREADTH_POOL):
    """SP500 廣度：站上 20MA/50MA 家數% + 52週新高/新低家數，皆與昨日比。"""
    symbols = eng.load_pool(pool) or []
    if not symbols:
        return None
    df = eng._download(symbols, period="15mo")  # 52週高低需 ~252+ 日
    W, D = 252, 21                              # 252日窗;近 D 個交易日(約一個月)
    cnt = {"ma20_today": 0, "ma20_prev": 0, "ma50_today": 0, "ma50_prev": 0, "n": 0}
    nh_series = [0] * D
    nl_series = [0] * D
    for sym in symbols:
        try:
            sub = eng._sub(df, symbols, sym)
            closes = list(sub["Close"])
            m = len(closes)
            if m < 52:
                continue
            def ma(idx, w):
                return sum(closes[idx + 1 - w:idx + 1]) / w
            last = m - 1
            prev = last - 1
            cnt["n"] += 1
            if closes[last] > ma(last, 20): cnt["ma20_today"] += 1
            if closes[prev] > ma(prev, 20): cnt["ma20_prev"] += 1
            if closes[last] > ma(last, 50): cnt["ma50_today"] += 1
            if closes[prev] > ma(prev, 50): cnt["ma50_prev"] += 1
            if m >= W + D:                  # 近 D 日各自的 52週新高/新低
                for j in range(D):
                    idx = m - D + j
                    win = closes[idx - W + 1:idx + 1]
                    if closes[idx] >= max(win): nh_series[j] += 1
                    if closes[idx] <= min(win): nl_series[j] += 1
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
        "nh": nh_series[-1], "nh_prev": nh_series[-2],
        "nl": nl_series[-1], "nl_prev": nl_series[-2],
        "nh_series": nh_series, "nl_series": nl_series,
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


def _fetch_gdp_trillions():
    """當期名目 GDP(兆美元)。優先 FRED 季度年化(GDP 系列,十億);失敗退 World Bank 年度。
    回傳 (gdp_兆, 來源標籤)。FRED 對齊 GuruFocus 等標準口徑(~4.1%);World Bank 年度偏舊會墊高比率。"""
    try:
        u = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP"
        d = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}),
            timeout=20).read().decode("utf-8", "ignore")
        rows = [r for r in csv.reader(io.StringIO(d)) if r]
        vals = [r for r in rows[1:] if r and r[-1] not in ("", ".")]
        if vals:
            last = vals[-1]
            return float(last[-1]) / 1000.0, "FRED " + last[0][:7]   # 十億→兆,季度年化
    except Exception:
        pass
    try:
        gu = "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD?format=json&per_page=6"
        gd = json.loads(urllib.request.urlopen(
            urllib.request.Request(gu, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode("utf-8", "ignore"))
        for r in gd[1]:
            if r.get("value"):
                return r["value"] / 1e12, "World Bank " + r["date"] + "(年度)"
    except Exception:
        pass
    return None, ""


def fetch_leverage():
    """市場槓桿:FINRA 融資餘額(月) ÷ 名目GDP(FRED 季度年化優先) = 融資/GDP 泡沫比%。"""
    try:
        u = "https://www.finra.org/investors/learn-to-invest/advanced-investing/margin-statistics"
        html = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20
        ).read().decode("utf-8", "ignore")
        pairs = re.findall(r"([A-Z][a-z]{2}-\d{2})[\s\S]{0,400}?([1-9],\d{3},\d{3})", html)
        if not pairs:
            return None
        pairs = pairs[:12][::-1]   # 最新在前→取近12月→反轉成時間序(舊→新)
        gdp_t, gdp_label = _fetch_gdp_trillions()
        if not gdp_t:
            return None
        margins = [float(a.replace(",", "")) / 1e6 for _, a in pairs]
        ratio_series = [round(mv / gdp_t * 100, 2) for mv in margins]
        return {"margin_t": round(margins[-1], 2), "margin_month": pairs[-1][0],
                "gdp_t": round(gdp_t, 2), "gdp_label": gdp_label,
                "ratio_pct": ratio_series[-1], "ratio_series": ratio_series,
                "months": [mn for mn, _ in pairs]}
    except Exception:
        return None


def fetch_tw_margin_ratio():
    """台股大盤融資維持率(上市)= 融資市值 / 融資金額。
    來源:TWSE STOCK_DAY_ALL(逐檔收盤)+ 舊版 MI_MARGN(融資金額總額 + 逐檔張)。
    歷史:回讀已發布 sentiment.json 逐日累積(免額外儲存)。"""
    def _g(u, t=25):
        return urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=t
        ).read().decode("utf-8", "ignore")
    try:
        sd = json.loads(_g("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"))
        price, roc = {}, ""
        for r in sd:
            c = _safe(r.get("ClosingPrice"))
            if c:
                price[r["Code"]] = c
            roc = r.get("Date", roc)
        if not price or not roc:
            return None
        ymd = str(int(roc[:3]) + 1911) + roc[3:]   # 1150605 -> 20260605
        mj = json.loads(_g(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json"))
        tables = mj.get("tables", [])
        loan = None
        for row in tables[0]["data"]:
            if "融資金額" in row[0]:
                loan = float(row[5].replace(",", "")) * 1000   # 仟元→元(今日餘額)
        if not loan:
            return None
        mv = 0.0
        for row in tables[1]["data"]:
            code = row[0].strip()
            if code.startswith("00"):       # 排除 ETF(對齊標準:分子不含 ETF)
                continue
            lots = _safe(row[6].replace(",", "")) if len(row) > 6 else None
            p = price.get(code)
            if lots and p:
                mv += lots * 1000 * p
        if mv <= 0:
            return None
        ratio = round(mv / loan * 100, 2)
        dates, series = [], []
        try:
            prev = json.loads(_g("https://stockview1.pages.dev/data/sentiment.json", 10))
            for lv in prev.get("levels", []):
                if lv.get("sym") == "TWMARGIN":
                    dates = list(lv.get("dates") or [])
                    series = list(lv.get("spark") or [])
        except Exception:
            pass
        if dates and dates[-1] == ymd:
            series[-1] = ratio
        else:
            dates.append(ymd); series.append(ratio)
        dates, series = dates[-60:], series[-60:]
        diff = round(series[-1] - series[-2], 2) if len(series) >= 2 else None
        return {"sym": "TWMARGIN", "label": "台股融資維持率",
                "note": "上市·不含ETF·斷頭壓力", "unit": "pt",
                "read": "<130% 斷頭警戒(常見底部);上市口徑、分子不含ETF,絕對值略高於含上櫃版",
                "level": ratio, "diff": diff, "spark": series, "dates": dates}
    except Exception:
        return None


def build():
    levels, failed = fetch_levels()
    cor = fetch_cor1m()
    if cor:
        levels.append(cor)
    else:
        failed.append("COR1M")
    tw = fetch_tw_margin_ratio()
    if tw:
        levels.append(tw)
    else:
        failed.append("TWMARGIN")
    breadth = market_breadth()
    fng = fetch_fear_greed()
    leverage = fetch_leverage()
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance + CNN F&G + FINRA/WorldBank",
        "levels": levels,
        "breadth": breadth,
        "fear_greed": fng,
        "leverage": leverage,
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

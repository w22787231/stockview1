# -*- coding: utf-8 -*-
"""情緒指標匯出。
- VIX/VXN/SKEW/HYG：水準 + 與昨日差。
- 市場廣度：SP500 中站上 20MA/50MA 的家數%，並與昨日比。
- F&G(Fear & Greed)：試爬 CNN 非官方 API，抓不到則略過。
輸出 ../data/sentiment.json。
"""
import sys, os, io, json, csv, re, datetime, time, calendar
import urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import adr_screen as eng
import tw_margin_ratio as TWMR

DATA_DIR = os.path.join(HERE, "..", "data")
BREADTH_POOL = "sp500"   # 用 SP500 當美股大盤廣度代表

# yield_like 概念：這些指標用「水準 + 日差」呈現，不是漲跌%。
LEVELS = [
    {"sym": "^VIX",  "cboe": "VIX",  "label": "VIX 恐慌指數",  "note": "標普500波動率", "unit": "pt",
     "read": "高=恐慌、低=貪婪(<15 偏自滿、>30 偏恐慌)"},
    {"sym": "^VXN",  "cboe": "VXN",  "label": "VXN 那指波動",  "note": "Nasdaq-100 波動率", "unit": "pt",
     "read": "那指版 VIX，科技股恐慌程度"},
    {"sym": "^SKEW", "cboe": "SKEW", "label": "SKEW 尾部風險", "note": "黑天鵝/崩盤避險需求", "unit": "pt",
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


def _cboe_index(name):
    """Cboe 指數日線 CSV → 收盤序列(最後一欄=CLOSE,兼容 2 欄與 OHLC 格式)。"""
    try:
        d = urllib.request.urlopen(urllib.request.Request(
            f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode("utf-8", "ignore")
        closes = []
        for r in list(csv.reader(io.StringIO(d)))[1:]:
            v = _safe(r[-1]) if r else None
            if v is not None:
                closes.append(v)
        return closes if len(closes) >= 2 else None
    except Exception:
        return None


def fetch_levels():
    out, failed = [], []
    # HYG(ETF)用 yfinance;VIX/VXN/SKEW 改用 Cboe 官方 CSV(yfinance 指數常掉資料)
    yf_syms = [x["sym"] for x in LEVELS if not x.get("cboe")]
    ydf = (yf.download(yf_syms, period="4mo", interval="1d", group_by="ticker",
                       progress=False, auto_adjust=False) if yf_syms else None)
    for it in LEVELS:
        s = it["sym"]
        try:
            if it.get("cboe"):
                closes = _cboe_index(it["cboe"])
                if not closes:
                    failed.append(s); continue
            else:
                if getattr(ydf.columns, "nlevels", 1) > 1 and s in ydf.columns.get_level_values(0):
                    sub = ydf[s].dropna()
                else:
                    sub = ydf.dropna()
                closes = [float(x) for x in sub["Close"].tolist() if x == x]
                if len(closes) < 2:
                    failed.append(s); continue
            last, prev = closes[-1], closes[-2]
            row = {"sym": s, "label": it["label"], "note": it["note"],
                   "read": it["read"], "unit": it["unit"], "level": _round(last, 2)}
            if it["unit"] == "px":
                row["diff_pct"] = _round((last / prev - 1) * 100, 2)   # 價格類用%
            else:
                row["diff"] = _round(last - prev, 2)                   # 指數類用點差
            row["spark"] = [round(v, 2) for v in closes[-60:]]         # ~60日迷你走勢
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
    uniq_nh = uniq_nl = 0                 # 近一個月內「曾」創新高/新低的不重複家數
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
            if m >= W + D:                  # 近 D 日:逐日序列 + 整月不重複家數
                hit_hi = hit_lo = False
                for j in range(D):
                    idx = m - D + j
                    win = closes[idx - W + 1:idx + 1]
                    if closes[idx] >= max(win): nh_series[j] += 1; hit_hi = True
                    if closes[idx] <= min(win): nl_series[j] += 1; hit_lo = True
                if hit_hi: uniq_nh += 1
                if hit_lo: uniq_nl += 1
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
        "nh_uniq": uniq_nh, "nl_uniq": uniq_nl,
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
    """當期名目 GDP(兆美元)。優先 FRED 官方 API(env FRED_API_KEY,雲端 CI 不被擋),失敗退公開
    fredgraph.csv,再失敗退近期估值。回 (gdp_兆, 來源標籤)。FRED 季度年化,對齊 GuruFocus 口徑(~4.1%)。"""
    key = os.environ.get("FRED_API_KEY", "").strip()
    for _ in range(3):                          # FRED 從 CI 偶爾連不到 → 重試
        try:
            if key:
                j = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://api.stlouisfed.org/fred/series/observations?series_id=GDP"
                    f"&api_key={key}&file_type=json&sort_order=desc&limit=1",
                    headers={"User-Agent": "Mozilla/5.0"}), timeout=30
                ).read().decode("utf-8", "ignore"))
                obs = [o for o in j.get("observations", []) if o.get("value") not in (None, "", ".")]
                if obs:
                    o = obs[0]                  # sort_order=desc → 最新一筆
                    return float(o["value"]) / 1000.0, "FRED " + o.get("date", "")[:7]
            else:
                d = urllib.request.urlopen(
                    urllib.request.Request("https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP",
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}),
                    timeout=30).read().decode("utf-8", "ignore")
                vals = [r for r in list(csv.reader(io.StringIO(d)))[1:] if r and r[-1] not in ("", ".")]
                if vals:
                    last = vals[-1]
                    return float(last[-1]) / 1000.0, "FRED " + last[0][:7]   # 十億→兆
        except Exception:
            pass
        time.sleep(1.5)
    # 後備:近期名目GDP估值(FRED 2026Q1 ~31.8兆;每季手動更新一次)。不用 World Bank 年度(偏舊墊高比率)。
    return 31.8, "估值~2026Q1"


def _finra_margin_history_xlsx():
    """FINRA 官方 margin-statistics.xlsx:完整月度 Debit Balances(margin debt,百萬美元)1997→今。
    回 [(label 'May-26', 兆USD), ...] 舊→新;失敗回 None。openpyxl 缺席時回 None(退頁面來源)。"""
    try:
        import openpyxl
        raw = urllib.request.urlopen(urllib.request.Request(
            "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        out = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            ym = row[0] if row else None
            debit = row[1] if row and len(row) > 1 else None
            if ym is None or debit is None:
                continue
            try:
                if hasattr(ym, "year"):                       # datetime
                    yy, mm = ym.year, ym.month
                else:                                         # 'YYYY-MM'
                    p = str(ym).split("-")
                    yy, mm = int(p[0]), int(p[1])
                lbl = _MON_NAMES[mm - 1] + "-" + f"{yy % 100:02d}"
                out.append(((yy, mm), lbl, round(float(debit) / 1e6, 4)))
            except Exception:
                continue
        if len(out) < 12:
            return None
        out.sort(key=lambda x: x[0])                          # 舊→新
        return [(lbl, v) for _, lbl, v in out]
    except Exception:
        return None


def _finra_margin_history_page():
    """後備:FINRA margin-statistics 頁面嵌入(近~12月)。回 [(label,兆),...] 舊→新 或 None。"""
    try:
        u = "https://www.finra.org/investors/learn-to-invest/advanced-investing/margin-statistics"
        html = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20
        ).read().decode("utf-8", "ignore")
        pairs = re.findall(r"([A-Z][a-z]{2}-\d{2})[\s\S]{0,400}?([1-9],\d{3},\d{3})", html)
        if not pairs:
            return None
        pairs = pairs[:60][::-1]
        return [(mn, float(a.replace(",", "")) / 1e6) for mn, a in pairs]
    except Exception:
        return None


def fetch_leverage():
    """市場槓桿 + 保證金借款歷史。優先 FINRA 官方 xlsx(完整 1997→今 margin debt),失敗退頁面(近12月)。
    ratio_series/ratio_pct/months = 近12月 融資/GDP%(供「市場槓桿·融資/GDP」卡);
    margin_series/margin_months = 完整月度絕對融資餘額(兆,供「保證金借款」大圖)。"""
    hist = _finra_margin_history_xlsx() or _finra_margin_history_page()
    if not hist:
        return None
    try:
        gdp_t, gdp_label = _fetch_gdp_trillions()
        months = [l for l, _ in hist]
        margins = [v for _, v in hist]
        recent_v = margins[-12:]
        ratio_series = [round(mv / gdp_t * 100, 2) for mv in recent_v] if gdp_t else []
        return {"margin_t": round(margins[-1], 2), "margin_month": months[-1],
                "gdp_t": round(gdp_t, 2) if gdp_t else None, "gdp_label": gdp_label,
                "ratio_pct": ratio_series[-1] if ratio_series else None,
                "ratio_series": ratio_series, "months": months[-12:],
                # 供「保證金借款」大圖:完整絕對融資餘額(兆)月序,build() 會併上次歷史
                "margin_series": [round(m, 4) for m in margins],
                "margin_months": months}
    except Exception:
        return None


def _twii_close_map(start="2023-01-01"):
    """^TWII 日線收盤 {YYYYMMDD: close};失敗回 {}。"""
    try:
        import yfinance as yf
        h = yf.Ticker("^TWII").history(start=start, auto_adjust=False)
        out = {}
        for idx, row in h.iterrows():
            c = row.get("Close")
            if c is not None and c == c:
                out[idx.strftime("%Y%m%d")] = round(float(c), 2)
        return out
    except Exception:
        return {}


def fetch_tw_margin_ratio(seed_path=None):
    """台股大盤融資維持率(上市)= 融資市值 / 融資金額。
    今日值:TWSE STOCK_DAY_ALL(逐檔收盤)+ MI_MARGN(融資金額總額 + 逐檔張)。
    歷史:合併 committed 種子檔 + 前版 published sentiment.json 的 tw_margin_ratio。"""
    def _g(u, t=25):
        return urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=t
        ).read().decode("utf-8", "ignore")

    point = None
    ymd = None
    try:
        sd = json.loads(_g("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"))
        price, roc = {}, ""
        for r in sd:
            c = _safe(r.get("ClosingPrice"))
            if c:
                price[r["Code"]] = c
            roc = r.get("Date", roc)
        if price and roc:
            ymd = str(int(roc[:3]) + 1911) + roc[3:]
            mj = json.loads(_g(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json"))
            tables = mj.get("tables", [])
            loan = None
            for row in tables[0]["data"]:
                if "融資金額" in row[0]:
                    loan = float(row[5].replace(",", "")) * 1000  # 仟元→元
            lots = {}
            if loan and len(tables) > 1:
                for row in tables[1]["data"]:
                    code = row[0].strip()
                    if len(row) > 6:
                        lots[code] = row[6].replace(",", "")
            ratio = TWMR.compute_ratio(loan, lots, price) if loan else None
            if ratio is not None:
                twii_today = _twii_close_map().get(ymd)
                point = {"date": ymd, "ratio": ratio, "twii": twii_today}
    except Exception:
        point = None

    # 種子檔
    seed = None
    seed_path = seed_path or os.path.join(os.path.dirname(__file__), "tw_margin_ratio_seed.json")
    try:
        with open(seed_path, encoding="utf-8") as f:
            seed = json.load(f)
    except Exception:
        seed = None

    # 前版累積
    prev = None
    try:
        pj = json.loads(_g("https://stockview1.pages.dev/data/sentiment.json", 10))
        prev = pj.get("tw_margin_ratio")
    except Exception:
        prev = None

    dates, ratio_s, twii_s = TWMR.merge_history(seed, prev, point, cap=750)
    if not dates:
        return None

    # 補齊缺的 twii(疊圖恆完整):對既有日期用 ^TWII history 補
    if any(t is None for t in twii_s):
        tmap = _twii_close_map()
        twii_s = [twii_s[i] if twii_s[i] is not None else tmap.get(dates[i]) for i in range(len(dates))]

    level = ratio_s[-1]
    diff = round(ratio_s[-1] - ratio_s[-2], 2) if len(ratio_s) >= 2 and ratio_s[-2] is not None else None
    return {
        "as_of": dates[-1], "level": level, "diff": diff,
        "dates": dates, "ratio": ratio_s, "twii": twii_s,
        "note": "上市·含ETF·斷頭壓力", "unit": "%",
        "read": "<130% 斷頭警戒(常見底部);上市口徑(含ETF,與融資金額同口徑),對齊財經M平方",
        "src": "TWSE STOCK_DAY_ALL + MI_MARGN(每日自算)· 歷史回補 TWSE MI_INDEX+MI_MARGN",
        "url": "https://www.macromicro.me/charts/53117/taiwan-taiex-maintenance-margin",
    }


_MON_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MON_IDX = {m: i + 1 for i, m in enumerate(_MON_NAMES)}


def _month_key(lbl):
    """'May-26' -> 202605(供月序排序);無法解析回 0。"""
    try:
        mon, yy = lbl.split("-")
        y = int(yy)
        y = 2000 + y if y <= 50 else 1900 + y   # 世紀 pivot:26→2026、97→1997(FINRA 全史回到1997)
        return y * 100 + _MON_IDX[mon]
    except Exception:
        return 0


def _merge_months(pm, pv, nm, nv):
    """併兩組(月標籤, 值)月序:同月以新值覆蓋,依月份時序排序。回 (months, values)。"""
    d = {}
    for m, v in zip(pm or [], pv or []):
        d[m] = v
    for m, v in zip(nm or [], nv or []):
        d[m] = v
    ks = sorted((k for k in d if _month_key(k)), key=_month_key)
    return ks, [d[k] for k in ks]


def _monthly_index_map(sym, start):
    """yfinance 月線收盤 → {'May-26': close}(對齊 margin 月標籤)。失敗回 {}。"""
    try:
        df = yf.download(sym, start=start, interval="1mo", progress=False, auto_adjust=False)
        c = df["Close"]
        if hasattr(c, "columns"):          # MultiIndex → 取首欄
            c = c.iloc[:, 0]
        out = {}
        for ts, v in c.items():
            if v is not None and v == v:   # 非 NaN
                out[f"{_MON_NAMES[ts.month - 1]}-{ts.year % 100:02d}"] = round(float(v), 2)
        return out
    except Exception:
        return {}


_OI_UA = {"User-Agent": "stockview-research contact@stockview.example"}


def _oi_month_side(y, m, xp, xs, budget, cnt=5000):
    """OpenInsider screener 指定月的單側筆數(xp=1 只買 / xs=1 只賣)。
    達 cnt 上限(截斷)→ 半月拆再加總。budget=[剩餘查詢數]。失敗回 None。"""
    last = calendar.monthrange(y, m)[1]
    def q(d1, d2):
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        rng = urllib.parse.quote(f"{m:02d}/{d1:02d}/{y} - {m:02d}/{d2:02d}/{y}")
        url = (f"http://openinsider.com/screener?fd=-1&fdr={rng}"
               f"&xp={xp}&xs={xs}&cnt={cnt}&sortcol=0")
        try:
            h = urllib.request.urlopen(urllib.request.Request(url, headers=_OI_UA),
                                       timeout=25).read().decode("utf-8", "ignore")
            mt = re.search(r'<table[^>]*class="[^"]*tinytable[^"]*"[^>]*>(.*?)</table>',
                           h, re.S | re.I)
            if not mt:
                return 0
            n = 0
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", mt.group(1), re.S | re.I):
                cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
                if len(cells) < 13:
                    continue
                txt = re.sub(r"<[^>]+>", "", cells[7])
                if (xp and "P - Purchase" in txt) or (xs and "S - Sale" in txt):
                    n += 1
            time.sleep(0.15)
            return n
        except Exception:
            return None
    n = q(1, last)
    if n is None:
        return None
    if n >= cnt:                                   # 截斷 → 半月拆
        a, b = q(1, 15), q(16, last)
        if a is not None and b is not None:
            return a + b
    return n


def _load_insider_seed():
    """讀 committed 靜態種子檔(engine/insider_seed.json,一次性離線回抓的歷史買/賣月序)。"""
    try:
        with io.open(os.path.join(HERE, "insider_seed.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def fetch_insider_ratio(prev=None, refresh_months=2):
    """全市場內部人「買賣比(筆數)」月頻。ratio = 買筆 ÷ 賣筆(OpenInsider,分開查買/賣避免 cnt 截斷)。
    基底=committed 種子檔(離線回抓的歷史);疊上 prev(線上累積)較新月;每次只即時刷新最近
    refresh_months 月(含當月MTD,~40秒/月),避免 CI 逐月重抓(單月賣單查詢就 ~35 秒)。
    失敗仍回種子。無種子且抓不到 → None(前端該卡自動隱藏)。"""
    try:
        base = {}                                  # 'May-26' -> (buys, sells)
        seed = _load_insider_seed()
        for l, b, s in zip(seed.get("months", []), seed.get("buys", []), seed.get("sells", [])):
            if b is not None and s is not None:
                base[l] = (b, s)
        for l, b, s in zip((prev or {}).get("months") or [], (prev or {}).get("buys") or [],
                           (prev or {}).get("sells") or []):
            if b is not None and s is not None:
                base[l] = (b, s)
        budget = [refresh_months * 4 + 2]
        today = datetime.date.today()
        y, m = today.year, today.month
        for _ in range(max(1, refresh_months)):
            b = _oi_month_side(y, m, 1, 0, budget)
            s = _oi_month_side(y, m, 0, 1, budget)
            if b is not None and s is not None:
                base[_MON_NAMES[m - 1] + "-" + f"{y % 100:02d}"] = (b, s)
            m -= 1
            if m == 0:
                y -= 1; m = 12
        if len(base) < 2:
            return None
        months = sorted((k for k in base if _month_key(k)), key=_month_key)
        buys = [base[l][0] for l in months]
        sells = [base[l][1] for l in months]
        ratio = [round(s / b, 3) if b else None for b, s in zip(buys, sells)]   # 賣/買
        return {"months": months, "buys": buys, "sells": sells, "ratio": ratio,
                "current": ratio[-1], "as_of": today.strftime("%Y-%m-%d"),
                "unit": "賣筆/買筆"}
    except Exception:
        return None


_AI_CAPEX_COMP = [
    ("MSFT",  "0000789019", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("AMZN",  "0001018724", "PaymentsToAcquireProductiveAssets"),
    ("GOOGL", "0001652044", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("META",  "0001326801", "PaymentsToAcquirePropertyPlantAndEquipment"),
]


def _sec_quarterly_capex(cik, concept):
    """SEC XBRL 單概念 → 日曆季 capex($B)。以財年起始日錨定 FYTD 點逐季差分(排除 TTM/年度誤植)。
    財年起始 = 各點 start 的 (月,日) 眾數;只留 start 落該日的 FYTD 點,依財年分組後累計差分。回 {'2026Q1':30.9,...}。"""
    from collections import Counter
    def cq(d):
        y, m = int(d[:4]), int(d[5:7]); return f"{y}Q{(m - 1) // 3 + 1}"
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json",
            headers={"User-Agent": "stockview-research contact@stockview.example"}),
            timeout=25).read().decode("utf-8", "ignore"))
        pts = [(u["start"], u["end"], u["val"]) for u in j.get("units", {}).get("USD", [])
               if u.get("start") and u.get("end") and u.get("val") is not None]
        if len(pts) < 8:
            return {}
        md = Counter((s[5:7], s[8:10]) for s, _, _ in pts).most_common(1)[0][0]
        fysuffix = f"-{md[0]}-{md[1]}"
        grp = {}
        for s, e, v in pts:
            if s.endswith(fysuffix):
                grp.setdefault(s, {})[e] = v          # 同 end 多筆取後者(值一致)
        disc = {}
        for s, d in grp.items():
            prev = 0.0
            for e in sorted(d):
                disc[cq(e)] = round((d[e] - prev) / 1e9, 3); prev = d[e]
        return disc
    except Exception:
        return {}


def _q_index(q):
    y, k = q.split("Q"); return int(y) * 4 + int(k) - 1


def fetch_ai_capex(keep=28):
    """AI/雲端巨頭季度資本開支加總(MSFT/AMZN/GOOGL/META)+ YoY/環比增速。SEC XBRL 免key。
    回近 keep 季(4 家齊全者);失敗回 None → 前端該卡自動隱藏。"""
    try:
        per = {t: _sec_quarterly_capex(cik, con) for t, cik, con in _AI_CAPEX_COMP}
        if any(len(v) < 8 for v in per.values()):
            return None
        common = sorted(set.intersection(*[set(v) for v in per.values()]), key=_q_index)
        if len(common) < 6:
            return None
        common = common[-keep:]
        capex = [round(sum(per[t][q] for t in per), 2) for q in common]
        idx = {q: capex[i] for i, q in enumerate(common)}
        yoy = [round((idx[q] / idx[f"{int(q[:4])-1}Q{q[-1]}"] - 1) * 100, 1)
               if f"{int(q[:4])-1}Q{q[-1]}" in idx and idx[f"{int(q[:4])-1}Q{q[-1]}"] else None
               for q in common]
        qoq = [round((capex[i] / capex[i - 1] - 1) * 100, 1) if i and capex[i - 1] else None
               for i in range(len(capex))]
        return {"quarters": common, "capex": capex, "yoy": yoy, "qoq": qoq,
                "companies": [t for t, _, _ in _AI_CAPEX_COMP],
                "current": capex[-1], "current_yoy": yoy[-1], "current_qoq": qoq[-1],
                "as_of_q": common[-1], "unit": "$B"}
    except Exception:
        return None


def _fred_monthly_map(sid, api_extra=""):
    """FRED 序列 → {'May-26': value}(依日期月份)。優先用官方 API(需 env FRED_API_KEY,雲端 CI 不被擋;
    api_extra 例 '&frequency=m&aggregation_method=eop&observation_start=1985-01-01'),無 key 退回
    公開 fredgraph.csv。皆重試 4 次。失敗回 {}。"""
    def _put(out, dt, v):
        try:
            y, m = int(dt[:4]), int(dt[5:7])
            out[f"{_MON_NAMES[m - 1]}-{y % 100:02d}"] = float(v)
        except Exception:
            pass
    key = os.environ.get("FRED_API_KEY", "").strip()
    for _ in range(4):
        try:
            if key:
                j = json.loads(urllib.request.urlopen(urllib.request.Request(
                    f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}"
                    f"&api_key={key}&file_type=json{api_extra}",
                    headers={"User-Agent": "Mozilla/5.0"}), timeout=30
                ).read().decode("utf-8", "ignore"))
                out = {}
                for o in j.get("observations", []):
                    if o.get("value") not in (None, "", "."):
                        _put(out, o.get("date", ""), o["value"])
                if out:
                    return out
            else:
                d = urllib.request.urlopen(urllib.request.Request(
                    f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}), timeout=30
                ).read().decode("utf-8", "ignore")
                out = {}
                for r in csv.reader(io.StringIO(d)):
                    if r and len(r) >= 2 and r[-1] not in ("", ".", r[0]):
                        _put(out, r[0], r[-1])
                if out:
                    return out
        except Exception:
            pass
        time.sleep(1.5)
    return {}


def fetch_ndx_m2():
    """Nasdaq-100 ÷ 美國 M2 貨幣供給 比值(月頻)。資產價格相對印鈔速度的估值/流動性指標。
    兩者皆用 FRED(NASDAQ100 日頻取月底 / M2SL $B),免 Yahoo 避免 CI 限流。失敗回 None。"""
    try:
        ndx = _fred_monthly_map("NASDAQ100", "&frequency=m&aggregation_method=eop&observation_start=1985-01-01")
        m2 = _fred_monthly_map("M2SL")                     # {Mon-YY: $B}
        common = sorted(set(ndx) & set(m2), key=_month_key)
        print(f"[ndx_m2] ndx={len(ndx)} m2={len(m2)} common={len(common)}")   # CI 診斷
        if len(common) < 24:
            return None
        ndx_s = [round(ndx[m], 1) for m in common]
        m2_s = [round(m2[m] / 1000, 3) for m in common]    # $兆
        ratio = [round(ndx[m] / (m2[m] / 1000), 1) for m in common]
        srt = sorted(ratio); cur = ratio[-1]
        pct = round(sum(1 for x in srt if x <= cur) / len(srt) * 100)
        return {"months": common, "ratio": ratio, "ndx": ndx_s, "m2": m2_s,
                "current": cur, "pctile": pct, "as_of": common[-1],
                "unit": "NDX / M2($兆)"}
    except Exception:
        return None


def _fetch_live_sentiment():
    """讀已部署線上 sentiment.json(供跨次累積月序);失敗回 None。"""
    try:
        return json.loads(urllib.request.urlopen(
            urllib.request.Request("https://stockview1.pages.dev/data/sentiment.json",
                                   headers={"User-Agent": "Mozilla/5.0"}), timeout=12
        ).read().decode("utf-8", "ignore"))
    except Exception:
        return None


def _tw_margin_loan_on(ymd):
    """TWSE MI_MARGN 指定日(YYYYMMDD)融資金額餘額(億);非交易日/失敗回 None。"""
    try:
        mj = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore"))
        if mj.get("stat") != "OK":
            return None
        tabs = mj.get("tables") or []
        if not tabs:
            return None
        for row in tabs[0].get("data", []):
            if row and "融資金額" in row[0]:
                return round(float(row[5].replace(",", "")) * 1000 / 1e8, 1)   # 仟元→元→億
        return None
    except Exception:
        return None


def _tw_month_end_loan(y, m, budget):
    """該月最後交易日融資餘額(億):月末日往前找最多 8 天。budget=[剩餘查詢數](就地遞減)。"""
    last = calendar.monthrange(y, m)[1]
    for d in range(last, max(0, last - 8), -1):
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        v = _tw_margin_loan_on(f"{y:04d}{m:02d}{d:02d}")
        if v is not None:
            return v
        time.sleep(0.12)
    return None


def fetch_tw_margin_balance(prev=None, years=10, query_budget=340):
    """台股融資餘額(億)月頻月環比,含最多 years 年月度歷史(TWSE MI_MARGN 各月月底)。
    增量:已在 prev(上次 sentiment.json 的 tw_margin)的月份不重查 → 首次補滿、之後幾乎零成本;
    query_budget 上限保護 CI 時間,超出的缺月留待下次排程補齊(前端 connectNulls 容缺)。
    失敗回 None → 前端該卡自動隱藏。"""
    try:
        budget = [query_budget]
        # 以近幾日最新一筆當「現在」錨點(當月至今值)
        now_bal = now_ym = now_date = None
        base = datetime.date.today()
        for i in range(0, 10):
            dt = base - datetime.timedelta(days=i)
            budget[0] -= 1
            v = _tw_margin_loan_on(dt.strftime("%Y%m%d"))
            if v is not None:
                now_bal, now_ym, now_date = v, (dt.year, dt.month), dt.strftime("%Y-%m-%d")
                break
            time.sleep(0.12)
        if now_bal is None:
            return None
        # 目標近 years*12 月 (y,m),舊→新
        ymonths, y, m = [], now_ym[0], now_ym[1]
        for _ in range(years * 12):
            ymonths.append((y, m))
            m -= 1
            if m == 0:
                y -= 1; m = 12
        ymonths.reverse()
        known = {lbl: v for lbl, v in zip((prev or {}).get("months") or [],
                                          (prev or {}).get("series") or [])}
        months, series = [], []
        for (yy, mm) in ymonths:
            lbl = _MON_NAMES[mm - 1] + "-" + f"{yy % 100:02d}"
            if (yy, mm) == now_ym:
                val = now_bal                       # 當月至今
            elif lbl in known:
                val = known[lbl]                    # 已知,不重查
            else:
                val = _tw_month_end_loan(yy, mm, budget) if budget[0] > 0 else None
            if val is not None:
                months.append(lbl); series.append(val)
        if len(series) < 2:
            return None
        mom = round((series[-1] / series[-2] - 1) * 100, 2) if series[-2] else None
        return {"bal": series[-1], "prev_bal": series[-2], "as_of": now_date,
                "mom_pct": mom, "months": months, "series": series, "unit": "億"}
    except Exception:
        return None


def fetch_micro_retail():
    """微台散戶多空比 = 散戶淨未平倉 ÷ 微台總未平倉(%)。
    散戶淨 = -(三大法人微型臺指未平倉多空淨額合計),反向指標。
    來源:期交所「三大法人-區分各契約」(取微型臺指三法人,各列未平倉淨額=倒數第2個數)
         + 「期貨每日交易行情(commodity_id=TMF)」首個小計列末欄=總未平倉 OI。
    歷史:回讀已發布 sentiment.json + 用單一 queryDate 向期交所逐日回補,首次即建 ~50 點走勢。"""
    def _g(url, data=None, ref=None, t=25):
        hd = {"User-Agent": "Mozilla/5.0"}
        if ref:
            hd["Referer"] = ref
        return urllib.request.urlopen(urllib.request.Request(
            url, data=(data.encode() if data else None), headers=hd), timeout=t
        ).read().decode("utf-8", "ignore")
    def _one_day(ds):
        # ds="YYYY/MM/DD";用單一 queryDate 查該日,回 (ymd, ratio, retail_net, oi) 或 None。
        # 以「每日行情報表 echo 日期 == 查詢日」確認確為該日資料(非交易日端點會回最新→剔除)。
        try:
            html = _g("https://www.taifex.com.tw/cht/3/futContractsDateExcel",
                      f"queryType=1&queryDate={ds}&commodityId=",
                      "https://www.taifex.com.tw/cht/3/futContractsDate")
            trs = re.split(r"<tr", html, flags=re.I)
            start = next((k for k, t in enumerate(trs)
                          if "微型臺指期貨" in t and len(re.findall(r">\s*-?[\d,]+\s*<", t)) >= 11), None)
            if start is None:
                return None
            net3 = 0
            for j in range(3):                         # 自營商 / 投信 / 外資 三列
                row = trs[start + j] if start + j < len(trs) else ""
                ints = [int(x.replace(",", "")) for x in re.findall(r">\s*(-?[\d,]+)\s*<", row)]
                if len(ints) < 11:
                    return None
                net3 += ints[-2]                       # 未平倉多空淨額口數(末欄=金額,取倒數第2)
            rep = _g("https://www.taifex.com.tw/cht/3/futDailyMarketExcel",
                     f"queryDate={ds}&commodity_id=TMF",
                     "https://www.taifex.com.tw/cht/3/futDailyMarketReport")
            oi = None
            for line in re.split(r"</tr>", rep, flags=re.I):
                if "小計" in line:                      # 首個小計列(單式契約)末欄=總未平倉
                    ii = re.findall(r"-?[\d,]+", re.sub(r"<[^>]*>", " ", line))
                    if ii:
                        oi = int(ii[-1].replace(",", "")); break
            if not oi or oi <= 0:
                return None
            m = re.search(r"日期[：:]\s*(\d{4}/\d{2}/\d{2})", rep)
            if not m or m.group(1) != ds:              # 報表日期須等於查詢日,否則為非交易日回最新→剔除
                return None
            retail_net = -net3
            return ds.replace("/", ""), round(retail_net / oi * 100, 2), retail_net, oi
        except Exception:
            return None
    try:
        hist = {}                                      # ymd -> ratio(既有歷史 + 本次回補)
        try:
            prev = json.loads(_g("https://stockview1.pages.dev/data/sentiment.json", t=10))
            for lv in prev.get("levels", []):
                if lv.get("sym") == "TWMICRORETAIL":
                    for dd, vv in zip(lv.get("dates") or [], lv.get("spark") or []):
                        hist[dd] = vv
        except Exception:
            pass
        # 從台北今天往回逐交易日:先確保拿到最新有效日(retail/oi),並回補缺漏到 ~60 點(單次最多查 55 天)。
        tpe = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        last = None
        queries = 0
        for back in range(0, 80):
            if len(hist) >= 60 or queries >= 55:
                break
            dt = tpe - datetime.timedelta(days=back)
            if dt.weekday() >= 5:                       # 略過週末
                continue
            ymd = dt.strftime("%Y%m%d")
            if last is not None and ymd in hist:        # 已拿到最新日、且該日已有 → 略過
                continue
            queries += 1
            r = _one_day(dt.strftime("%Y/%m/%d"))
            if r:
                hist[r[0]] = r[1]
                if last is None:
                    last = r                            # 最近一個有效交易日
        if not hist:
            return None
        dates = sorted(hist)[-60:]
        series = [hist[k] for k in dates]
        ratio = series[-1]
        retail_net = last[2] if last else None
        oi = last[3] if last else None
        diff = round(series[-1] - series[-2], 2) if len(series) >= 2 else None
        return {"sym": "TWMICRORETAIL", "label": "微台散戶多空比",
                "note": "期交所·散戶部位反推·反向指標", "unit": "pct",
                "read": "散戶淨未平倉÷總未平倉(口數)。正=散戶偏多、負=偏空。"
                        "反向指標:散戶極度偏多常見過熱、極度偏空常見底部(門檻待歷史校準)。",
                "level": ratio, "diff": diff, "spark": series, "dates": dates,
                "retail_lots": retail_net, "oi": oi,
                "url": "https://www.taifex.com.tw/cht/3/futContractsDate", "src": "期交所"}
    except Exception:
        return None


def _factset_week(dd, _io):
    """抓某週五(dd)的 FactSet Earnings Insight PDF,回 (fwd_eps, a5, a10) 或 None。"""
    import urllib.parse
    base = ("https://advantage.factset.com/hubfs/Website/Resources Section/"
            "Research Desk/Earnings Insight/EarningsInsight_")
    for suf in ("", "A", "B"):
        url = base + dd.strftime("%m%d%y") + suf + ".pdf"
        try:
            raw = urllib.request.urlopen(urllib.request.Request(
                urllib.parse.quote(url, safe=":/"), headers={"User-Agent": "Mozilla/5.0"}),
                timeout=30).read()
            if raw[:4] != b"%PDF" or len(raw) < 200000:
                continue
            import pypdf
            r = pypdf.PdfReader(_io.BytesIO(raw))
            txt = "\n".join((p.extract_text() or "") for p in r.pages[:16])   # PE句約p5、收盤價約p11,解前16頁省時又夠用
            mp = re.search(r"forward 12-month P/E ratio is ([0-9]{1,2}\.[0-9])", txt)
            mx = re.search(r"closing price of ([0-9]{3,5}\.[0-9]{2})", txt)
            if mp and mx:
                m5 = re.search(r"5-year average \(([0-9]{1,2}\.[0-9])\)", txt)
                m10 = re.search(r"10-year average \(([0-9]{1,2}\.[0-9])\)", txt)
                return (round(float(mx.group(1)) / float(mp.group(1)), 2),
                        float(m5.group(1)) if m5 else None, float(m10.group(1)) if m10 else None)
        except Exception:
            continue
    return None


def fetch_sp500_fwd_pe():
    """S&P500 forward P/E:逐「週」抓 FactSet Earnings Insight 取「當週」forward EPS(反推),
    配 ^GSPC 日收盤 → 每天用「該日所屬週的實際 EPS」算 forward P/E(歷史準確,非用現值近似)。
    首跑回補近 ~26 週各週 EPS,之後每跑只補新一週(已發布 json 回讀累積)。
    標線:>21.5 偏高、<16 偏低、<14 超賣(使用者設定)。"""
    import io as _io
    prev = {}
    try:
        pj = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://stockview1.pages.dev/data/sentiment.json",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode("utf-8", "ignore"))
        prev = pj.get("sp500_fwd_pe") or {}
    except Exception:
        pass
    eps_hist = dict(prev.get("eps_hist") or {})    # {報告週五 ISO: forward EPS}
    a5, a10 = prev.get("avg5"), prev.get("avg10")
    et = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    prev_latest = max(eps_hist) if eps_hist else ""
    got_cnt, tries, newest_av, newest_iso = 0, 0, None, ""
    for back in range(0, 3300):                    # 回溯 ~9 年的週五(FactSet PDF 約存到 2017)
        dd = et.date() - datetime.timedelta(days=back)
        if dd.weekday() != 4:
            continue
        iso = dd.isoformat()
        ym = iso[:7]
        if iso in eps_hist or any(k[:7] == ym for k in eps_hist):
            continue                               # 每月只抓一份(forward EPS 月變化小,月粒度夠準)
        if got_cnt >= 70:                          # 單跑「成功」上限 70 份(一次回補約 ~7 年)
            break
        if tries >= 360:                           # 探測上限(404 那週只是沒發報,不佔成功額度;但總探測有限)
            break
        tries += 1
        got = _factset_week(dd, _io)
        if got:
            eps_hist[iso] = got[0]
            got_cnt += 1
            if iso >= prev_latest and iso > newest_iso:   # 只用「最新一期」的 5/10 年均,避免被舊月份覆蓋
                newest_av, newest_iso = (got[1], got[2]), iso
    if newest_av:
        a5 = newest_av[0] or a5; a10 = newest_av[1] or a10
    eps_hist = dict(sorted(eps_hist.items())[-96:])    # 保留近 ~96 期(~8 年)
    if not eps_hist:
        return None
    sorted_eps = sorted(eps_hist.items())          # [(報告ISO, eps), ...] 由舊到新
    latest_eps = sorted_eps[-1][1]
    earliest = sorted_eps[0][0]
    def eps_at(day):                               # 該日生效 EPS = 不晚於該日的最近一期
        e = sorted_eps[0][1]
        for dt, val in sorted_eps:
            if dt <= day:
                e = val
            else:
                break
        return e
    try:
        ch = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=10y",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore"))
        res = ch["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        rows = []
        for t, c in zip(ts, cl):
            if c is None:
                continue
            ds = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
            if ds >= earliest:                     # 只取有 forward EPS 的區間
                rows.append((ds, c))
        live = (res.get("meta") or {}).get("regularMarketPrice") or (rows[-1][1] if rows else None)
    except Exception:
        return None
    if not rows:
        return None
    samp = rows[::5]                               # 週取樣(每5交易日)讓長區間圖輕量
    if samp[-1] != rows[-1]:
        samp.append(rows[-1])
    dates = [d for d, _ in samp]
    pe = [round(c / eps_at(d), 1) for d, c in samp]
    cur = round(live / latest_eps, 1)
    spy = None                                     # SPY 收盤價(右軸比較):對齊 forward PE 取樣日期
    try:
        ch2 = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=10y",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore"))
        r2 = ch2["chart"]["result"][0]
        ts2, cl2 = r2["timestamp"], r2["indicators"]["quote"][0]["close"]
        smap = {}
        for t, c in zip(ts2, cl2):
            if c is not None:
                smap[datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")] = c
        skeys = sorted(smap)

        def spy_at(day):                           # 不晚於該日的最近一筆 SPY 收盤
            val = None
            for k in skeys:
                if k <= day:
                    val = smap[k]
                else:
                    break
            return val
        spy = [round(spy_at(d), 2) if spy_at(d) is not None else None for d in dates]
    except Exception:
        spy = None
    return {"label": "S&P500 Forward P/E", "cur": cur, "fwd_eps": latest_eps,
            "report_date": sorted_eps[-1][0], "avg5": a5, "avg10": a10,
            "eps_hist": eps_hist, "dates": dates, "pe": pe, "spy": spy,
            "thr": {"high": 21.5, "low": 20, "oversold": 16}, "src": "FactSet 週報(逐週 EPS)+ ^GSPC + SPY 價"}


def fetch_0dte():
    """SPY/QQQ 0DTE(當日到期)選擇權 Put/Call Ratio(成交量)。Yahoo 選擇權鏈(需 crumb)。
    歷史回讀已發布 sentiment.json 逐日累積 spark(Yahoo 無歷史選擇權量,只能往後累積)。"""
    import http.cookiejar
    import urllib.parse
    try:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.addheaders = [("User-Agent", "Mozilla/5.0")]
        try:
            op.open("https://fc.yahoo.com/", timeout=10)
        except Exception:
            pass
        crumb = op.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10).read().decode("utf-8", "ignore").strip()
        if not crumb or len(crumb) > 30:
            return None
        res = {}
        for sym in ("SPY", "QQQ"):
            try:
                u = "https://query1.finance.yahoo.com/v7/finance/options/" + sym + "?crumb=" + urllib.parse.quote(crumb)
                d = json.loads(op.open(u, timeout=12).read().decode("utf-8", "ignore"))
                oc = (d["optionChain"]["result"][0].get("options") or [{}])[0]
                cv = sum((c.get("volume") or 0) for c in oc.get("calls", []))
                pv = sum((p.get("volume") or 0) for p in oc.get("puts", []))
                res[sym] = {"pcr": round(pv / cv, 2) if cv > 0 else None, "vol": cv + pv}
            except Exception:
                pass
        spy = res.get("SPY") or {}
        if spy.get("pcr") is None:
            return None
        pcr = spy["pcr"]
        qqq = res.get("QQQ") or {}
        tpe = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        ymd = tpe.strftime("%Y%m%d")
        dates, series = [], []
        try:
            prev = json.loads(urllib.request.urlopen(urllib.request.Request(
                "https://stockview1.pages.dev/data/sentiment.json",
                headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode("utf-8", "ignore"))
            for lv in prev.get("levels", []):
                if lv.get("sym") == "ODTE_PCR":
                    dates = list(lv.get("dates") or [])
                    series = list(lv.get("spark") or [])
        except Exception:
            pass
        if dates and dates[-1] == ymd:
            series[-1] = pcr
        else:
            dates.append(ymd); series.append(pcr)
        dates, series = dates[-60:], series[-60:]
        diff = round(series[-1] - series[-2], 2) if len(series) >= 2 else None
        qtxt = ("目前 QQQ %.2f。" % qqq["pcr"]) if qqq.get("pcr") is not None else ""
        return {
            "sym": "ODTE_PCR", "label": "0DTE Put/Call", "note": "SPY 當日到期選擇權·情緒", "unit": "ratio",
            "read": "0DTE(當日到期)選擇權 Put/Call 量比。>1=put 多(避險/偏空)、<1=call 多(偏多/投機);"
                    "≥1.3 避險濃(常見反彈)、≤0.7 過度樂觀(留意回檔)。" + qtxt + "Yahoo 延遲/盤後量。",
            "level": pcr, "diff": diff, "spark": series, "dates": dates,
            "qqq_pcr": qqq.get("pcr"), "spy_vol": spy.get("vol"), "src": "Yahoo 選擇權",
        }
    except Exception:
        return None




def fetch_cot_spx():
    """CFTC TFF(Traders in Financial Futures) - E-mini S&P 500 期貨定位。
    Leveraged Funds = 槓桿資金/CTA 代理；Asset Manager = 機構長線。
    資料來源：www.cftc.gov 年度 ZIP/CSV，每週五發布，免費公開。"""
    import zipfile
    MARKET = "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"

    def _dl_year(year):
        url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
            ).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            fname = next(n for n in z.namelist() if n.lower().endswith(".txt") or n.lower().endswith(".csv"))
            return z.open(fname).read().decode("latin-1", "ignore")
        except Exception:
            return ""

    try:
        import csv as _csv
        year = datetime.datetime.now().year
        raw = ""
        for y in range(year - 4, year + 1):
            raw += _dl_year(y)

        def _int(v):
            try: return int(v.strip() or 0)
            except: return 0

        seen, rows = set(), []
        for line in raw.split("\n"):
            if not line.strip() or MARKET not in line:
                continue
            cols = next(_csv.reader([line]))
            if len(cols) < 16 or cols[0].strip() != MARKET:
                continue
            d = cols[2].strip()[:10]
            if not d or d in seen:
                continue
            seen.add(d)
            rows.append({
                "date":  d,
                "lev_l": _int(cols[14]), "lev_s": _int(cols[15]),
                "am_l":  _int(cols[11]), "am_s":  _int(cols[12]),
            })

        rows.sort(key=lambda r: r["date"])
        rows = rows[-260:]
        if not rows:
            return None

        dates   = [r["date"]               for r in rows]
        lev_net = [r["lev_l"] - r["lev_s"] for r in rows]
        am_net  = [r["am_l"]  - r["am_s"]  for r in rows]

        def _pctile(arr):
            # 排名分位:有幾%的歷史值 <= 現值(與圖上 decile 線/過多過空門檻同口徑)。
            # 舊版用 min-max 區間位置會被極端值拉歪、與圖對不上,已改。
            if len(arr) < 2: return 50
            cur = arr[-1]; n = len(arr)
            return round(sum(1 for x in arr if x <= cur) / n * 100)

        lev_prev = lev_net[-2] if len(lev_net) >= 2 else lev_net[-1]
        am_prev  = am_net[-2]  if len(am_net)  >= 2 else am_net[-1]

        _sorted = sorted(lev_net)
        _n = len(_sorted)
        lo_thresh = _sorted[max(0, int(_n * 0.20) - 1)]
        hi_thresh = _sorted[min(_n - 1, int(_n * 0.80))]
        buy_sigs, sell_sigs = [], []
        for i in range(1, len(lev_net)):
            if lev_net[i] <= lo_thresh and lev_net[i - 1] > lo_thresh:
                buy_sigs.append(i)
            elif lev_net[i] >= hi_thresh and lev_net[i - 1] < hi_thresh:
                sell_sigs.append(i)

        spy_prices = [None] * len(dates)
        try:
            import yfinance as yf
            import datetime as _dt
            # 使用 Ticker.history() 確保欄位為 flat(不受 yfinance 版本 MultiIndex 影響)
            _spy_hist = yf.Ticker("SPY").history(period="10y", interval="1wk")
            _spy_map = {}
            for idx in _spy_hist.index:
                try:
                    v = float(_spy_hist.at[idx, "Close"])
                    if v == v:  # 排除 NaN
                        _spy_map[str(idx)[:10]] = round(v, 2)
                except Exception:
                    pass
            print(f"[cot_spx] SPY 週收盤 {len(_spy_map)} 筆")
            for i, d in enumerate(dates):
                if d in _spy_map:
                    spy_prices[i] = _spy_map[d]
                    continue
                _dt_obj = _dt.datetime.strptime(d, "%Y-%m-%d")
                for delta in range(1, 6):
                    for sign in (1, -1):
                        nd = (_dt_obj + _dt.timedelta(days=delta * sign)).strftime("%Y-%m-%d")
                        if nd in _spy_map:
                            spy_prices[i] = _spy_map[nd]
                            break
                    else:
                        continue
                    break
            filled = sum(1 for p in spy_prices if p is not None)
            print(f"[cot_spx] SPY 對齊 {filled}/{len(dates)} 週")
        except Exception as e:
            print(f"[cot_spx] SPY 失敗: {e}")

        return {
            "dates":      dates,
            "lev_net":    lev_net,
            "am_net":     am_net,
            "spy_prices": spy_prices,
            "buy_sigs":   buy_sigs,
            "sell_sigs":  sell_sigs,
            "lo_thresh":  lo_thresh,
            "hi_thresh":  hi_thresh,
            "lev_cur":    lev_net[-1],
            "lev_wow":    lev_net[-1] - lev_prev,
            "lev_pctile": _pctile(lev_net),
            "am_cur":     am_net[-1],
            "am_wow":     am_net[-1] - am_prev,
            "am_pctile":  _pctile(am_net),
            "src":        "CFTC TFF Disaggregated / E-mini S&P 500",
        }
    except Exception as e:
        print(f"[cot_spx] 失敗: {e}")
        return None

def build():
    levels, failed = fetch_levels()
    cor = fetch_cor1m()
    if cor:
        levels.append(cor)
    else:
        failed.append("COR1M")
    micro = fetch_micro_retail()        # 微台散戶多空比(期交所)
    if micro:
        levels.append(micro)
    else:
        failed.append("TWMICRORETAIL")
    dte = fetch_0dte()                   # 0DTE 選擇權 Put/Call(Yahoo)
    if dte:
        levels.append(dte)
    else:
        failed.append("ODTE_PCR")
    breadth = market_breadth()
    fng = fetch_fear_greed()
    # 「保證金借款」大圖:先讀上次線上 sentiment.json → 台股增量回補只查缺月、跨次累積成長
    prev_sent = _fetch_live_sentiment()
    leverage = fetch_leverage()
    tw_margin = fetch_tw_margin_balance(prev=(prev_sent or {}).get("tw_margin"))
    if leverage and leverage.get("margin_months") and leverage.get("margin_series"):
        pv = (prev_sent or {}).get("leverage") or {}
        mm, ms = _merge_months(pv.get("margin_months"), pv.get("margin_series"),
                               leverage["margin_months"], leverage["margin_series"])
        leverage["margin_months"], leverage["margin_series"] = mm, ms
    if tw_margin and tw_margin.get("months") and tw_margin.get("series"):
        pv = (prev_sent or {}).get("tw_margin") or {}
        mm, ms = _merge_months(pv.get("months"), pv.get("series"),
                               tw_margin["months"], tw_margin["series"])
        tw_margin["months"], tw_margin["series"] = mm, ms
        if len(ms) >= 2 and ms[-2]:
            tw_margin["bal"], tw_margin["prev_bal"] = ms[-1], ms[-2]
            tw_margin["mom_pct"] = round((ms[-1] / ms[-2] - 1) * 100, 2)
    # 疊圖用:各市場指數對齊 margin 月序(美股 S&P500、台股 加權指數)
    if leverage and leverage.get("margin_months"):
        gm = _monthly_index_map("^GSPC", "1996-12-01")
        leverage["sp500_series"] = [gm.get(l) for l in leverage["margin_months"]]
    if tw_margin and tw_margin.get("months"):
        tm = _monthly_index_map("^TWII", "2016-01-01")
        tw_margin["twii_series"] = [tm.get(l) for l in tw_margin["months"]]
    # 全市場內部人買賣比(筆數,月頻,OpenInsider)+ S&P500 疊圖,放 PI 下方
    insider = fetch_insider_ratio(prev=(prev_sent or {}).get("insider_ratio"))
    ndx_m2 = fetch_ndx_m2() or (prev_sent or {}).get("ndx_m2")   # FRED 失敗沿用線上 last-good
    if insider and insider.get("months"):
        gi = _monthly_index_map("^GSPC", "2005-12-01")
        insider["sp500_series"] = [gi.get(l) for l in insider["months"]]
    cot_spx = fetch_cot_spx()
    if not cot_spx:
        failed.append("COT_SPX")
    tw_margin_ratio = fetch_tw_margin_ratio()
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance + CNN F&G + FINRA/WorldBank + CFTC",
        "levels": levels,
        "breadth": breadth,
        "fear_greed": fng,
        "leverage": leverage,
        "tw_margin": tw_margin,
        "tw_margin_ratio": tw_margin_ratio,
        "insider_ratio": insider,
        "ai_capex": fetch_ai_capex(),
        "ndx_m2": ndx_m2,
        "sp500_fwd_pe": fetch_sp500_fwd_pe(),
        "cot_spx": cot_spx,
        "failed": failed,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "sentiment.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    _us_n = len((leverage or {}).get("margin_months") or [])
    _tw_n = len((tw_margin or {}).get("months") or [])
    _in_n = len((insider or {}).get("months") or [])
    _cx_n = len((payload.get("ai_capex") or {}).get("quarters") or [])
    print(f"[sentiment] -> data/sentiment.json  (levels {len(levels)}, "
          f"breadth {'ok' if breadth else 'none'}, F&G {'ok' if fng else 'none'}, "
          f"margin US {_us_n}月/TW {_tw_n}月, insider {_in_n}月, ai_capex {_cx_n}季, 失敗 {len(failed)})")


if __name__ == "__main__":
    build()

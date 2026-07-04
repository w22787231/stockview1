# -*- coding: utf-8 -*-
"""總體市場 macro 匯出：指數 + 類股/主題 ETF。
- 一般標的：收盤價 + 今日漲跌%。
- 收益率/VIX(yield_like=True)：顯示水準 + 與昨日差(bps；VIX 用點)。
輸出 ../data/macro.json。
"""
import sys, os, io, json, datetime, csv, ssl, unicodedata
import urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings; warnings.filterwarnings("ignore")
import yfinance as yf

_CBC_SSL = ssl.create_default_context()
_CBC_SSL.check_hostname = False
_CBC_SSL.verify_mode = ssl.CERT_NONE        # 央行 OpenData 憑證鏈在部分環境驗不過 → 容錯

DATA_DIR = os.path.join(HERE, "..", "data")

# 指數總覽。yield_like=True 者以「水準 + bps差」呈現(不是 %漲跌)。
INDICES = [
    {"sym": "^TWII",     "label": "台股加權",        "note": "台灣加權指數 TAIEX"},
    {"sym": "^TWOII",    "label": "櫃買指數",        "note": "台灣櫃買 OTC/TPEx"},
    {"sym": "^GSPC",     "label": "S&P 500",        "note": "標普500指數"},
    {"sym": "^IXIC",     "label": "Nasdaq",         "note": "那斯達克綜合"},
    {"sym": "^SOX",      "label": "SOX 半導體",      "note": "費城半導體指數"},
    {"sym": "^TNX",      "label": "10Y 公債殖利率",  "note": "美國10年期", "yield_like": True, "unit": "bps"},
    {"sym": "GC=F",      "label": "黃金",           "note": "黃金期貨"},
    {"sym": "CL=F",      "label": "原油 WTI",        "note": "西德州原油期貨"},
    {"sym": "DX-Y.NYB",  "label": "美元指數",        "note": "DXY"},
]

# 類股 / 主題 ETF。type 為類型標註。
ETFS = [
    # 11 大 SPDR 類股
    {"sym": "XLK",  "label": "科技",     "type": "類股"},
    {"sym": "XLF",  "label": "金融",     "type": "類股"},
    {"sym": "XLE",  "label": "能源",     "type": "類股"},
    {"sym": "XLV",  "label": "醫療保健", "type": "類股"},
    {"sym": "XLY",  "label": "非必需消費","type": "類股"},
    {"sym": "XLP",  "label": "必需消費", "type": "類股"},
    {"sym": "XLI",  "label": "工業",     "type": "類股"},
    {"sym": "XLC",  "label": "通訊服務", "type": "類股"},
    {"sym": "XLB",  "label": "原物料",   "type": "類股"},
    {"sym": "XLU",  "label": "公用事業", "type": "類股"},
    {"sym": "XLRE", "label": "房地產",   "type": "類股"},
    # 熱門主題
    {"sym": "SMH",  "label": "半導體",     "type": "主題"},
    {"sym": "SOXX", "label": "半導體(SOXX)","type": "主題"},
    {"sym": "ARKK", "label": "創新顛覆",   "type": "主題"},
    {"sym": "IBB",  "label": "生技",       "type": "主題"},
    {"sym": "XBI",  "label": "生技(等權)", "type": "主題"},
    {"sym": "ITB",  "label": "房屋建商",   "type": "主題"},
    {"sym": "XOP",  "label": "石油開採",   "type": "主題"},
]


def _round(x, n=2):
    try: return round(float(x), n)
    except Exception: return None


def fetch_all(symbols):
    df = yf.download(symbols, period="5d", interval="1d",
                     group_by="ticker", progress=False, auto_adjust=False)
    out = {}
    for s in symbols:
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            if len(sub) < 2:
                out[s] = None; continue
            last = float(sub["Close"].iloc[-1])
            prev = float(sub["Close"].iloc[-2])
            out[s] = {"last": last, "prev": prev}
        except Exception:
            out[s] = None
    return out


def fetch_m1b_m2(months=72):
    """央行貨幣總計數(OpenData EF15M01.csv):取 M1B/M2 年增率,算 M1B−M2 差。
    M1B>M2(差為正)=黃金交叉、資金動能轉強;反之死亡交叉。NFKC 正規化全形 Ｍ１Ｂ→M1B 比對欄位。"""
    url = "https://www.cbc.gov.tw/public/data/OpenData/經研處/EF15M01.csv"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(
            urllib.parse.quote(url, safe=":/"), headers={"User-Agent": "Mozilla/5.0"}),
            timeout=25, context=_CBC_SSL).read()
        txt = None
        for enc in ("utf-8-sig", "utf-8", "big5"):
            try:
                txt = raw.decode(enc); break
            except Exception:
                continue
        if not txt:
            return None
        rows = list(csv.reader(io.StringIO(txt)))
        hdr = [unicodedata.normalize("NFKC", h).replace(" ", "") for h in rows[0]]
        def col(key):
            return next((i for i, h in enumerate(hdr) if key in h), None)
        i_m1b, i_m2 = col("M1B-年增率"), col("M2-年增率")
        if i_m1b is None or i_m2 is None:
            return None
        dates, m1b, m2, spread = [], [], [], []
        for r in rows[1:]:
            if len(r) <= max(i_m1b, i_m2):
                continue
            a, b = _round(r[i_m1b], 2), _round(r[i_m2], 2)
            if a is None or b is None:
                continue
            dates.append(r[0].strip()); m1b.append(a); m2.append(b); spread.append(round(a - b, 2))
        if not dates:
            return None
        return {"dates": dates[-months:], "m1b": m1b[-months:], "m2": m2[-months:],
                "spread": spread[-months:], "src": "中央銀行 貨幣總計數",
                "url": "https://www.cbc.gov.tw/tw/np-643-1.html"}
    except Exception:
        return None


def fetch_us_reserves(series="WRESBAL", start="2010-01-01"):
    """美國-聯準會存款機構準備金(週,WRESBAL,十億美元)← FRED API(需 FRED_API_KEY)。
    準備金=銀行體系流動性;QT 抽準備金、QE 灌準備金,是美元流動性關鍵指標。無 key 回 None。"""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("[macro] FRED_API_KEY 未設,跳過 us_reserves")
        return None
    try:
        url = ("https://api.stlouisfed.org/fred/series/observations"
               "?series_id=%s&api_key=%s&file_type=json&observation_start=%s" % (series, key, start))
        j = json.loads(urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8"))
        dates, vals = [], []
        for o in j.get("observations") or []:
            v = o.get("value")
            if v in (None, "", "."):
                continue
            try:
                fv = float(v)
            except ValueError:
                continue
            dates.append(o["date"]); vals.append(round(fv, 1))
        if len(dates) < 2:
            return None
        return {"label": "美國-聯準會存款機構準備金(週)", "unit": "十億美元",
                "dates": dates, "values": vals, "cur": vals[-1], "as_of": dates[-1],
                "src": "FRED WRESBAL(Reserve Balances with Federal Reserve Banks)"}
    except Exception as e:
        print("[macro] us_reserves 失敗:", e)
        return None


def build():
    all_syms = [x["sym"] for x in INDICES] + [x["sym"] for x in ETFS]
    px = fetch_all(all_syms)

    indices, etfs, failed = [], [], []

    for it in INDICES:
        d = px.get(it["sym"])
        if not d:
            failed.append(it["sym"]); continue
        last, prev = d["last"], d["prev"]
        row = {"sym": it["sym"], "label": it["label"], "note": it.get("note", "")}
        if it.get("yield_like"):
            unit = it.get("unit", "bps")
            # 收益率代號(^TNX/^TYX/^IRX)在 yfinance 上值=百分比數字(如 4.3 表 4.3%)。
            # 與昨日差：bps = (last-prev)*100；VIX 用點(pt)。
            row["mode"] = "yield"
            row["level"] = _round(last, 2)
            if unit == "bps":
                row["diff"] = _round((last - prev) * 100.0, 1); row["unit"] = "bps"
            else:
                row["diff"] = _round(last - prev, 2); row["unit"] = "pt"
        else:
            row["mode"] = "price"
            row["last"] = _round(last, 2)
            row["chg"] = _round((last / prev - 1.0) * 100.0, 2)
        indices.append(row)

    for it in ETFS:
        d = px.get(it["sym"])
        if not d:
            failed.append(it["sym"]); continue
        last, prev = d["last"], d["prev"]
        etfs.append({"sym": it["sym"], "label": it["label"], "type": it["type"],
                     "last": _round(last, 2),
                     "chg": _round((last / prev - 1.0) * 100.0, 2)})

    # ETF 預設依今日漲跌由高到低
    etfs.sort(key=lambda r: (r["chg"] if r["chg"] is not None else -999), reverse=True)

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily)",
        "indices": indices,
        "etfs": etfs,
        "m1b_m2": fetch_m1b_m2(),
        "us_reserves": fetch_us_reserves(),
        "failed": failed,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "macro.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[macro] -> data/macro.json  (指數 {len(indices)}, ETF {len(etfs)}, 失敗 {len(failed)})")
    if failed:
        print("[macro] 失敗:", ", ".join(failed))


if __name__ == "__main__":
    build()

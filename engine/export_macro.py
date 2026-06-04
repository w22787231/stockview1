# -*- coding: utf-8 -*-
"""總體市場 macro 匯出：指數 + 類股/主題 ETF。
- 一般標的：收盤價 + 今日漲跌%。
- 收益率/VIX(yield_like=True)：顯示水準 + 與昨日差(bps；VIX 用點)。
輸出 ../data/macro.json。
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings; warnings.filterwarnings("ignore")
import yfinance as yf

DATA_DIR = os.path.join(HERE, "..", "data")

# 指數總覽。yield_like=True 者以「水準 + bps差」呈現(不是 %漲跌)。
INDICES = [
    {"sym": "^TWII",     "label": "台股加權",        "note": "台灣加權指數 TAIEX"},
    {"sym": "^TWOII",    "label": "櫃買指數",        "note": "台灣櫃買 OTC/TPEx"},
    {"sym": "^GSPC",     "label": "S&P 500",        "note": "標普500指數"},
    {"sym": "^IXIC",     "label": "Nasdaq",         "note": "那斯達克綜合"},
    {"sym": "^SOX",      "label": "SOX 半導體",      "note": "費城半導體指數"},
    {"sym": "^VIX",      "label": "VIX 波動率",      "note": "標普500波動率", "yield_like": True, "unit": "pt"},
    {"sym": "^TNX",      "label": "10Y 公債殖利率",  "note": "美國10年期", "yield_like": True, "unit": "bps"},
    {"sym": "UTWO",      "label": "2Y 公債(UTWO)",  "note": "2年期公債ETF代理"},
    {"sym": "GC=F",      "label": "黃金",           "note": "黃金期貨"},
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

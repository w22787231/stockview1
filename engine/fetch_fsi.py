# -*- coding: utf-8 -*-
"""OFR 金融壓力指數(Financial Stress Index)抓取 + 純計算 → 供 export_fsi.py 落盤。
來源:美國財政部 OFR 官網 CSV(免 key、每日、2000~)。
CSV 欄位:Date, OFR FSI, Credit, Equity valuation, Safe assets, Funding, Volatility,
          United States, Other advanced economies, Emerging markets。
產出:FSI + 20MA + 50MA + S&P500 疊圖序列 + 5 類/3 地區「最新」拆解。
OFR FSI 已標準化(0=正常,正=壓力高於常態),不需再算 z。"""
import urllib.request, io, csv

OFR_URL = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
KEEP = 10000  # 落盤保留(OFR 全史 ~6700 點/2000 至今,夠 10年/全部 窗;tail 取最近 N)
WINDOWS = ["1m", "3m", "6m", "1y", "3y", "5y", "10y", "max"]
CAT_MAP = [("Credit", "信用"), ("Equity valuation", "股票評價"), ("Safe assets", "安全資產"),
           ("Funding", "資金面"), ("Volatility", "波動")]
REG_MAP = [("United States", "美國"), ("Other advanced economies", "其他成熟"),
           ("Emerging markets", "新興")]
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
       "Accept-Language": "en-US"}


def fetch_ofr(url=OFR_URL):
    """抓 OFR FSI CSV → list[dict]({date, fsi, <各分量英文欄>}),依日期升冪。"""
    req = urllib.request.Request(url, headers=_UA)
    txt = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    return parse_ofr(txt)


def parse_ofr(txt):
    """純解析(供測試):CSV 文字 → list[dict]。"""
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows:
        return []
    hdr = rows[0]
    idx = {h.strip(): i for i, h in enumerate(hdr)}
    if "OFR FSI" not in idx or "Date" not in idx:
        return []
    out = []
    for r in rows[1:]:
        if len(r) < len(hdr):
            continue
        v = r[idx["OFR FSI"]].strip()
        if v in ("", "."):
            continue
        try:
            fsi = float(v)
        except ValueError:
            continue
        rec = {"date": r[idx["Date"]].strip(), "fsi": fsi}
        for en, _zh in CAT_MAP + REG_MAP:
            j = idx.get(en, -1)
            try:
                rec[en] = float(r[j]) if j >= 0 and r[j].strip() not in ("", ".") else None
            except (ValueError, IndexError):
                rec[en] = None
        out.append(rec)
    out.sort(key=lambda x: x["date"])
    return out


def moving_avg(arr, w):
    """簡單移動平均;前 w-1 點為 None。"""
    out = []
    for i in range(len(arr)):
        if i + 1 < w:
            out.append(None)
        else:
            seg = arr[i + 1 - w:i + 1]
            out.append(round(sum(seg) / w, 4))
    return out


def align_sp500(dates, sp_map):
    """把 {date:close} 對齊到 FSI 的 dates,缺日 forward-fill。"""
    out = []
    last = None
    for d in dates:
        if d in sp_map and sp_map[d] is not None:
            last = sp_map[d]
        out.append(last)
    return out


def fetch_sp500_map(start):
    """yfinance 抓 ^GSPC 日收盤 → {date_iso: close}。失敗回 {}。"""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        df = yf.download("^GSPC", start=start, auto_adjust=True, progress=False, threads=False)
        close = df["Close"]
        if hasattr(close, "columns"):   # MultiIndex/DataFrame → 取首欄
            close = close.iloc[:, 0]
        m = {}
        for ts, val in close.items():
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            if fv == fv:   # 非 NaN
                m[ts.date().isoformat()] = round(fv, 2)
        return m
    except Exception as e:
        print("[fsi] ^GSPC 抓取失敗:", e)
        return {}


def build_fsi_json(records, sp_map, today, keep=KEEP):
    """純計算:OFR records + S&P500 map → fsi.json dict(不連網、不寫檔,供測試)。"""
    dates = [r["date"] for r in records]
    fsi = [r["fsi"] for r in records]
    ma20 = moving_avg(fsi, 20)
    ma50 = moving_avg(fsi, 50)
    ma60 = moving_avg(fsi, 60)
    sp500 = align_sp500(dates, sp_map)

    def tail(a):
        return a[-keep:]

    last = records[-1]
    cats = [{"key": zh, "val": last.get(en)} for en, zh in CAT_MAP]
    regs = [{"key": zh, "val": last.get(en)} for en, zh in REG_MAP]
    return {
        "generated_at": today + "T00:00:00Z",
        "as_of": last["date"],
        "default_window": "5y",
        "windows": WINDOWS,
        "current": last["fsi"],
        "ma20_last": ma20[-1],
        "ma50_last": ma50[-1],
        "ma60_last": ma60[-1],
        "breakdown": {"categories": cats, "regions": regs},
        "series": {
            "dates": tail(dates),
            "fsi": tail(fsi),
            "ma20": tail(ma20),
            "ma50": tail(ma50),
            "ma60": tail(ma60),
            "sp500": tail(sp500),
        },
    }


def build_live(today):
    """抓 OFR + ^GSPC → fsi.json dict。供 export_fsi 呼叫。"""
    records = fetch_ofr()
    if not records:
        return None
    sp_map = fetch_sp500_map(records[0]["date"])
    return build_fsi_json(records, sp_map, today)


if __name__ == "__main__":
    import datetime
    j = build_live(datetime.date.today().isoformat())
    if not j:
        print("抓取失敗")
    else:
        s = j["series"]
        print("as_of", j["as_of"], "current", j["current"], "ma20", j["ma20_last"], "ma50", j["ma50_last"])
        print("series 點數", len(s["dates"]), "末日", s["dates"][-1], "末 sp500", s["sp500"][-1])
        print("5 類:", [(c["key"], c["val"]) for c in j["breakdown"]["categories"]])
        print("3 地區:", [(r["key"], r["val"]) for r in j["breakdown"]["regions"]])

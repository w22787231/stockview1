# -*- coding: utf-8 -*-
"""美國國債收益率曲線(各天期時間序列)→ data/yieldcurve.json。
- 10 個恆定到期名目公債殖利率(FRED DGS3MO…DGS30),各天期一條時間序列線。
- 子圖:2s10s 利差 = 10Y − 2Y(<0 倒掛,經典衰退領先訊號)。
- 另抓 Fed Funds 有效利率(DFF),供總體市場頁比較 Fed Funds vs 2Y/10Y。
有 FRED_API_KEY 走官方 API(雲端不被擋),否則退 fredgraph(本機/無金鑰)。
抓取全失敗 → 不覆寫(沿用線上 last-good,與 FSI/PI/TIPS 一致)。
用法:cd engine && FRED_API_KEY=xxx python export_yieldcurve.py"""
import os, io, json, datetime
import urllib.request
import urllib.parse
import numpy as np, pandas as pd
import fetch_pi as P   # 重用 fetch_fred

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "yieldcurve.json")

START = "2006-01-01"     # 20Y(2006 復名)/30Y(2006 復發)後,10 天期才同時連續
KEEP = 5200              # ~2006 至今 ~5000 交易日,供「全部」視窗

# (key, 顯示label, FRED series);常用 benchmark 天期,由短到長上色。
# 2s10s 利差子圖用 2Y、10Y。如需增減天期在此改即可。
MATS = [
    ("3m",  "3M",  "DGS3MO"),
    ("2y",  "2Y",  "DGS2"),
    ("5y",  "5Y",  "DGS5"),
    ("10y", "10Y", "DGS10"),
    ("20y", "20Y", "DGS20"),
    ("30y", "30Y", "DGS30"),
]


def _num(x, n=2):
    try:
        f = float(x)
        return None if (f != f) else round(f, n)   # NaN → None
    except Exception:
        return None


def fetch_dgs(series_id):
    """抓單一 DGS 殖利率(%)。先官方 API,失敗退 fredgraph CSV。回 pandas.Series 或 None。"""
    s = P.fetch_fred(series_id, START)
    if s is not None and len(s.dropna()):
        return s
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={START}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(txt))
        df.columns = [c.strip().upper() for c in df.columns]
        dcol = "DATE" if "DATE" in df.columns else df.columns[0]
        vcol = series_id.upper() if series_id.upper() in df.columns else df.columns[-1]
        val = pd.to_numeric(df[vcol].replace(".", np.nan), errors="coerce")
        out = pd.Series(val.values, index=pd.DatetimeIndex(pd.to_datetime(df[dcol])), dtype=float)
        return out.sort_index()
    except Exception as e:
        print(f"[yc] fredgraph 後備失敗 {series_id}: {e}")
        return None


def fetch_nyfed_effr(start=START):
    """抓 New York Fed EFFR(有效聯邦基金利率)作為 DFF 備援。回 pandas.Series 或 None。"""
    end = datetime.date.today().strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "startDate": start,
        "endDate": end,
        "type": "rate",
    })
    url = f"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            obj = json.loads(r.read().decode("utf-8"))
        rows = obj.get("refRates") or []
        dates, vals = [], []
        for row in rows:
            d = row.get("effectiveDate")
            v = row.get("percentRate")
            if d is None or v is None:
                continue
            dates.append(pd.Timestamp(d))
            vals.append(float(v))
        if not dates:
            return None
        return pd.Series(vals, index=pd.DatetimeIndex(dates), dtype=float).sort_index()
    except Exception as e:
        print(f"[yc] New York Fed EFFR 後備失敗: {e}")
        return None


def build_live():
    """抓 DGS + DFF → yieldcurve.json dict。2Y/10Y(算利差骨幹)缺 → None。"""
    cols = {}
    for key, _lab, sid in MATS:
        s = fetch_dgs(sid)
        if s is not None:
            cols[key] = s
    fed_funds = fetch_dgs("DFF")
    if fed_funds is None:
        fed_funds = fetch_nyfed_effr()
    if fed_funds is not None:
        cols["fed_funds"] = fed_funds

    if "2y" not in cols or "10y" not in cols:
        print("[yc] 關鍵來源缺失(需 2Y 與 10Y),放棄本次")
        return None

    df = pd.DataFrame(cols).sort_index()
    df = df.dropna(subset=["2y", "10y"])          # 只留 2Y/10Y 皆有的交易日(骨幹)
    df = df[df.index >= pd.Timestamp(START)]
    if len(df) < 30:
        print("[yc] 對齊後資料點不足,放棄本次")
        return None
    df = df.tail(KEEP)

    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    yields = {}
    for key, _lab, _sid in MATS:
        if key in df.columns:
            yields[key] = [_num(v, 2) for v in df[key].values]
    spread = [(_num(a - b, 2) if (a == a and b == b) else None)
              for a, b in zip(df["10y"].values, df["2y"].values)]
    fed_funds_series = ([_num(v, 2) for v in df["fed_funds"].values]
                        if "fed_funds" in df.columns else [])

    # 最新讀數(各天期最後非空)
    def last_of(key):
        if key not in df.columns:
            return None
        arr = yields[key]
        return next((v for v in reversed(arr) if v is not None), None)

    latest = {k: last_of(k) for k, _l, _s in MATS}
    latest["fed_funds"] = (next((v for v in reversed(fed_funds_series) if v is not None), None)
                           if fed_funds_series else None)
    spread_last = next((v for v in reversed(spread) if v is not None), None)

    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "FRED 恆定到期名目公債殖利率 (DGS3MO…DGS30)；Fed Funds 有效利率 (DFF)",
        "maturities": [{"key": k, "label": lab} for k, lab, _s in MATS if k in df.columns],
        "latest": latest,
        "spread_last": spread_last,          # 10Y − 2Y(<0 倒掛)
        "windows": ["3m", "6m", "1y", "3y", "5y", "10y", "max"],
        "default_window": "5y",
        "series": {
            "dates": dates,
            "yields": yields,
            "spread_2s10s": spread,
            "fed_funds": fed_funds_series,
        },
    }


def main():
    print("=== 抓取 美國國債收益率曲線 (DGS3MO…DGS30) ===", flush=True)
    j = None
    try:
        j = build_live()
    except Exception as e:
        print("[yc] 抓取失敗:", e)
    # 驗證:必須是 dict 且 series.yields.10y 非空,才落盤(否則沿用線上)
    if not (isinstance(j, dict) and ((j.get("series") or {}).get("yields") or {}).get("10y")):
        print("[!] 收益率曲線抓取失敗或資料不足 → 不覆寫 yieldcurve.json,保留上次資料")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ yieldcurve.json 已更新:as_of %s FedFunds=%s%% 10Y=%s%% 2Y=%s%% 2s10s=%s,序列 %d 點,%d 天期"
          % (j["as_of"], j["latest"].get("fed_funds"), j["latest"].get("10y"),
             j["latest"].get("2y"), j["spread_last"], len(s["dates"]),
             len(j["maturities"])))


if __name__ == "__main__":
    main()

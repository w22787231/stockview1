# -*- coding: utf-8 -*-
"""TIPS 實質利率 × S&P500 → data/tips.json。
- 主線：10Y TIPS 實質殖利率(FRED DFII10，單位 %)＋ S&P500(^GSPC)。
- 子圖：20 日滾動相關性 = 「TIPS 殖利率每日變動」vs「S&P500 每日報酬」的皮爾森相關(-1~+1)。
  經濟意義：實質利率一動、股市怎麼反應。通常為負(利率升→股市壓)。
抓取全失敗 → 不覆寫(沿用線上 last-good，擋 Cloudflare HTML fallback)。
用法:cd engine && FRED_API_KEY=xxx python export_tips.py"""
import os, io, json, datetime
import urllib.request
import numpy as np, pandas as pd
import fetch_pi as P   # 重用 fetch_fred / fetch_yf_close

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tips.json")

START = "2012-01-01"     # 涵蓋 5y 視窗(1260 交易日)有餘
KEEP = 1400              # json 只留最近 N 點(5y=1260 + 相關暖身)
CORR_WIN = 20            # 20 日滾動相關


def _num(x, n):
    try:
        f = float(x)
        return None if (f != f) else round(f, n)   # NaN → None
    except Exception:
        return None


def fetch_dfii10():
    """10Y TIPS 實質殖利率(%)。有 FRED_API_KEY 走官方 API(雲端不被擋)，
    否則退回 fredgraph CSV(本機/無金鑰;CI 可能被 Cloudflare 擋)。回 pandas.Series 或 None。"""
    s = P.fetch_fred("DFII10", START)
    if s is not None and len(s.dropna()):
        return s
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd={START}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(txt))
        df.columns = [c.strip().upper() for c in df.columns]
        dcol = "DATE" if "DATE" in df.columns else df.columns[0]
        vcol = "DFII10" if "DFII10" in df.columns else df.columns[-1]
        val = pd.to_numeric(df[vcol].replace(".", np.nan), errors="coerce")
        out = pd.Series(val.values, index=pd.DatetimeIndex(pd.to_datetime(df[dcol])), dtype=float)
        return out.sort_index()
    except Exception as e:
        print(f"[tips] fredgraph 後備失敗: {e}")
        return None


def build_live():
    """抓 DFII10 + ^GSPC → tips.json dict。任一關鍵源缺 → None。"""
    tips = fetch_dfii10()                                 # 10Y TIPS 實質殖利率(%)
    yfc  = P.fetch_yf_close(["^GSPC"], START)
    spx  = P._col(yfc, "^GSPC")
    if tips is None or spx is None:
        print("[tips] 關鍵來源缺失(DFII10 或 ^GSPC)，放棄本次")
        return None

    df = pd.DataFrame({"tips": tips, "sp500": spx}).sort_index()
    df = df.dropna(subset=["tips", "sp500"])             # 只留兩者皆有的交易日
    if len(df) < CORR_WIN + 5:
        print("[tips] 對齊後資料點不足，放棄本次")
        return None

    tips_chg = df["tips"].diff()                          # 殖利率日變動(百分點)
    spx_ret  = df["sp500"].pct_change()                  # S&P500 日報酬
    corr20   = tips_chg.rolling(CORR_WIN).corr(spx_ret)  # 20 日滾動相關

    df = df.tail(KEEP); corr20 = corr20.reindex(df.index)
    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    tips_s  = [_num(v, 3) for v in df["tips"].values]
    sp500_s = [_num(v, 2) for v in df["sp500"].values]
    corr_s  = [_num(v, 3) for v in corr20.values]

    # 當前讀數卡：最新 TIPS 水準、與前一交易日差(bps)、最新 20 日相關
    tips_last = tips_s[-1]
    prev = next((v for v in reversed(tips_s[:-1]) if v is not None), None)
    tips_diff_bps = _num((tips_last - prev) * 100.0, 1) if (tips_last is not None and prev is not None) else None
    corr_last = next((v for v in reversed(corr_s) if v is not None), None)

    return {
        "as_of": dates[-1],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "FRED DFII10 (10Y TIPS 實質殖利率) + Yahoo Finance ^GSPC",
        "tips_last": tips_last,
        "tips_diff_bps": tips_diff_bps,
        "corr20_last": corr_last,
        "corr_win": CORR_WIN,
        "windows": ["3m", "6m", "1y", "3y", "5y"],
        "default_window": "1y",
        "series": {"dates": dates, "tips": tips_s, "sp500": sp500_s, "corr20": corr_s},
    }


def main():
    print("=== 抓取 TIPS 實質利率 × S&P500 ===", flush=True)
    j = None
    try:
        j = build_live()
    except Exception as e:
        print("[tips] 抓取失敗:", e)
    # 驗證：必須是 dict 且 series.tips 非空，才落盤(否則沿用線上)
    if not (isinstance(j, dict) and (j.get("series") or {}).get("tips")):
        print("[!] TIPS 抓取失敗或資料不足 → 不覆寫 tips.json，保留上次資料")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ tips.json 已更新:as_of %s TIPS=%s%%(日差 %s bps) 20日相關=%s，序列 %d 點"
          % (j["as_of"], j["tips_last"], j["tips_diff_bps"], j["corr20_last"], len(s["dates"])))


if __name__ == "__main__":
    main()

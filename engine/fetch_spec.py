# -*- coding: utf-8 -*-
"""投機交易指標 + 投機溫度:抓取(fetch/assemble)+ 純計算(build_spec_json,重用 fetch_pi)。"""
import io, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fetch_pi import rolling_z, weighted_pi, _percentile, fetch_yf_close, WINDOWS

SOURCE_KEYS = ["投機成長","高beta偏好","槓桿ETF熱度","風險偏好","COT槓桿基金","融資GDP"]

# ── Task 2: 抓取層 ────────────────────────────────────────────────────────────

def cot_series_from_sentiment(sent):
    """從 sentiment dict 的 cot_spx.dates + lev_net 組 pd.Series；缺欄/長度不符回 None。"""
    c = (sent or {}).get("cot_spx") or {}
    dates, lev = c.get("dates"), c.get("lev_net")
    if not dates or not lev or len(dates) != len(lev):
        return None
    return pd.Series([float(x) for x in lev], index=pd.to_datetime(dates)).sort_index()

_MON = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
        "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

def margin_series_from_sentiment(sent):
    """從 sentiment dict 的 leverage.months + ratio_series 組 pd.Series；月字串如 "Jun-25" → 2025-06-01；缺欄/長度不符回 None。"""
    L = (sent or {}).get("leverage") or {}
    months, ratios = L.get("months"), L.get("ratio_series")
    if not months or not ratios or len(months) != len(ratios):
        return None
    idx = []
    for m in months:          # "Jun-25" → 2025-06-01
        mon, yr = m.split("-")
        idx.append(pd.Timestamp(2000 + int(yr), _MON[mon[:3]], 1))
    return pd.Series([float(x) for x in ratios], index=pd.DatetimeIndex(idx)).sort_index()

def _read_sentiment():
    """先讀本機 ../data/sentiment.json，無則抓線上。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sentiment.json")
    try:
        if os.path.exists(p):
            return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        pass
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            "https://stockview1.pages.dev/data/sentiment.json",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
        return json.loads(b.decode("utf-8", "ignore"))
    except Exception as e:
        print("[spec] 讀 sentiment.json 失敗:", e)
        return {}

def fetch_reddit_context():
    """抓 meiguhuli 旁註；失敗回 {}。"""
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            "https://cache.meiguhuli.com",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
        rows = (json.loads(b.decode("utf-8", "ignore")).get("results")) or []
        total = sum(int(r.get("mentions") or 0) for r in rows)
        top = [r.get("ticker") for r in rows[:5] if r.get("ticker")]
        return {"reddit_mentions": total, "reddit_top": top}
    except Exception as e:
        print("[spec] meiguhuli 失敗:", e)
        return {}

def _spark(s, n=26):
    """半年週頻 sparkline（最多 26 週）。"""
    w = s.dropna().resample("W-FRI").last().dropna().tail(n)
    return [round(float(v), 4) for v in w.values]

def assemble_spec_raw(start):
    """組裝 (sources, cards, context, sp500)；yfinance 整批失敗回 None；任何 fetch 例外安全處理。"""
    yfc = fetch_yf_close(["ARKK", "SPY", "SPHB", "SPLV", "TQQQ", "SOXL", "BTC-USD"], start)
    if yfc is None:
        print("[spec] yfinance 全失敗")
        return None
    def col(n):
        return yfc[n] if (n in yfc.columns) else None
    arkk, spy, sphb, splv, tqqq, soxl, btc = (
        col(x) for x in ["ARKK", "SPY", "SPHB", "SPLV", "TQQQ", "SOXL", "BTC-USD"])
    # 成交量:另抓(fetch_yf_close 只回 Close)
    try:
        import yfinance as yf
        vol = yf.download(["TQQQ", "SOXL"], start=start, progress=False)["Volume"]
    except Exception:
        vol = None
    lev_vol = None
    if vol is not None:
        v = vol.fillna(0)
        lev_vol = (v.get("TQQQ", 0) + v.get("SOXL", 0)) if hasattr(v, "get") else None
        if lev_vol is not None and hasattr(lev_vol, "replace"):
            lev_vol = lev_vol.replace(0, np.nan)
    def ratio(a, b):
        return (a / b) if (a is not None and b is not None) else None
    sources = {
        "投機成長":   ratio(arkk, spy),
        "高beta偏好": ratio(sphb, splv),
        "槓桿ETF熱度": lev_vol,
        "風險偏好":   btc,
    }
    sent = _read_sentiment()
    cot = cot_series_from_sentiment(sent)
    margin = margin_series_from_sentiment(sent)
    if cot is not None:
        sources["COT槓桿基金"] = cot
    if margin is not None:
        sources["融資GDP"] = margin
    sources = {k: v for k, v in sources.items() if v is not None}
    def card(key, sub, s, note):
        sd = s.dropna() if s is not None else None
        if sd is None or not len(sd):
            return None
        cur = float(sd.iloc[-1])
        prev = float(sd.iloc[-2]) if len(sd) > 1 else cur
        chg = (cur - prev) / prev * 100 if prev else 0.0
        return {"key": key, "sub": sub, "value": round(cur, 4), "chg_pct": round(chg, 2),
                "spark": _spark(s), "note": note}
    cards = [c for c in [
        card("投機成長",   "ARKK/SPY",   sources.get("投機成長"),   "比值升=偏好投機成長"),
        card("高beta偏好", "SPHB/SPLV",  sources.get("高beta偏好"), "升=偏好高beta(風險)"),
        card("槓桿ETF熱度","TQQQ+SOXL量",sources.get("槓桿ETF熱度"),"量升=散戶追漲投機"),
        card("風險偏好",   "BTC-USD",    sources.get("風險偏好"),   "升=風險偏好/投機升溫"),
    ] if c]
    context = fetch_reddit_context()
    L = (sent or {}).get("leverage") or {}
    if L.get("ratio_pct") is not None:
        context["margin_gdp_pct"] = L.get("ratio_pct")
    sp500 = yfc["SPY"] if "SPY" in yfc.columns else None
    return sources, cards, context, sp500
PCT_LOOKBACK = 1260  # 5 年(溫度=composite z 的近 5 年百分位)
DEFAULT_WINDOW = "5y"

def _win_min_periods(wlen):
    # 短窗用半窗(反應快);長窗上限 252(1年),讓歷史較短的源(如融資GDP ~2-3年)也能進合成
    return max(min(wlen // 2, 252), 10)

def _safe_last(col, last):
    try:
        v = col.loc[last]
    except Exception:
        return None
    return None if pd.isna(v) else round(float(v), 2)

def build_spec_json(sources, cards, context, weights, today_iso, sp500=None):
    present = [k for k in SOURCE_KEYS if k in sources and sources[k] is not None and sources[k].notna().any()]
    win_keys = list(WINDOWS.keys())
    if not present:
        return {"generated_at": today_iso, "weights": weights, "indicators": cards or [],
                "temperature": {"default_window": DEFAULT_WINDOW, "windows": win_keys,
                                "series": {"dates": [], "sp500": [], "z_by_window": {w: [] for w in win_keys}},
                                "by_window": {w: {"current": None, "components": {k: None for k in SOURCE_KEYS}} for w in win_keys}},
                "context": context or {}}
    idx = pd.bdate_range(min(sources[k].index.min() for k in present),
                         max(sources[k].index.max() for k in present))
    src_aligned = {k: sources[k].reindex(idx).ffill() for k in present}
    cutoff = idx.max() - pd.Timedelta(days=365*10)
    wk_idx = pd.Series(1, index=idx).resample("W-FRI").last().index
    wk_idx = wk_idx[wk_idx >= cutoff]
    def _sample(s):
        return [None if pd.isna(v) else round(float(v), 4)
                for v in s.reindex(idx).ffill().reindex(wk_idx, method="ffill").values]
    z_by_window, by_window = {}, {}
    for w, wlen in WINDOWS.items():
        mp = _win_min_periods(wlen)
        z_df = pd.DataFrame({k: rolling_z(src_aligned[k], wlen, mp) for k in present})
        comp = weighted_pi(z_df, {k: weights.get(k, 1.0) for k in present})
        z_by_window[w] = _sample(comp)
        valid = comp.dropna()
        last = valid.index[-1] if len(valid) else idx[-1]
        comps = {k: (_safe_last(z_df[k], last) if k in z_df.columns else None) for k in SOURCE_KEYS}
        temp = _percentile(comp, PCT_LOOKBACK)
        by_window[w] = {"current": (None if temp is None else int(temp)), "components": comps}
    if sp500 is not None:
        sp500_series = [None if pd.isna(v) else round(float(v), 2)
                        for v in sp500.reindex(idx).ffill().reindex(wk_idx, method="ffill").values]
    else:
        sp500_series = []
    return {"generated_at": today_iso, "weights": weights, "indicators": cards or [],
            "temperature": {"default_window": DEFAULT_WINDOW, "windows": win_keys,
                            "series": {"dates": [d.strftime("%Y-%m-%d") for d in wk_idx],
                                       "sp500": sp500_series, "z_by_window": z_by_window},
                            "by_window": by_window},
            "context": context or {}}

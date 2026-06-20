# -*- coding: utf-8 -*-
"""流動性壓力指數 PI:抓取(fetch_*)+ 純計算(rolling_z/weighted_pi/build_pi_json)。"""
import numpy as np, pandas as pd

FACTOR_KEYS = ["①短端利率","②久期供給","③官方流動性","④一級擁擠","⑤波動率","⑥油價"]
WINDOWS = {"1m":21,"3m":63,"6m":126,"1y":252,"3y":756,"5y":1260}

def rolling_z(s, window, min_periods):
    m = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std()
    return (s - m) / sd

def weighted_pi(z_df, weights):
    cols = list(z_df.columns)
    w = np.array([weights[c] for c in cols], dtype=float)
    vals = z_df.to_numpy(dtype=float)
    mask = ~np.isnan(vals)
    wsum = (mask * w).sum(axis=1)
    contrib = np.where(mask, vals * w, 0.0).sum(axis=1)
    out = np.where(wsum > 0, contrib / np.where(wsum > 0, wsum, 1.0), np.nan)
    return pd.Series(out, index=z_df.index)

def _percentile(series, lookback=252*4):
    s = series.dropna()
    if len(s) < 30: return None
    tail = s.tail(lookback)
    cur = tail.iloc[-1]
    return round(float((tail < cur).sum()) / max(len(tail)-1, 1) * 100, 0)

def build_pi_json(factors_raw, signs, sp500, weights, today_iso):
    # 處理 ⑤波動率 可能為 tuple(VIX, MOVE) 的情況
    vix_move = factors_raw.get("⑤波動率")
    is_blend = isinstance(vix_move, tuple)

    # 收集所有 Series 以計算日期範圍
    all_series = [v for k, v in factors_raw.items() if not isinstance(v, tuple)]
    if is_blend:
        all_series += [vix_move[0], vix_move[1]]
    all_series.append(sp500)

    # 對齊到工作日 + 前值填補
    idx = pd.bdate_range(
        min(s.index.min() for s in all_series),
        max(s.index.max() for s in all_series)
    )

    # 非 ⑤ 因子的 DataFrame
    base_keys = [k for k in FACTOR_KEYS if k != "⑤波動率"] if is_blend else FACTOR_KEYS
    df = pd.DataFrame({k: factors_raw[k].reindex(idx).ffill() for k in base_keys})

    if is_blend:
        vix_s = vix_move[0].reindex(idx).ffill()
        move_s = vix_move[1].reindex(idx).ffill()

    spx = sp500.reindex(idx).ffill()

    # 各窗:對每因子 z-score、定向,合成 PI
    pi_by_window, current = {}, {}
    for wkey, wlen in WINDOWS.items():
        mp = max(wlen // 2, 10)
        if is_blend:
            zcols = {k: rolling_z(df[k], wlen, mp) * signs[k] for k in base_keys}
            zcols["⑤波動率"] = ((rolling_z(vix_s, wlen, mp) + rolling_z(move_s, wlen, mp)) / 2.0) * signs["⑤波動率"]
            z = pd.DataFrame({k: zcols[k] for k in FACTOR_KEYS})
        else:
            z = pd.DataFrame({k: rolling_z(df[k], wlen, mp) * signs[k] for k in FACTOR_KEYS})

        pi = weighted_pi(z, weights)
        pi_by_window[wkey] = pi

        last = z.dropna(how="all").index[-1] if z.dropna(how="all").shape[0] else z.index[-1]
        comp = {k: (round(float(z[k].loc[last]), 2) if not pd.isna(z[k].loc[last]) else None) for k in FACTOR_KEYS}
        current[wkey] = {
            "pi": (round(float(pi.loc[last]), 2) if not pd.isna(pi.loc[last]) else None),
            "pctile": _percentile(pi),
            "components": comp
        }

    # 週頻取樣,近 10 年
    cutoff = idx.max() - pd.Timedelta(days=365*10)
    wk_idx = pd.Series(1, index=idx).resample("W-FRI").last().index
    wk_idx = wk_idx[wk_idx >= cutoff]

    def sample(s):
        return [None if pd.isna(v) else round(float(v), 4)
                for v in s.reindex(idx).ffill().reindex(wk_idx, method="ffill").values]

    out = {
        "generated_at": today_iso,
        "weights": weights,
        "default_window": "5y",
        "windows": list(WINDOWS.keys()),
        "series": {
            "dates": [d.strftime("%Y-%m-%d") for d in wk_idx],
            "sp500": sample(spx),
            "pi_by_window": {w: sample(pi_by_window[w]) for w in WINDOWS},
        },
        "current_by_window": current,
        "factors_meta": [
            {"key":"①短端利率","source":"FRED DGS2","dir":"+","note":"利率高=收緊=壓力"},
            {"key":"②久期供給","source":"FRED DGS10","dir":"+","note":"長端高=發債抽水=壓力"},
            {"key":"③官方流動性","source":"FRED WALCL-TGA-RRP","dir":"-","note":"淨流動性高=壓力低"},
            {"key":"④一級擁擠","source":"FRED BAMLH0A0HYM2","dir":"+","note":"HY利差走闊=壓力"},
            {"key":"⑤波動率","source":"yfinance ^VIX+^MOVE","dir":"+","note":"波動放大=壓力"},
            {"key":"⑥油價","source":"yfinance CL=F","dir":"+","note":"油價高=通脹=壓力"},
        ],
    }
    return out

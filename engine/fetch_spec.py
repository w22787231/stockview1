# -*- coding: utf-8 -*-
"""投機交易指標 + 投機溫度:抓取(fetch/assemble)+ 純計算(build_spec_json,重用 fetch_pi)。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fetch_pi import rolling_z, weighted_pi, _percentile  # noqa: F401(rolling_z/weighted_pi used below)

SOURCE_KEYS = ["投機成長","高beta偏好","槓桿ETF熱度","風險偏好","COT槓桿基金","融資GDP"]
Z_WIN = 756          # 3 年
PCT_LOOKBACK = 1260  # 5 年

def build_spec_json(sources, cards, context, weights, today_iso):
    present = [k for k in SOURCE_KEYS if k in sources and sources[k] is not None and sources[k].notna().any()]
    if not present:
        return {"generated_at": today_iso, "weights": weights, "indicators": cards or [],
                "temperature": {"current": None, "series": {"dates": [], "z": []},
                                "components": {k: None for k in SOURCE_KEYS}}, "context": context or {}}
    idx = pd.bdate_range(min(sources[k].index.min() for k in present),
                         max(sources[k].index.max() for k in present))
    z_df = pd.DataFrame({k: rolling_z(sources[k].reindex(idx).ffill(), Z_WIN, Z_WIN//2) for k in present})
    comp = weighted_pi(z_df, {k: weights.get(k, 1.0) for k in present})
    valid = comp.dropna()
    last = valid.index[-1] if len(valid) else idx[-1]
    components = {k: (round(float(z_df[k].loc[last]), 2) if (k in z_df and not pd.isna(z_df[k].loc[last])) else None)
                 for k in SOURCE_KEYS}
    cutoff = idx.max() - pd.Timedelta(days=365*10)
    wk_idx = pd.Series(1, index=idx).resample("W-FRI").last().index
    wk_idx = wk_idx[wk_idx >= cutoff]
    z_series = [None if pd.isna(v) else round(float(v), 4)
                for v in comp.reindex(idx).ffill().reindex(wk_idx, method="ffill").values]
    temp = _percentile(comp, PCT_LOOKBACK)  # 0-100 或 None
    return {
        "generated_at": today_iso, "weights": weights,
        "indicators": cards or [],
        "temperature": {
            "current": (None if temp is None else int(temp)),
            "series": {"dates": [d.strftime("%Y-%m-%d") for d in wk_idx], "z": z_series},
            "components": components,
        },
        "context": context or {},
    }

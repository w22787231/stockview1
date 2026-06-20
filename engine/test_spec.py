# -*- coding: utf-8 -*-
# engine/test_spec.py
import numpy as np, pandas as pd
import fetch_spec as S

def test_build_spec_composite_and_temperature():
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    rng = np.arange(len(idx), dtype=float)
    up = pd.Series(rng, index=idx)            # 單調上升 → z 正(越投機)
    sources = {k: up for k in S.SOURCE_KEYS}
    cards = [{"key":"投機成長","sub":"ARKK/SPY","value":0.1,"chg_pct":1.0,"spark":[1,2,3],"note":"x"}]
    context = {"reddit_mentions": 100, "reddit_top": ["NVDA"], "margin_gdp_pct": 4.4}
    weights = {k: 1.0 for k in S.SOURCE_KEYS}
    j = S.build_spec_json(sources, cards, context, weights, "2023-05-01T00:00:00Z")
    assert 0 <= j["temperature"]["current"] <= 100
    # 全源單調上升、+z → composite 末端為正、溫度偏高
    assert j["temperature"]["current"] >= 80
    assert j["temperature"]["components"]["投機成長"] > 0
    assert len(j["temperature"]["series"]["dates"]) == len(j["temperature"]["series"]["z"])
    assert j["indicators"] == cards
    assert j["context"] == context

def test_build_spec_skips_nan_source():
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    rng = np.arange(len(idx), dtype=float)
    up = pd.Series(rng, index=idx)
    sources = {k: up for k in S.SOURCE_KEYS}
    sources["融資GDP"] = pd.Series([np.nan]*len(idx), index=idx)   # 模擬歷史不足
    j = S.build_spec_json(sources, [], {}, {k:1.0 for k in S.SOURCE_KEYS}, "2023-05-01T00:00:00Z")
    assert j["temperature"]["components"]["融資GDP"] is None        # 缺源 → None
    assert j["temperature"]["current"] is not None                  # 其餘 5 源仍算出溫度

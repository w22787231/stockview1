# -*- coding: utf-8 -*-
# engine/test_spec.py
import numpy as np, pandas as pd
import fetch_spec as S

def test_build_spec_composite_and_temperature():
    import numpy as np, pandas as pd
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    # 前 3500 點平緩、最後 500 點明顯抬升 → 末端 z 高、溫度高
    vals = np.concatenate([np.linspace(0,1,3500), np.linspace(1,6,500)])
    base = pd.Series(vals, index=idx)
    sources = {k: base for k in S.SOURCE_KEYS}
    cards=[{"key":"投機成長","sub":"ARKK/SPY","value":0.1,"chg_pct":1.0,"spark":[1,2,3],"note":"x"}]
    context={"reddit_mentions":100,"reddit_top":["NVDA"],"margin_gdp_pct":4.4}
    weights={k:1.0 for k in S.SOURCE_KEYS}
    j=S.build_spec_json(sources, cards, context, weights, "2023-05-01T00:00:00Z")
    assert j["temperature"]["current"] is not None and 0 <= j["temperature"]["current"] <= 100
    assert j["temperature"]["current"] >= 50     # 近段抬升 → 偏熱
    assert j["temperature"]["components"]["投機成長"] > 0
    assert len(j["temperature"]["series"]["dates"]) == len(j["temperature"]["series"]["z"])
    assert j["indicators"]==cards and j["context"]==context

def test_build_spec_short_source_safe():
    import numpy as np, pandas as pd
    idx = pd.date_range("2008-01-01", periods=4000, freq="B"); base=pd.Series(np.arange(len(idx),dtype=float),index=idx)
    sources={k:base for k in S.SOURCE_KEYS}
    sources["風險偏好"]=pd.Series([1.0,2.0,3.0], index=pd.date_range("2008-01-01",periods=3,freq="B"))
    j=S.build_spec_json(sources, [], {}, {k:1.0 for k in S.SOURCE_KEYS}, "2023-05-01T00:00:00Z")
    assert "temperature" in j  # 不丟例外

def test_build_spec_skips_nan_source():
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    rng = np.arange(len(idx), dtype=float)
    up = pd.Series(rng, index=idx)
    sources = {k: up for k in S.SOURCE_KEYS}
    sources["融資GDP"] = pd.Series([np.nan]*len(idx), index=idx)   # 模擬歷史不足
    j = S.build_spec_json(sources, [], {}, {k:1.0 for k in S.SOURCE_KEYS}, "2023-05-01T00:00:00Z")
    assert j["temperature"]["components"]["融資GDP"] is None        # 缺源 → None
    assert j["temperature"]["current"] is not None                  # 其餘 5 源仍算出溫度

# ── Task 2: 純函式 sentiment 解析 ────────────────────────────────────────────

def test_cot_series_from_sentiment():
    sent = {"cot_spx": {"dates": ["2022-02-08","2022-02-15","2022-02-22"], "lev_net": [58542, 30528, 73418]}}
    s = S.cot_series_from_sentiment(sent)
    assert isinstance(s, pd.Series) and len(s) == 3
    assert s.index.is_monotonic_increasing
    assert float(s.iloc[0]) == 58542

def test_margin_series_from_sentiment():
    sent = {"leverage": {"months": ["Jun-25","Jul-25","Aug-25"], "ratio_series": [3.17, 3.22, 3.33]}}
    s = S.margin_series_from_sentiment(sent)
    assert isinstance(s, pd.Series) and len(s) == 3
    assert abs(float(s.iloc[-1]) - 3.33) < 1e-9

def test_cot_margin_missing_safe():
    assert S.cot_series_from_sentiment({}) is None
    assert S.margin_series_from_sentiment({"leverage": {}}) is None

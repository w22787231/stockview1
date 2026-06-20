# -*- coding: utf-8 -*-
# engine/test_pi.py
import numpy as np, pandas as pd
import fetch_pi as P

def test_rolling_z_known_values():
    s = pd.Series([1,2,3,4,5], dtype=float)
    z = P.rolling_z(s, window=5, min_periods=3)
    # 末點:窗=[1..5],mean=3,std(ddof=1)=1.5811,z=(5-3)/1.5811
    assert abs(z.iloc[-1] - (5-3)/np.std([1,2,3,4,5], ddof=1)) < 1e-9
    assert np.isnan(z.iloc[0])  # 不足 min_periods

def test_weighted_pi_ignores_nan_and_weights():
    z = pd.DataFrame({"a":[1.0,2.0],"b":[3.0,np.nan],"c":[ -1.0, 0.0]})
    w = {"a":1.0,"b":1.5,"c":1.0}
    pi = P.weighted_pi(z, w)
    # 第0列:(1*1 + 3*1.5 + -1*1)/(1+1.5+1)=(1+4.5-1)/3.5=4.5/3.5
    assert abs(pi.iloc[0] - (4.5/3.5)) < 1e-9
    # 第1列:b 為 NaN → 只用 a,c:(2*1 + 0*1)/(1+1)=1.0
    assert abs(pi.iloc[1] - 1.0) < 1e-9

def test_build_pi_json_shape_and_direction():
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    rng = np.arange(len(idx), dtype=float)
    factors_raw = {
        "①短端利率": pd.Series(rng, index=idx),
        "②久期供給": pd.Series(rng, index=idx),
        "③官方流動性": pd.Series(rng, index=idx),   # 上升 → 定向後應為負壓力
        "④一級擁擠": pd.Series(rng, index=idx),
        "⑤波動率": pd.Series(rng, index=idx),
        "⑥油價": pd.Series(rng, index=idx),
    }
    signs = {"①短端利率":1,"②久期供給":1,"③官方流動性":-1,"④一級擁擠":1,"⑤波動率":1,"⑥油價":1}
    sp500 = pd.Series(1000+rng, index=idx)
    weights = {"①短端利率":1,"②久期供給":1,"③官方流動性":1.5,"④一級擁擠":1,"⑤波動率":1,"⑥油價":1}
    j = P.build_pi_json(factors_raw, signs, sp500, weights, "2023-05-01T00:00:00Z")
    assert j["default_window"] == "5y"
    assert set(j["windows"]) == {"1m","3m","6m","1y","3y","5y"}
    assert len(j["series"]["dates"]) == len(j["series"]["sp500"])
    for w in j["windows"]:
        assert len(j["series"]["pi_by_window"][w]) == len(j["series"]["dates"])
    # ③定向:單調上升序列,z 為正,定向 −1 → component ③ 應為負
    comp = j["current_by_window"]["5y"]["components"]
    assert comp["③官方流動性"] < 0
    assert comp["①短端利率"] > 0

def test_weighted_pi_all_nan_row_returns_nan():
    z = pd.DataFrame({"a":[np.nan,1.0],"b":[np.nan,3.0]})
    w = {"a":1.0,"b":1.0}
    pi = P.weighted_pi(z, w)
    assert np.isnan(pi.iloc[0])          # 全 NaN 列 → NaN
    assert abs(pi.iloc[1] - 2.0) < 1e-9  # (1+3)/2

def test_build_pi_blends_vix_move_for_factor5():
    idx = pd.date_range("2008-01-01", periods=4000, freq="B")
    rng = np.arange(len(idx), dtype=float)
    base = pd.Series(rng, index=idx)
    factors_raw = {"①短端利率":base,"②久期供給":base,"③官方流動性":base,
                   "④一級擁擠":base,"⑤波動率":(base, base*2),"⑥油價":base}
    signs = {"①短端利率":1,"②久期供給":1,"③官方流動性":-1,"④一級擁擠":1,"⑤波動率":1,"⑥油價":1}
    j = P.build_pi_json(factors_raw, signs, pd.Series(1000+rng,index=idx),
                        {k:(1.5 if k=="③官方流動性" else 1) for k in P.FACTOR_KEYS}, "2023-05-01T00:00:00Z")
    assert j["current_by_window"]["5y"]["components"]["⑤波動率"] is not None

def test_weighted_pi_distinct_values_exact():
    z = pd.DataFrame({"①短端利率":[2.0],"②久期供給":[0.0],"③官方流動性":[-1.0],
                      "④一級擁擠":[1.0],"⑤波動率":[0.5],"⑥油價":[-0.5]})
    w = {"①短端利率":1,"②久期供給":1,"③官方流動性":1.5,"④一級擁擠":1,"⑤波動率":1,"⑥油價":1}
    pi = P.weighted_pi(z, w)
    # (2*1 + 0*1 + -1*1.5 + 1*1 + 0.5*1 + -0.5*1) / (1+1+1.5+1+1+1)
    num = 2 + 0 - 1.5 + 1 + 0.5 - 0.5
    assert abs(pi.iloc[0] - num/6.5) < 1e-9

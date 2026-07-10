# -*- coding: utf-8 -*-
"""export_yieldcurve 純計算測試:monkeypatch fetch_dgs 餵合成殖利率序列,
驗證 2s10s 利差 = 10Y − 2Y、JSON 結構、視窗、最新讀數。不需網路/FRED。"""
import pandas as pd
import export_yieldcurve as Y


def _series(vals, start="2006-01-02"):
    idx = pd.bdate_range(start=start, periods=len(vals))
    return pd.Series(vals, index=idx, dtype=float)


def _fake_fetch(monkeypatch, per_key):
    """per_key: {maturity_key: [values]} → 依 MATS 對映到 series id。"""
    key_by_sid = {sid: key for key, _lab, sid in Y.MATS}

    def fake(sid):
        key = key_by_sid.get(sid)
        vals = per_key.get(key)
        return _series(vals) if vals is not None else None
    monkeypatch.setattr(Y, "fetch_dgs", fake)


def test_spread_and_structure(monkeypatch):
    n = 40
    per = {k: [i * 0.01 + j for i in range(n)]  # 每天期不同水準
           for j, (k, _l, _s) in enumerate(Y.MATS)}
    _fake_fetch(monkeypatch, per)
    j = Y.build_live()
    assert j is not None
    s = j["series"]
    # 結構
    assert set(s["yields"].keys()) == {k for k, _l, _s in Y.MATS}
    assert len(s["dates"]) == n
    assert j["windows"][-1] == "max"
    assert j["default_window"] == "5y"
    assert len(j["maturities"]) == 10
    # 2s10s 利差逐點 = 10y − 2y(四捨五入 2 位)
    y2, y10 = s["yields"]["2y"], s["yields"]["10y"]
    for i in range(n):
        assert s["spread_2s10s"][i] == round(y10[i] - y2[i], 2)
    # 最新讀數 = 各序列最後值
    assert j["latest"]["10y"] == y10[-1]
    assert j["spread_last"] == round(y10[-1] - y2[-1], 2)


def test_missing_backbone_returns_none(monkeypatch):
    # 缺 10Y(骨幹)→ 放棄(回 None,呼叫端不覆寫)
    per = {k: [1.0] * 40 for k, _l, _s in Y.MATS if k != "10y"}
    _fake_fetch(monkeypatch, per)
    assert Y.build_live() is None


def test_inverted_spread_negative(monkeypatch):
    # 2Y 高於 10Y → 利差為負(倒掛)
    per = {k: [1.0] * 40 for k, _l, _s in Y.MATS}
    per["2y"] = [4.9] * 40
    per["10y"] = [4.2] * 40
    _fake_fetch(monkeypatch, per)
    j = Y.build_live()
    assert j["spread_last"] == round(4.2 - 4.9, 2)
    assert j["spread_last"] < 0


if __name__ == "__main__":
    import pytest, sys
    raise SystemExit(pytest.main([__file__, "-v"]))

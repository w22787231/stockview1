# -*- coding: utf-8 -*-
import fetch_0dte as F


def test_compute_pct_basic():
    exps = ["2026-07-06", "2026-07-07", "2026-07-10"]
    vols = {"2026-07-06": 90000, "2026-07-07": 20000, "2026-07-10": 40000}
    r = F.compute_pct(exps, vols)
    assert r["nearest_exp"] == "2026-07-06"
    assert r["nearest_vol"] == 90000
    assert r["total_vol"] == 150000
    assert r["pct"] == 60.0


def test_compute_pct_zero_total():
    assert F.compute_pct(["2026-07-06"], {"2026-07-06": 0}) is None
    assert F.compute_pct(None, None) is None
    assert F.compute_pct([], {}) is None


def test_build_json_first_point():
    r = {"nearest_exp": "2026-07-06", "nearest_vol": 9, "total_vol": 20, "pct": 45.0}
    j = F.build_0dte_json(None, "2026-07-06", r)
    assert j["current_pct"] == 45.0
    assert j["dte"] == 0                      # 到期=當日 → 真 0DTE
    assert j["series"]["dates"] == ["2026-07-06"]
    assert j["series"]["spx_pct"] == [45.0]
    assert j["cboe_official"]["value"] == 59


def test_build_json_appends_and_dedups():
    r1 = {"nearest_exp": "2026-07-06", "nearest_vol": 9, "total_vol": 20, "pct": 45.0}
    j1 = F.build_0dte_json(None, "2026-07-06", r1)
    r2 = {"nearest_exp": "2026-07-07", "nearest_vol": 5, "total_vol": 20, "pct": 25.0}
    j2 = F.build_0dte_json(j1, "2026-07-07", r2)
    assert j2["series"]["dates"] == ["2026-07-06", "2026-07-07"]
    assert j2["series"]["spx_pct"] == [45.0, 25.0]
    # 同日重跑 → 覆蓋不重複
    r2b = {"nearest_exp": "2026-07-07", "nearest_vol": 6, "total_vol": 20, "pct": 30.0}
    j3 = F.build_0dte_json(j2, "2026-07-07", r2b)
    assert j3["series"]["dates"] == ["2026-07-06", "2026-07-07"]
    assert j3["series"]["spx_pct"] == [45.0, 30.0]


def test_dte_next_day_flag_appends():
    # 收盤後今日已到期 → 近端變次日,dte=1(仍算真近端 → 進序列)
    r = {"nearest_exp": "2026-07-07", "nearest_vol": 3, "total_vol": 20, "pct": 15.0}
    j = F.build_0dte_json(None, "2026-07-06", r)
    assert j["dte"] == 1
    assert j["series"]["spx_pct"] == [15.0]


def test_weekend_dte2_not_appended():
    # 週末/假日:近端到期 >=2 天 → 只更新當前值,不進趨勢序列(避免污染)
    r = {"nearest_exp": "2026-07-06", "nearest_vol": 2, "total_vol": 20, "pct": 10.0}
    j = F.build_0dte_json(None, "2026-07-04", r)   # 07-04 週六,近端 07-06(週一)dte=2
    assert j["dte"] == 2
    assert j["current_pct"] == 10.0                # 當前值仍更新
    assert j["series"]["dates"] == []              # 但不進趨勢序列

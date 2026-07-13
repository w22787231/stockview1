# -*- coding: utf-8 -*-
import safe_haven as SH


def test_value_at_exact_match():
    assert SH.value_at("2026-07-09", ["2026-07-07", "2026-07-08", "2026-07-09"], [6180.0, 6230.0, 6280.0]) == 6280.0


def test_value_at_nearest_prior():
    assert SH.value_at("2026-07-11", ["2026-07-07", "2026-07-08", "2026-07-09"], [6180.0, 6230.0, 6280.0]) == 6280.0


def test_value_at_before_series_returns_none():
    assert SH.value_at("2026-07-01", ["2026-07-07"], [6180.0]) is None


def test_to_ymd_converts_ms_epoch_utc():
    # 2026-07-09 00:00:00 UTC
    assert SH.to_ymd(1783555200000) == "2026-07-09"


def test_build_series_aligns_sp500_and_rounds_y():
    raw = [
        {"x": 1783382400000, "y": 3.611263162},   # 2026-07-07
        {"x": 1783468800000, "y": 3.038284856},   # 2026-07-08
        {"x": None, "y": 5.0},                    # 缺 x → 跳過
        {"x": 1783555200000, "y": None},          # 缺 y → 跳過
    ]
    gspc_dates = ["2026-07-06", "2026-07-07", "2026-07-08"]
    gspc_close = [6180.0, 6230.0, 6280.0]
    dates, y, sp500 = SH.build_series(raw, gspc_dates, gspc_close)
    assert dates == ["2026-07-07", "2026-07-08"]
    assert y == [3.61, 3.04]
    assert sp500 == [6230.0, 6280.0]


def test_build_series_dedups_same_day_keeping_last():
    # CNN 有時同一天出現兩筆(當日收盤快照 + 當日尾盤即時值),日期截斷後撞同一天 → 只留最後一筆
    raw = [
        {"x": 1783641600000, "y": 3.0},   # 2026-07-10 00:00:00
        {"x": 1783713599000, "y": 3.5},   # 2026-07-10 19:59:59(同日,較新)
    ]
    gspc_dates = ["2026-07-10"]
    gspc_close = [7575.39]
    dates, y, sp500 = SH.build_series(raw, gspc_dates, gspc_close)
    assert dates == ["2026-07-10"]
    assert y == [3.5]
    assert sp500 == [7575.39]


def test_build_series_sp500_none_when_before_gspc_history():
    raw = [{"x": 1783382400000, "y": 3.6}]   # 2026-07-07
    gspc_dates = ["2026-07-08"]
    gspc_close = [6280.0]
    dates, y, sp500 = SH.build_series(raw, gspc_dates, gspc_close)
    assert dates == ["2026-07-07"]
    assert sp500 == [None]

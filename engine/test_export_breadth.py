# -*- coding: utf-8 -*-
import export_breadth as b


def test_detect_bearish_divergence():
    dates = [f"2026-01-{i:02d}" for i in range(1, 22)]
    index_series = list(range(100, 121))
    ad_line = list(range(100, 120)) + [115]
    divs = b._detect_divergences(dates, index_series, ad_line, window=20)
    assert divs and divs[0]["type"] == "bearish"


def test_detect_bullish_divergence():
    dates = [f"2026-01-{i:02d}" for i in range(1, 22)]
    index_series = list(range(121, 100, -1))
    ad_line = list(range(121, 102, -1)) + [108, 109]
    divs = b._detect_divergences(dates, index_series, ad_line, window=20)
    assert divs and divs[0]["type"] == "bullish"


def test_pending_when_history_short():
    divs = b._detect_divergences(["2026-01-01"], [100], [0], window=20)
    assert divs and divs[0]["type"] == "pending"


def test_core_fields_math():
    row = b._with_core_fields(
        "測試",
        ["2026-01-01", "2026-01-02"],
        [3, -1],
        [100, 101],
        {"advancers": 7, "decliners": 2, "unchanged": 1},
        "unit-test",
    )
    assert row["ad_diff"] == 5
    assert row["ad_ratio"] == 3.5
    assert row["ad_line"] == [3, 2]

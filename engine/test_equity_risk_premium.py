# -*- coding: utf-8 -*-
import equity_risk_premium as ERP


def test_value_at_exact_match():
    assert ERP.value_at("2026-07-09", ["2026-07-07", "2026-07-08", "2026-07-09"], [4.50, 4.52, 4.54]) == 4.54


def test_value_at_nearest_prior():
    # 2026-07-10 不在序列裡 → 用不晚於它的最近一筆(07-09)
    assert ERP.value_at("2026-07-10", ["2026-07-07", "2026-07-08", "2026-07-09"], [4.50, 4.52, 4.54]) == 4.54


def test_value_at_before_series_returns_none():
    assert ERP.value_at("2026-07-01", ["2026-07-07", "2026-07-08"], [4.50, 4.52]) is None


def test_value_at_empty_series_returns_none():
    assert ERP.value_at("2026-07-09", [], []) is None


def test_compute_erp_basic():
    # fwd PE 21.1 → 盈餘殖利率 100/21.1=4.7393;10Y=4.54 → ERP=0.20
    assert ERP.compute_erp(21.1, 4.54) == 0.20


def test_compute_erp_none_when_pe_invalid():
    assert ERP.compute_erp(0, 4.54) is None
    assert ERP.compute_erp(None, 4.54) is None
    assert ERP.compute_erp(21.1, None) is None


def test_build_series_aligns_weekly_pe_to_daily_yield():
    pe_dates = ["2026-06-25", "2026-07-02", "2026-07-10"]
    pe = [20.5, 20.8, 21.1]
    yc_dates = ["2026-06-24", "2026-06-25", "2026-07-01", "2026-07-02", "2026-07-09"]
    yc_10y = [4.40, 4.42, 4.50, 4.52, 4.54]
    dates, erp = ERP.build_series(pe_dates, pe, yc_dates, yc_10y)
    assert dates == pe_dates
    assert erp == [
        ERP.compute_erp(20.5, 4.42),
        ERP.compute_erp(20.8, 4.52),
        ERP.compute_erp(21.1, 4.54),
    ]


def test_pick_by_date_exact_match_and_missing():
    out = ERP.pick_by_date(
        ["2026-07-02", "2026-07-10"],
        ["2026-06-25", "2026-07-02"],
        [5800.0, 5900.0],
    )
    assert out == [5900.0, None]


def test_build_series_skips_points_before_yield_history():
    pe_dates = ["2020-01-01", "2026-07-02"]
    pe = [18.0, 20.8]
    yc_dates = ["2026-06-25", "2026-07-02"]
    yc_10y = [4.42, 4.52]
    dates, erp = ERP.build_series(pe_dates, pe, yc_dates, yc_10y)
    assert dates == ["2026-07-02"]
    assert erp == [ERP.compute_erp(20.8, 4.52)]

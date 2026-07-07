# -*- coding: utf-8 -*-
import tw_margin_ratio as M


def test_compute_ratio_basic():
    # 2330: 10 張 × 1000 股 × 1000 元 = 10,000,000 市值;loan 5,000,000 → 200%
    r = M.compute_ratio(5_000_000, {"2330": "10"}, {"2330": 1000.0})
    assert r == 200.0


def test_compute_ratio_excludes_etf():
    # 0050 應被排除,結果與只有 2330 相同
    r = M.compute_ratio(5_000_000, {"2330": 10, "0050": 100}, {"2330": 1000.0, "0050": 50.0})
    assert r == 200.0


def test_compute_ratio_none_when_no_loan_or_value():
    assert M.compute_ratio(0, {"2330": 10}, {"2330": 1000}) is None
    assert M.compute_ratio(5_000_000, {}, {}) is None
    assert M.compute_ratio(5_000_000, {"2330": 10}, {}) is None  # 無價 → 市值 0 → None


def test_merge_history_dedup_sort_cap():
    seed = {"dates": ["20260101", "20260102"], "ratio": [180.0, 181.0], "twii": [20000, 20100]}
    prev = {"dates": ["20260102", "20260103"], "ratio": [181.5, 182.0], "twii": [20150, 20200]}  # d2 覆蓋
    point = {"date": "20260104", "ratio": 183.0, "twii": 20300}
    dates, ratio, twii = M.merge_history(seed, prev, point, cap=3)
    assert dates == ["20260102", "20260103", "20260104"]
    assert ratio == [181.5, 182.0, 183.0]      # d2 取 prev 覆蓋值
    assert twii == [20150, 20200, 20300]


def test_merge_history_point_updates_same_day():
    seed = {"dates": ["20260105"], "ratio": [190.0], "twii": [21000]}
    point = {"date": "20260105", "ratio": 191.0, "twii": 21050}
    dates, ratio, twii = M.merge_history(seed, None, point, cap=750)
    assert dates == ["20260105"]
    assert ratio == [191.0] and twii == [21050]

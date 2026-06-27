# -*- coding: utf-8 -*-
"""半導體 forward PE 中位數與離群防護。cd engine && python test_semi_fwd_pe.py"""
import export_sentiment as e


def test_median_basic():
    # fwdPE 10, 20, 60 → 中位數 20(非平均 30,藉此區別 median vs mean)
    quotes = [
        {"epsForward": 1.0, "marketCap": 1.0, "price": 10.0},
        {"epsForward": 1.0, "marketCap": 1.0, "price": 20.0},
        {"epsForward": 1.0, "marketCap": 1.0, "price": 60.0},
    ]
    pe, incl, total = e._aggregate_semi_fwd_pe(quotes)
    assert abs(pe - 20.0) < 1e-6, pe
    assert (incl, total) == (3, 3)


def test_excludes_loss_maker_and_glitch():
    quotes = [
        {"epsForward": 2.0, "marketCap": 1.0, "price": 50.0},      # fwdPE 25
        {"epsForward": -1.0, "marketCap": 1.0, "price": 30.0},     # 虧損 → 剔除
        {"epsForward": 148.79, "marketCap": 1.0, "price": 150.0},  # glitch fwdPE~1.0 → 剔除
    ]
    pe, incl, total = e._aggregate_semi_fwd_pe(quotes)
    assert abs(pe - 25.0) < 1e-6, pe   # 只剩一檔 → 中位數=25
    assert (incl, total) == (1, 3)


def test_all_invalid_returns_none():
    quotes = [{"epsForward": -1.0, "marketCap": 1.0, "price": 10.0}]
    assert e._aggregate_semi_fwd_pe(quotes) is None


if __name__ == "__main__":
    test_median_basic()
    test_excludes_loss_maker_and_glitch()
    test_all_invalid_returns_none()
    print("OK")

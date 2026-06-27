# -*- coding: utf-8 -*-
"""半導體 forward PE 加權與離群防護。cd engine && python test_semi_fwd_pe.py"""
import export_sentiment as e


def test_weighted_harmonic_basic():
    quotes = [
        {"epsForward": 1.0, "marketCap": 800.0, "price": 40.0},
        {"epsForward": 1.0, "marketCap": 200.0, "price": 10.0},
    ]
    pe, incl, total = e._aggregate_semi_fwd_pe(quotes)
    # ΣMC / Σ(MC/PE) = 1000 / (800/40 + 200/10) = 1000/40 = 25.0
    assert abs(pe - 25.0) < 1e-6, pe
    assert (incl, total) == (2, 2)


def test_excludes_loss_maker_and_glitch():
    quotes = [
        {"epsForward": 2.0, "marketCap": 1000.0, "price": 50.0},   # 正常 fwdPE 25
        {"epsForward": -1.0, "marketCap": 500.0, "price": 30.0},   # 虧損 → 剔除
        {"epsForward": 148.79, "marketCap": 1.28e12, "price": 150.0},  # glitch fwdPE~1.0 → 剔除
    ]
    pe, incl, total = e._aggregate_semi_fwd_pe(quotes)
    assert abs(pe - 25.0) < 1e-6, pe
    assert (incl, total) == (1, 3)


def test_all_invalid_returns_none():
    quotes = [{"epsForward": -1.0, "marketCap": 100.0, "price": 10.0}]
    assert e._aggregate_semi_fwd_pe(quotes) is None


if __name__ == "__main__":
    test_weighted_harmonic_basic()
    test_excludes_loss_maker_and_glitch()
    test_all_invalid_returns_none()
    print("OK")

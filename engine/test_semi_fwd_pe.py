# -*- coding: utf-8 -*-
"""半導體 forward PE 市值加權(調和)與離群防護。cd engine && python test_semi_fwd_pe.py"""
import export_sentiment as e


def test_capweighted_harmonic_basic():
    # A 市值 800、fwdPE 40(px40/ef1);B 市值 200、fwdPE 10(px10/ef1)
    # 市值加權調和 = ΣMC / Σ(MC/PE) = 1000 / (800/40 + 200/10) = 1000/40 = 25.0
    quotes = [
        {"epsForward": 1.0, "marketCap": 800.0, "price": 40.0},
        {"epsForward": 1.0, "marketCap": 200.0, "price": 10.0},
    ]
    pe, incl, total = e._aggregate_capw_fwd_pe(quotes)
    assert abs(pe - 25.0) < 1e-6, pe
    assert (incl, total) == (2, 2)


def test_big_cap_low_pe_dominates():
    # 市值加權對「大市值低 PE」敏感:大市值 PE 10 把整體拉低
    # ΣMC=1100 / (1000/10 + 100/20) = 1100/105 ≈ 10.48
    quotes = [
        {"epsForward": 1.0, "marketCap": 1000.0, "price": 10.0},   # 大市值低 PE
        {"epsForward": 1.0, "marketCap": 100.0, "price": 20.0},
    ]
    pe, incl, total = e._aggregate_capw_fwd_pe(quotes)
    assert abs(pe - round(1100 / 105.0, 2)) < 1e-6, pe
    assert (incl, total) == (2, 2)


def test_excludes_loss_maker_and_dirty_low_pe():
    quotes = [
        {"epsForward": 2.0, "marketCap": 100.0, "price": 50.0},     # fwdPE 25,正常
        {"epsForward": -1.0, "marketCap": 100.0, "price": 30.0},    # 虧損 → 剔除
        {"epsForward": 148.79, "marketCap": 1.28e12, "price": 150.0},  # MU 髒值 fwdPE~1.0(<8)→ 剔除
        {"epsForward": 1.0, "marketCap": 100.0, "price": 7.6},      # fwdPE 7.6(<8 髒資料)→ 剔除
    ]
    pe, incl, total = e._aggregate_capw_fwd_pe(quotes)
    assert abs(pe - 25.0) < 1e-6, pe   # 只剩第一檔 → 25
    assert (incl, total) == (1, 4)


def test_all_invalid_returns_none():
    quotes = [{"epsForward": -1.0, "marketCap": 100.0, "price": 10.0}]
    assert e._aggregate_capw_fwd_pe(quotes) is None


def test_tw50_tickers():
    # 讀 tw150.txt 前 50:應為 ≤50 檔、皆 .TW、不含註解/空行
    syms = e._tw50_tickers()
    assert 1 <= len(syms) <= 50, len(syms)
    assert all(s.endswith(".TW") for s in syms), syms[:5]
    assert not any(s.startswith("#") for s in syms)
    assert syms[0] == "2330.TW", syms[0]   # 市值第一 = 台積電


if __name__ == "__main__":
    test_capweighted_harmonic_basic()
    test_big_cap_low_pe_dominates()
    test_excludes_loss_maker_and_dirty_low_pe()
    test_all_invalid_returns_none()
    test_tw50_tickers()
    print("OK")

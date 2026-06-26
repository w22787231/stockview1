# -*- coding: utf-8 -*-
import fetch_fsi as F


def test_parse_ofr_basic():
    csv = ("Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,"
           "United States,Other advanced economies,Emerging markets\n"
           "2026-06-23,1.5,0.5,0.4,0.2,0.3,0.1,0.8,0.4,0.3\n"
           "2026-06-24,-2.152,-1.165,-0.563,-0.32,-0.073,-0.032,-1.118,-0.48,-0.555\n")
    recs = F.parse_ofr(csv)
    assert len(recs) == 2
    assert recs[-1]["date"] == "2026-06-24"
    assert abs(recs[-1]["fsi"] - (-2.152)) < 1e-9
    assert abs(recs[-1]["Credit"] - (-1.165)) < 1e-9
    assert abs(recs[-1]["United States"] - (-1.118)) < 1e-9


def test_parse_skips_blank_and_dot():
    csv = ("Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,"
           "United States,Other advanced economies,Emerging markets\n"
           "2026-06-20,.,,,,,,,,\n"
           "2026-06-23,1.0,0.1,0.1,0.1,0.1,0.1,0.5,0.3,0.2\n")
    recs = F.parse_ofr(csv)
    assert len(recs) == 1
    assert recs[0]["date"] == "2026-06-23"


def test_parse_sorts_ascending():
    csv = ("Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,"
           "United States,Other advanced economies,Emerging markets\n"
           "2026-06-24,2,0,0,0,0,0,0,0,0\n"
           "2026-06-23,1,0,0,0,0,0,0,0,0\n")
    recs = F.parse_ofr(csv)
    assert [r["date"] for r in recs] == ["2026-06-23", "2026-06-24"]


def test_moving_avg():
    arr = [1, 2, 3, 4, 5]
    ma3 = F.moving_avg(arr, 3)
    assert ma3[0] is None and ma3[1] is None
    assert ma3[2] == 2.0 and ma3[3] == 3.0 and ma3[4] == 4.0


def test_align_sp500_ffill():
    dates = ["2026-06-22", "2026-06-23", "2026-06-24"]
    sp = {"2026-06-22": 6000.0, "2026-06-24": 6050.0}   # 缺 06-23
    out = F.align_sp500(dates, sp)
    assert out == [6000.0, 6000.0, 6050.0]   # 06-23 forward-fill 6000


def test_align_sp500_leading_none():
    dates = ["2026-06-20", "2026-06-23"]
    sp = {"2026-06-23": 6050.0}              # 開頭缺 → None
    out = F.align_sp500(dates, sp)
    assert out == [None, 6050.0]


def test_build_fsi_json_shape():
    recs = []
    base = 6000.0
    for i in range(60):
        d = "2026-04-%02d" % (i + 1) if i < 30 else "2026-05-%02d" % (i - 29)
        recs.append({"date": d, "fsi": float(i % 5 - 2),
                     "Credit": -1.0, "Equity valuation": -0.5, "Safe assets": -0.3,
                     "Funding": -0.1, "Volatility": 0.0,
                     "United States": -1.0, "Other advanced economies": -0.5, "Emerging markets": -0.4})
    sp = {r["date"]: base + i for i, r in enumerate(recs)}
    j = F.build_fsi_json(recs, sp, "2026-05-30", keep=40)
    assert j["default_window"] == "5y"
    assert j["windows"] == ["1m", "3m", "6m", "1y", "3y", "5y"]
    s = j["series"]
    assert len(s["dates"]) == 40 and len(s["fsi"]) == 40
    assert len(s["ma20"]) == 40 and len(s["ma50"]) == 40 and len(s["sp500"]) == 40
    assert s["ma20"][-1] is not None   # 末點 MA 有值
    cats = {c["key"]: c["val"] for c in j["breakdown"]["categories"]}
    assert cats["信用"] == -1.0 and "波動" in cats
    regs = {r["key"]: r["val"] for r in j["breakdown"]["regions"]}
    assert regs["美國"] == -1.0 and len(regs) == 3
    assert j["current"] == recs[-1]["fsi"]

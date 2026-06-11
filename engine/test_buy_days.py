# -*- coding: utf-8 -*-
"""_ma_buy_days + compute_trend buy_days 欄。cd engine && python test_buy_days.py"""
import pandas as pd, numpy as np
import adr_screen as e

def _sub_from_closes(closes):
    return pd.DataFrame({"Close": closes, "High":[c*1.01 for c in closes],
                         "Low":[c*0.99 for c in closes], "Open":closes,
                         "Volume":[1_000_000]*len(closes)})

def test_buy_days_detects_recent_up_cross_with_up_close():
    # 70 根:前 60 平、後段拉升使 EMA20 上穿 EMA60,且最後收紅
    closes=[100.0]*70+[100.0+i for i in range(1,61)]   # 130 根,中段上穿
    sub=_sub_from_closes([float(c) for c in closes])
    bd=e._ma_buy_days(sub)
    assert bd is not None and bd>=0, bd

def test_buy_days_none_when_bearish():
    closes=[float(x) for x in range(170,100,-1)]  # 一路下跌,無上穿
    sub=_sub_from_closes(closes)
    assert e._ma_buy_days(sub) is None

def test_compute_trend_row_has_buy_days():
    e._download = lambda syms, period="1y": _multi(_sub_from_closes([100.0]*70+[100.0+i for i in range(1,61)]))
    rows,failed=e.compute_trend(["AAA"])
    assert rows and "buy_days" in rows[0], (rows[0].keys() if rows else failed)

def _multi(sub):
    idx=pd.RangeIndex(len(sub))
    cols=pd.MultiIndex.from_product([["AAA"],["Open","High","Low","Close","Volume"]])
    data={("AAA",c):sub[c].values for c in ["Open","High","Low","Close","Volume"]}
    return pd.DataFrame(data, index=idx, columns=cols)

if __name__=="__main__":
    test_buy_days_detects_recent_up_cross_with_up_close()
    test_buy_days_none_when_bearish()
    test_compute_trend_row_has_buy_days()
    print("OK")

# -*- coding: utf-8 -*-
"""compute_trend row 應含 close（供 us5000 price 門檻）。cd engine && python test_compute_close.py"""
import pandas as pd, numpy as np
import adr_screen as e

def _fake_df():
    n=70; idx=pd.date_range("2025-01-01", periods=n, freq="D")
    close=pd.Series(np.linspace(100,110,n), index=idx)
    cols=pd.MultiIndex.from_product([["AAA"],["Open","High","Low","Close","Volume"]])
    data={("AAA","Open"):close,("AAA","High"):close*1.01,("AAA","Low"):close*0.99,
          ("AAA","Close"):close,("AAA","Volume"):pd.Series([1_000_000]*n,index=idx)}
    return pd.DataFrame(data, columns=cols)

def test_row_has_close():
    e._download = lambda syms, period="1y": _fake_df()   # monkeypatch 模組級下載
    rows, failed = e.compute_trend(["AAA"])
    assert rows, ("no rows", failed)
    assert "close" in rows[0], rows[0].keys()
    assert abs(rows[0]["close"] - 110.0) < 1e-6, rows[0]["close"]

if __name__=="__main__":
    test_row_has_close(); print("OK")

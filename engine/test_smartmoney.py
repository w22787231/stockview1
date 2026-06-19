# -*- coding: utf-8 -*-
import os, io
import fetch_smartmoney as S

HERE = os.path.dirname(os.path.abspath(__file__))
def _fx(name):
    with io.open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f: return f.read()

def test_parse_openinsider_extracts_buy_and_sell():
    rows = S.parse_openinsider(_fx("openinsider_sample.html"))
    assert len(rows) >= 2
    r = rows[0]
    assert set(["ticker","insider","title","trade_type","value_usd","date"]) <= set(r)
    assert r["trade_type"] in ("buy", "sell")
    assert any(x["trade_type"] == "buy" for x in rows)
    assert isinstance(r["value_usd"], (int, float))

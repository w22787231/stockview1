# -*- coding: utf-8 -*-
"""export_lite_pool 單元測試。cd engine && python test_export_lite_pool.py"""
import os, tempfile
import export_lite_pool as L

def _row(sym, state, days, close, dv, cur="USD"):
    return {"sym": sym, "cross_state": state, "cross_days": days, "close": close,
            "dv": dv, "score": 1.0, "sc5": 50.0, "r5": 1.0,
            "e5": 0.3, "e20": 0.2, "a20": 5.0, "cur": cur}

def _fake_compute(syms):
    data = {"HI":  _row("HI",  "golden", 1, 100.0, 5e7),
            "LOWP":_row("LOWP","golden", 0,   2.0, 5e7),    # 低價
            "LOWV":_row("LOWV","golden", 0, 100.0, 1e6),    # 低量
            "DEAD":_row("DEAD","death",  2,  80.0, 5e7)}
    return [data[s] for s in syms if s in data], []

def test_us5000_filters_and_lite():
    tmp = tempfile.mkdtemp()
    pl = L.run_lite_pool("us5000", "5000股", 5.0, 5e6, "USD",
                         symbols=["HI","LOWP","LOWV","DEAD"],
                         compute=_fake_compute, out_dir=tmp)
    assert pl["lite"] is True, pl
    assert pl["pool_label"] == "5000股"
    gold = [r["sym"] for r in pl["cross_signals"]["golden"]]
    assert "HI" in gold, gold
    assert "LOWP" not in gold and "LOWV" not in gold, gold      # 門檻濾掉
    assert "bt_win_rate" not in pl["cross_signals"]["golden"][0] # 無回測欄
    assert os.path.exists(os.path.join(tmp, "us5000.json"))

def test_tw_all_no_filter():
    tmp = tempfile.mkdtemp()
    pl = L.run_lite_pool("tw_all", "台股全市場", 0.0, 0.0, "TWD",
                         symbols=["HI","LOWP","LOWV","DEAD"],
                         compute=_fake_compute, out_dir=tmp)
    gold = set(r["sym"] for r in pl["cross_signals"]["golden"])
    assert gold == {"HI","LOWP","LOWV"}, gold     # 不過濾,三檔金叉全留
    assert pl["pool_label"] == "台股全市場"


def _fake_compute_buy(syms):
    d = {"BUY2": _row("BUY2","golden",2,100.0,5e7),
         "BUY7": _row("BUY7","golden",7,100.0,5e7),
         "NOBUY":_row("NOBUY","golden",1,100.0,5e7)}
    d["BUY2"]["buy_days"]=2; d["BUY7"]["buy_days"]=7; d["NOBUY"]["buy_days"]=None
    return [d[x] for x in syms if x in d], []

def test_buy_within_keeps_only_recent_buy():
    tmp = tempfile.mkdtemp()
    pl = L.run_lite_pool("us5000","5000股",0.0,0.0,"USD",buy_within=5,
                         symbols=["BUY2","BUY7","NOBUY"],
                         compute=_fake_compute_buy, out_dir=tmp)
    gold = set(r["sym"] for r in pl["cross_signals"]["golden"])
    assert gold == {"BUY2"}, gold          # 只留 buy_days<=5
    assert pl["buy_within"] == 5

if __name__ == "__main__":
    test_us5000_filters_and_lite(); test_tw_all_no_filter(); test_buy_within_keeps_only_recent_buy(); print("OK")

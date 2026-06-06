# -*- coding: utf-8 -*-
"""export_chain 單元測試：flow_of 判定 + merge 行情合併。"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from export_chain import flow_of, merge_quotes


def test_flow_inflow():
    # 量比放大且上漲 → 資金流入
    assert flow_of(2.0, 5.0) == "inflow"
    assert flow_of(1.5, 0.1) == "inflow"


def test_flow_outflow():
    # 量比放大但下跌 → 爆量出貨
    assert flow_of(2.0, -3.0) == "outflow"


def test_flow_quiet():
    # 縮量 → 觀望（不論漲跌）
    assert flow_of(0.5, 4.0) == "quiet"
    assert flow_of(0.69, -4.0) == "quiet"


def test_flow_neutral():
    # 量平、或爆量但平盤 → 量平
    assert flow_of(1.0, 2.0) == "neutral"
    assert flow_of(1.5, 0.0) == "neutral"   # 平盤爆量歸量平，非出貨
    assert flow_of(0.7, 1.0) == "neutral"   # 0.7 為 quiet 的開區間端點 → 不算 quiet


def test_flow_null():
    # 缺量比或漲跌 → None（前端不顯示徽章）
    assert flow_of(None, 1.0) is None
    assert flow_of(2.0, None) is None


def test_merge_keeps_classification():
    m = {"sym": "3363.TWO", "name": "上詮", "tags": ["FAU"], "note": "台積電夥伴"}
    q = {"last": 840.0, "r1": -4.98, "r5": 3.07, "r20": 3.07, "volr": 2.1}
    out = merge_quotes(m, q)
    assert out["sym"] == "3363.TWO"
    assert out["name"] == "上詮"
    assert out["tags"] == ["FAU"]
    assert out["note"] == "台積電夥伴"
    assert out["r1"] == -4.98 and out["r5"] == 3.07 and out["r20"] == 3.07
    assert out["volr"] == 2.1
    assert out["flow"] == "outflow"   # volr>=1.5 且 r1<0


def test_merge_missing_quote_fills_null():
    m = {"sym": "9999.TW", "name": "測試", "tags": ["X"]}
    out = merge_quotes(m, None)
    assert out["sym"] == "9999.TW" and out["name"] == "測試" and out["tags"] == ["X"]
    assert out["r1"] is None and out["r5"] is None and out["r20"] is None
    assert out["volr"] is None and out["flow"] is None


def test_merge_no_tags_no_note():
    m = {"sym": "2330.TW", "name": "台積電"}
    out = merge_quotes(m, {"last": 1, "r1": 0.5, "r5": 1, "r20": 1, "volr": 1.0})
    assert "tags" not in out and "note" not in out   # 不無中生有
    assert out["flow"] == "neutral"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

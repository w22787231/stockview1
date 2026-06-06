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


def test_build_assembles_and_fills_null(monkeypatch, tmp_path):
    import export_chain, json, io, os
    # 假定義檔：2 檔，一檔會「抓不到」
    spec = {"source":"t","note":"n","chains":[
        {"id":"x","name":"鏈X","desc":"d","concepts":["c"],"stages":[
            {"pos":"上游","name":"環A","desc":"da","concepts":["ca"],"members":[
                {"sym":"1111.TW","name":"甲","tags":["T"],"note":"備註"},
                {"sym":"9999.TW","name":"乙"}
            ]},
            {"pos":"中游","name":"空環","desc":"de","concepts":[],"members":[]}
        ]}
    ]}
    def_file = tmp_path / "tw_chain.json"
    def_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "data"
    web_dir = tmp_path / "web" / "data"
    monkeypatch.setattr(export_chain, "CHAIN_DEF", str(def_file))
    monkeypatch.setattr(export_chain, "DATA_DIR", str(out_dir))
    monkeypatch.setattr(export_chain, "WEB_DATA_DIR", str(web_dir))
    # 假 fetch：1111 有資料(爆量上漲→inflow)、9999 抓不到(None)
    monkeypatch.setattr(export_chain, "fetch", lambda syms: {
        "1111.TW": {"last":100.0,"r1":3.0,"r5":5.0,"r20":8.0,"volr":2.0},
        "9999.TW": None,
    })
    export_chain.build()
    # 兩處都該寫出且內容一致
    d1 = json.loads(io.open(str(out_dir / "tw_chain.json"), encoding="utf-8").read())
    d2 = json.loads(io.open(str(web_dir / "tw_chain.json"), encoding="utf-8").read())
    assert d1 == d2
    members = d1["chains"][0]["stages"][0]["members"]
    assert members[0]["sym"] == "1111.TW" and members[0]["flow"] == "inflow"
    assert members[0]["tags"] == ["T"] and members[0]["note"] == "備註"
    assert members[1]["sym"] == "9999.TW" and members[1]["flow"] is None  # 抓不到填 null
    assert d1["chains"][0]["stages"][1]["members"] == []  # 空環節保留、不報錯
    assert d1["failed"] == ["9999.TW"]  # 失敗收集且去重
    assert d1["chains"][0]["stages"][0]["pos"] == "上游"  # 分類結構保留


def test_build_empty_universe_exits(monkeypatch, tmp_path):
    import export_chain, json
    spec = {"chains":[{"id":"x","name":"X","stages":[{"pos":"上","name":"a","members":[]}]}]}
    def_file = tmp_path / "tw_chain.json"
    def_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(export_chain, "CHAIN_DEF", str(def_file))
    import pytest
    with pytest.raises(SystemExit):
        export_chain.build()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

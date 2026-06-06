# -*- coding: utf-8 -*-
"""export_etf 離線單元測試(注入假 fetcher，不連網)。
執行：cd engine && python test_etf.py"""
import os, json, tempfile
import export_etf as E


def _row(code, name, weight, qty):
    return {"etf": "", "etf_name": "", "code": code, "name": name,
            "weight": str(weight), "qty": str(qty)}


def _data(**etfs):
    """etfs: 00981A=[(code,name,w,q),...] → fetch_all 形態 dict。"""
    out = {}
    for etf, rows in etfs.items():
        out[etf] = [_row(*r) for r in rows]
    return out


def test_compute_changes_four_tags():
    prev = {"00981A": [_row("2330", "台積電", 10, 100), _row("2317", "鴻海", 5, 50)]}
    cur = {"00981A": [_row("2330", "台積電", 11, 120),   # 加碼(qty 100→120)
                      _row("3231", "緯創", 2, 30)]}        # 新增 / 2317 出清
    ch = E.compute_changes(cur, prev)
    by = {c["code"]: c for c in ch["00981A"]}
    assert by["2330"]["action"] == "加碼", by["2330"]
    assert by["2330"]["dqty"] == 20, by["2330"]
    assert by["3231"]["action"] == "新增", by["3231"]
    assert by["2317"]["action"] == "出清", by["2317"]
    cur2 = {"00981A": [_row("2330", "台積電", 10, 100)]}
    prev2 = {"00981A": [_row("2330", "台積電", 10, 100)]}
    ch2 = E.compute_changes(cur2, prev2)
    real = [c for c in ch2["00981A"] if c["action"] in ("新增", "出清", "加碼", "減碼")]
    assert real == [], real


def test_build_history_skips_no_change_day():
    snap = {"00981A": [_row("2330", "台積電", 10, 100)]}
    j = {"snapshot": snap, "history": [], "etfs": {}, "order": []}
    j2 = E.build_json(snap, j, today="2026-06-07")
    assert j2["history"] == [], j2["history"]


def test_build_history_appends_and_caps_30():
    j = {"snapshot": {"00981A": []}, "history": [
        {"date": f"2026-04-{d:02d}", "changes": [{"etf": "00981A"}]} for d in range(1, 31)
    ], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 10, 100)]}
    j2 = E.build_json(cur, j, today="2026-06-07")
    assert len(j2["history"]) == 30, len(j2["history"])
    assert j2["history"][0]["date"] == "2026-06-07", j2["history"][0]["date"]
    assert j2["history"][-1]["date"] != "2026-04-01", "最舊應被滾掉"


def test_build_history_same_day_dedup():
    j = {"snapshot": {"00981A": []}, "history": [], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 10, 100)]}
    j1 = E.build_json(cur, j, today="2026-06-07")
    j2 = E.build_json(cur, j1, today="2026-06-07")
    dates = [h["date"] for h in j2["history"]]
    assert dates.count("2026-06-07") == 1, dates


def test_failed_etf_keeps_old_snapshot():
    old = {"snapshot": {"00981A": [_row("2330", "台積電", 10, 100)],
                        "00982A": [_row("2454", "聯發科", 8, 80)]},
           "history": [], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 11, 120)],
           "00982A": []}
    merged = E.merge_fetched(cur, old["snapshot"])
    assert merged["00982A"] == old["snapshot"]["00982A"], "失敗檔應保留舊快照"
    assert merged["00981A"] == cur["00981A"], "成功檔應更新"


def test_all_failed_returns_none():
    assert E.merge_fetched({"00981A": [], "00982A": []}, {}) is None


def test_order_field_matches_etfs():
    j = E.build_json({"00981A": [_row("2330", "台積電", 10, 100)]},
                     None, today="2026-06-07")
    import fetch_etf as F
    assert j["order"] == list(F.ETFS.keys()), j["order"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"\n{len(fns)} passed")

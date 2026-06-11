# -*- coding: utf-8 -*-
"""build_cross_signals 單元測試（無第三方框架，純 assert）。
執行：cd engine && python test_cross_signals.py"""
import export_json as ej


def _row(sym, state, days, score=1.0, sc5=50.0, r5=1.0):
    return {"sym": sym, "cross_state": state, "cross_days": days,
            "score": score, "sc5": sc5, "r5": r5,
            "e5": 0.3, "e20": 0.2, "a20": 5.0, "cur": "USD"}


def _no_net(syms):
    """離線 downloader：grouping/sorting 測試不需真回測，避免連網拖慢。"""
    raise RuntimeError("offline stub")


def test_splits_golden_and_death():
    rows = [_row("A", "golden", 5), _row("B", "death", 2),
            _row("C", "golden", 1)]
    cs = ej.build_cross_signals(rows, downloader=_no_net)
    assert cs["n_golden"] == 2, cs["n_golden"]
    assert cs["n_death"] == 1, cs["n_death"]
    assert all(r["cross_state"] == "golden" for r in cs["golden"])
    assert all(r["cross_state"] == "death" for r in cs["death"])


def test_skips_none_state():
    rows = [_row("A", "golden", 3), _row("X", None, None)]
    cs = ej.build_cross_signals(rows, downloader=_no_net)
    syms = [r["sym"] for r in cs["golden"]] + [r["sym"] for r in cs["death"]]
    assert "X" not in syms, syms
    assert cs["n_golden"] + cs["n_death"] == 1


def test_sort_recent_first_none_last():
    # cross_days 小→前；None→墊底；同天數 score 大→前
    rows = [_row("OLD", "golden", 40, score=9),
            _row("NEW", "golden", 1, score=1),
            _row("NEVER", "golden", None, score=5),
            _row("MID_HI", "golden", 10, score=8),
            _row("MID_LO", "golden", 10, score=2)]
    cs = ej.build_cross_signals(rows, downloader=_no_net)
    order = [r["sym"] for r in cs["golden"]]
    assert order == ["NEW", "MID_HI", "MID_LO", "OLD", "NEVER"], order


def test_fresh_days_constant():
    cs = ej.build_cross_signals([_row("A", "golden", 1)], downloader=_no_net)
    assert cs["fresh_days"] == 3, cs["fresh_days"]


def test_row_has_expected_keys():
    cs = ej.build_cross_signals([_row("A", "golden", 1)], downloader=_no_net)
    r = cs["golden"][0]
    for k in ("sym", "name", "cross_state", "cross_days",
              "sc5", "r5", "score", "e5", "e20", "a20", "cur"):
        assert k in r, k


def test_empty_rows():
    cs = ej.build_cross_signals([])
    assert cs["n_golden"] == 0 and cs["n_death"] == 0
    assert cs["golden"] == [] and cs["death"] == []


def test_payload_contains_cross_signals():
    """驗證 run_pool payload 組裝把 cross_signals 帶進去(原始碼層級，免連網)。"""
    src = open("export_json.py", encoding="utf-8").read()
    assert '"cross_signals": build_cross_signals(rows)' in src, \
        "run_pool payload 尚未加入 cross_signals"


# ── 需求 A：平均報酬排行 ──────────────────────────────
def test_backtest_rankings_has_by_avg():
    """build_backtest_rankings 原始碼須回傳 by_avg(依平均報酬排序)。"""
    src = open("export_json.py", encoding="utf-8").read()
    assert '"by_avg": by_avg' in src, "build_backtest_rankings 尚未加入 by_avg"
    assert 'by_avg = sorted(' in src, "尚未依 avg 排序"


# ── 需求 B：剛觸發股加金叉回測欄位 ─────────────────────
def _gen_closes(n=300):
    """造週期性(正弦波，週期~60根)疊微升的收盤序列：保證多次 MA10/MA50 交叉
    與 >=3 筆完整波段，讓 _golden_backtest_swing 算得出統計。"""
    import math
    return [100 + 15 * math.sin(i * 2 * math.pi / 60) + i * 0.05 for i in range(n)]


def test_annotate_fresh_backtest_single_ticker():
    """單檔(下載回傳單層欄位 DataFrame)：fresh 列被標上 bt_win_rate/bt_avg/bt_n。"""
    import pandas as pd
    closes = _gen_closes()
    df = pd.DataFrame({"Close": closes})
    fresh = [{"sym": "AAA", "cross_days": 0}]
    ej._annotate_fresh_backtest(fresh, downloader=lambda ss: df)
    r = fresh[0]
    # 有足夠交叉時應標出三欄；序列保證 >=3 筆
    assert "bt_win_rate" in r and "bt_avg" in r and "bt_n" in r, r
    assert isinstance(r["bt_n"], int) and r["bt_n"] >= 1, r


def test_annotate_fresh_backtest_empty_noop():
    """空 fresh 不下載、不報錯。"""
    called = {"n": 0}
    def dl(ss): called["n"] += 1; return None
    ej._annotate_fresh_backtest([], downloader=dl)
    assert called["n"] == 0


def test_annotate_fresh_backtest_download_fail_safe():
    """下載丟例外時不應炸掉，列保持無 bt 欄位。"""
    def dl(ss): raise RuntimeError("network down")
    fresh = [{"sym": "AAA", "cross_days": 0}]
    ej._annotate_fresh_backtest(fresh, downloader=dl)
    assert "bt_win_rate" not in fresh[0]


def test_build_cross_signals_all_golden_get_bt():
    """全部金叉都跑回測（對齊 build_cross_signals 現行行為:「全部金叉都標」）；死叉僅剛觸發。"""
    import pandas as pd
    closes = _gen_closes()
    captured = {"syms": None}
    def dl(ss):
        captured["syms"] = list(ss)
        # 回傳多層欄位(group_by ticker 形態)
        cols = pd.MultiIndex.from_product([ss, ["Close"]])
        data = {(s, "Close"): closes for s in ss}
        return pd.DataFrame(data, columns=cols)
    rows = [_row("FRESH", "golden", 0), _row("OLD", "golden", 40)]
    cs = ej.build_cross_signals(rows, downloader=dl)
    g = {r["sym"]: r for r in cs["golden"]}
    assert captured["syms"] == ["FRESH", "OLD"], captured["syms"]  # 全部金叉都下載回測
    assert "bt_win_rate" in g["FRESH"], g["FRESH"]
    assert "bt_win_rate" in g["OLD"], g["OLD"]


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"\n{len(fns)} passed")

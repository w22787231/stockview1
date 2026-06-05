# -*- coding: utf-8 -*-
"""build_cross_signals 單元測試（無第三方框架，純 assert）。
執行：cd engine && python test_cross_signals.py"""
import export_json as ej


def _row(sym, state, days, score=1.0, sc5=50.0, r5=1.0):
    return {"sym": sym, "cross_state": state, "cross_days": days,
            "score": score, "sc5": sc5, "r5": r5,
            "e5": 0.3, "e20": 0.2, "a20": 5.0, "cur": "USD"}


def test_splits_golden_and_death():
    rows = [_row("A", "golden", 5), _row("B", "death", 2),
            _row("C", "golden", 1)]
    cs = ej.build_cross_signals(rows)
    assert cs["n_golden"] == 2, cs["n_golden"]
    assert cs["n_death"] == 1, cs["n_death"]
    assert all(r["cross_state"] == "golden" for r in cs["golden"])
    assert all(r["cross_state"] == "death" for r in cs["death"])


def test_skips_none_state():
    rows = [_row("A", "golden", 3), _row("X", None, None)]
    cs = ej.build_cross_signals(rows)
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
    cs = ej.build_cross_signals(rows)
    order = [r["sym"] for r in cs["golden"]]
    assert order == ["NEW", "MID_HI", "MID_LO", "OLD", "NEVER"], order


def test_fresh_days_constant():
    cs = ej.build_cross_signals([_row("A", "golden", 1)])
    assert cs["fresh_days"] == 3, cs["fresh_days"]


def test_row_has_expected_keys():
    cs = ej.build_cross_signals([_row("A", "golden", 1)])
    r = cs["golden"][0]
    for k in ("sym", "name", "cross_state", "cross_days",
              "sc5", "r5", "score", "e5", "e20", "a20", "cur"):
        assert k in r, k


def test_empty_rows():
    cs = ej.build_cross_signals([])
    assert cs["n_golden"] == 0 and cs["n_death"] == 0
    assert cs["golden"] == [] and cs["death"] == []


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"\n{len(fns)} passed")

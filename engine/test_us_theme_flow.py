# -*- coding: utf-8 -*-
import pandas as pd

import export_us_theme_flow as f


def test_classify_manual_theme_first():
    themes, method = f.classify("NVDA", {"NVDA": ["AI晶片/GPU"]}, {"NVDA": "半導體"})
    assert themes == ["AI晶片/GPU"]
    assert method == "manual"


def test_classify_industry_fallback():
    themes, method = f.classify("TEST", {}, {"TEST": "半導體設備"})
    assert themes == ["半導體設備-前段"]
    assert method == "industry_cache"


def test_multi_theme_memory_names_present():
    m = f._theme_map()
    assert "HBM/記憶體/儲存" in m["MU"]
    assert "SIMO" in f._theme_universe()


def test_manual_theme_symbols_are_clean():
    m = f._theme_map()
    assert "LUMENTUM" not in m
    assert "ARISTA" not in m
    for stale in ("BITF", "CYBR", "IIVI", "INFN", "IRBT", "LTHM", "SQ"):
        assert stale not in m
    assert "XYZ" in m
    assert "LITE" in m
    for sym, themes in m.items():
        assert themes == list(dict.fromkeys(themes))


def test_reworked_theme_groups_are_present():
    m = f._theme_map()
    expected = {
        "SPXC": "資料中心-散熱/機電/工程",
        "FIX": "資料中心-散熱/機電/工程",
        "CRDO": "CPO/光通訊/矽光子",
        "MTSI": "CPO/光通訊/矽光子",
        "NVMI": "半導體設備-量測/檢測",
        "ATEYY": "半導體設備-量測/檢測",
        "PLAB": "半導體材料/特氣/光罩",
        "VICR": "功率半導體/SiC/GaN",
        "RR": "機器人/自動化",
        "KTOS": "航太國防/太空",
        "RBRK": "資安",
        "PLTR": "AI軟體/AI資料平台",
        "BRUN": "AI雲端/算力/Neocloud",
    }
    for sym, theme in expected.items():
        assert theme in m[sym]


def test_return_uses_same_price_series():
    closes = pd.Series([100, 103, 106, 109, 112, 115])
    assert f._ret(closes, 1) == 2.68
    assert f._ret(closes, 5) == 15.0


def test_summarize_group_math():
    rows = [
        {"sym": "AAA", "theme": "AI晶片/GPU", "method": "manual", "close": 10, "r1": 2, "r5": 5, "r20": 10, "r60": 20},
        {"sym": "BBB", "theme": "AI晶片/GPU", "method": "manual", "close": 20, "r1": -1, "r5": 3, "r20": 8, "r60": 12},
        {"sym": "CCC", "theme": "未細分", "method": "unmapped", "close": 5, "r1": 0, "r5": None, "r20": None, "r60": None},
    ]
    groups = {g["theme"]: g for g in f.summarize(rows)}
    g = groups["AI晶片/GPU"]
    assert g["count"] == 2
    assert g["avg"]["r1"] == 0.5
    assert g["median"]["r5"] == 4
    assert g["up"] == 1
    assert g["down"] == 1
    assert g["up_ratio"] == 50.0

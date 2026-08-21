# -*- coding: utf-8 -*-
import math
import sys

import pandas as pd

import export_daily_checklist as D

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def eq(actual, expected, label):
    if isinstance(expected, float):
        assert actual is not None and math.isclose(actual, expected, abs_tol=1e-9), label
    else:
        assert actual == expected, label


# 交易日中間缺值必須跳過，取上一筆有效觀測值，而不是把缺值當 0。
eq(D.change([1.0, None, 1.3, 1.5], 1), 0.2, "1D 應使用上一筆有效交易日")
eq(D.change([1.0, None, 1.3, 1.5], 5), None, "20D 前資料不足必須為 None")
eq(D.percent_change([150.0, 153.0], 1), 2.0, "匯率判讀必須使用百分比變化，而不是絕對點數")

# 相對強弱 = 資產報酬 - SPY 報酬，單位為百分點。
eq(D.relative_return([100, 110], [100, 105], 1), 5.0, "RSP/SPY 相對報酬計算錯誤")
eq(D.relative_return([100, None], [100, 105], 1), None, "缺最新資產價格不可產生相對強弱")

# bp 與比值口徑必須明確。
eq(D.to_bps(0.12), 12.0, "殖利率 0.12% 應轉 12bps")
eq(D.ratio(18.0, 20.0), 0.9, "VIX9D/VIX 比值計算錯誤")
eq(D.ratio(None, 20.0), None, "缺資料不可產生比值")

# 黃金相關性只能用共同交易日；實質利率採日變動、黃金採日報酬，避免把水準直接相關化。
corr_dates = pd.date_range("2026-01-01", periods=25, freq="B")
real_fixture = pd.Series([1.0 + 0.01 * i + 0.002 * (i % 2) for i in range(25)], index=corr_dates)
gold_fixture = pd.Series([2000.0 + 2 * i + (i % 3) for i in range(25)], index=corr_dates)
gold_corr = D.real_gold_correlation(real_fixture, gold_fixture)
assert len(gold_corr.dropna()) == 5, "20日黃金相關在25個交易日中應有5筆有效值"
assert len(D.real_gold_correlation(real_fixture, gold_fixture, window=5).dropna()) == 20, "5日黃金相關在25個交易日中應有20筆有效值"
assert len(D.real_gold_correlation(real_fixture, gold_fixture, window=10).dropna()) == 15, "10日黃金相關在25個交易日中應有15筆有效值"

# VIX9D/VIX > 1 代表短期期限結構倒掛；即使 VIX9D 自身20日均值橫盤仍須示警。
vix_dates = pd.date_range("2026-01-01", periods=21, freq="B")
vix9d_flat = pd.Series([20.0] * 21, index=vix_dates)
vix_flat = pd.Series([18.0] * 21, index=vix_dates)
vix9d_term = D.vix9d_row(vix9d_flat, vix_flat)
eq(vix9d_term["score"], -2, "VIX9D/VIX > 1 必須覆蓋VIX9D自身橫盤判讀")
eq(vix9d_term["signal"], "避險升溫", "VIX9D/VIX > 1 必須標示避險升溫")
assert "VIX9D/VIX 1.111" in vix9d_term["note"], "期限結構比值必須可追溯"

# 量化判讀：百分位用有效歷史觀測值，且門檻不可把資料缺口補成 0。
eq(D.percentile(list(range(1, 26))), 100, "最新值應為歷史高位")
eq(D.judgment([2.0, 2.25, 2.40, 2.55, 2.70, 2.95], "tips")["score"], -2,
   "TIPS 五日大幅上升應為估值壓力")
eq(D.judgment([100, 101, 99, 100, 101], "relative")["score"], None,
   "相對強弱不足五日報酬觀測時不得產生分數")
eq(D.judgment([100, 101, 99, 100, 101], "relative")["signal"], "資料待補",
   "相對強弱不足五日報酬觀測時應標示資料待補")
eq(D.judgment([0, 0, 0, 0, 0, 0.5], "relative")["score"], 0,
   "五日相對 SPY 報酬未達正負一百分點應為橫盤")
eq(D.judgment([0, 0, 0, 0, 0, 0.5], "relative")["signal"], "橫盤",
   "五日相對 SPY 報酬未達正負一百分點應標示橫盤")
eq(D.judgment([], "vix")["score"], None, "缺資料不得產生分數")
eq(D.judgment([100] * 20 + [125], "vix")["score"], -2,
   "VIX 相對前二十日均值上升二成應為避險升溫")
eq(D.judgment([100] * 20 + [85], "move")["score"], 2,
   "MOVE 相對前二十日均值下降一成五應為壓力緩解")
eq(D.judgment([0, 0, 0, 0, 0, -1.0], "relative")["score"], -2,
   "五日相對 SPY 報酬達負一百分點應為內部轉弱")
eq(D.judgment([150, 150, 150, 150, 150, 152], "fx_jpy")["score"], 2,
   "USD/JPY 五日升逾一百分點應標示日圓走弱")
eq(D.judgment([150, 150, 150, 150, 150, 152], "fx_jpy")["note"], "日圓走弱／風險偏好",
   "USD/JPY 上升不可誤標為日圓走強")
eq(D.judgment([150, 150, 150, 150, 150, 148], "fx_jpy")["score"], -2,
   "USD/JPY 五日跌逾一百分點應標示日圓走強")
eq(D.judgment([150, 150, 150, 150, 150, 148], "fx_jpy")["note"], "日圓走強／避險升溫",
   "USD/JPY 下跌必須標示日圓走強與避險升溫")

# Exporter 的量化判讀只允許 -2..+2；資料不足則明確保留 None。
for kind, values in [
    ("tips", []),
    ("tips", [2.0, 2.25, 2.40, 2.55, 2.70, 2.95]),
    ("relative", [0, 0, 0, 0, 0, 1.0]),
    ("vix", [100] * 20 + [125]),
    ("move", [100] * 20 + [85]),
]:
    score = D.judgment(values, kind)["score"]
    assert score is None or -2 <= score <= 2, "judgment score 超出 -2..+2：%r" % score

# 端對端：交易日對齊→5D相對SPY報酬→列判讀，且 build 的14列都含完整量化欄位。
relative_dates = pd.date_range("2026-02-02", periods=12, freq="B")
relative_asset = pd.Series([100 + 2 * i for i in range(12)], index=relative_dates)
relative_spy = pd.Series([100 + i for i in range(11)], index=relative_dates[1:])
relative = D.relative_row("RSP", relative_asset, relative_spy)
eq(relative["changes"]["d5"], 4.17, "relative_row 應以對齊價格算5D相對SPY報酬")
eq(relative["score"], 2, "相對SPY 5D明顯轉強應為正向分數")

fixture_dates = pd.date_range("2026-03-02", periods=25, freq="B")
fixture_fred = pd.Series([2.0 + 0.01 * i for i in range(25)], index=fixture_dates)
fixture_prices = pd.DataFrame({
    "^MOVE": [100.0] * 25,
    "^VIX": [18.0] * 25,
    "^VIX3M": [19.0] * 25,
    "^VIX9D": [20.0] * 25,
    "GC=F": [2000.0 + 2 * i + (i % 3) for i in range(25)],
    "JPY=X": [150.0 + 0.1 * i for i in range(25)],
    "SPY": [100.0 + i for i in range(25)],
    "RSP": [100.0 + 2 * i for i in range(25)],
    "IWM": [100.0 + 2 * i for i in range(25)],
    "KRE": [100.0 + 2 * i for i in range(25)],
}, index=fixture_dates)
old_fred, old_yf = D.fred_series, D.P.fetch_yf_close
try:
    D.fred_series = lambda _series_id: fixture_fred
    D.P.fetch_yf_close = lambda _symbols, _start: fixture_prices
    built = D.build()
finally:
    D.fred_series, D.P.fetch_yf_close = old_fred, old_yf
built_rows = [row for group in built["groups"] for row in group["rows"]]
eq(len(built_rows), 16, "build 必須產生16個量化檢查列")
for built_row in built_rows:
    assert {"score", "level", "signal", "note"} <= set(built_row), "每列必須有完整量化判讀欄位"
vix9d_built = next(row for row in built_rows if row["key"] == "vix9d")
eq(vix9d_built["score"], -2, "build 必須把VIX9D/VIX期限結構納入生產判讀")
eq(built["charts"]["risk"]["series"]["VIX9D/VIX"]["values"][-1], 1.111, "build 必須輸出已對齊的VIX9D/VIX比值序列")
assert built["charts"]["japan"]["series"]["USD/JPY"]["values"], "build 必須輸出 USD/JPY 圖表序列"
assert built["charts"]["japan"]["series"]["日本 10Y 殖利率（月頻）"]["values"], "build 必須輸出日本10Y殖利率圖表序列"
assert built["charts"]["real_gold"]["series"]["黃金期貨"]["values"], "build 必須輸出黃金圖表序列"
assert set(built["charts"]["credit"]["series"]) == {"IG 指數殖利率", "10Y 美債殖利率", "HY 指數殖利率", "IG 利差（OAS）", "BBB 利差（OAS）", "HY 利差（OAS）"}, "結構圖表必須輸出六條信用結構序列"
assert all(series["values"] for series in built["charts"]["credit"]["series"].values()), "信用結構六條序列都必須有資料"
assert len(built["charts"]["real_gold"]["series"]["5日相關"]["values"]) == 20, "5日相關應略過前5個無法計算的交易日"
assert len(built["charts"]["real_gold"]["series"]["10日相關"]["values"]) == 15, "10日相關應略過前10個無法計算的交易日"
assert len(built["charts"]["real_gold"]["series"]["20日相關"]["values"]) == 5, "20日相關應略過前20個無法計算的交易日"

print("✅ test_daily_checklist 通過：交易日差、相對強弱、bps 與比值口徑")

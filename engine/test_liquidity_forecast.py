# -*- coding: utf-8 -*-
import pandas as pd
import json
import export_liquidity_forecast as F


weekly = pd.date_range("2026-01-07", periods=16, freq="W-WED")
sample = {
    "WTREGEN": pd.Series([600000 + i * 1000 for i in range(len(weekly))], index=weekly),
    "WRESBAL": pd.Series([2800000 + i * 2000 for i in range(len(weekly))], index=weekly),
}


def sample_series():
    return {
        **sample,
        "WALCL": pd.Series([7000000 + i * 3000 for i in range(len(weekly))], index=weekly),
        "RRPONTSYD": pd.Series([200000 + i * 500 for i in range(len(weekly))], index=weekly),
        "CURRCIR": pd.Series([2300000 + i * 750 for i in range(len(weekly))], index=weekly),
        "WLRRAFOIAL": pd.Series([250000 + i * 250 for i in range(len(weekly))], index=weekly),
    }


terminal = F.build_terminal_forecast(sample_series(), [
    {"date": "2026-12-31", "value": 850000, "source_type": "official"}
], "2026-08-20T00:00:00Z")
assert terminal["status"] == "ok"
assert terminal["tga"]["forecast"][-1]["value"] == 850000
assert terminal["tga"]["forecast"][-1]["source_type"] == "official"
forecast_dates = [point["date"] for point in terminal["tga"]["forecast"]]
assert forecast_dates == ["2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30", "2026-12-31"], "TGA 應有每月預估點，並保留官方季度末錨點"
assert terminal["tga"]["forecast"][0]["source_type"] == "seasonal_model"
assert terminal["tga"]["forecast"][0]["value"] == 619000, "TGA 每月預估應使用歷史月增減幅"
assert [point["date"] for point in terminal["reserves"]["forecast"]] == forecast_dates, "準備金應使用相同月度公式節點"
assert [point["date"] for point in terminal["full_liquidity"]["forecast"]] == forecast_dates, "完整淨流動性應使用相同月度計算點"

# 同一月份的舊資料過多時，TGA 季節模型仍只可採用最近五年，避免舊制度扭曲預測。
seasonal_dates = pd.date_range("2010-01-31", "2025-12-31", freq="ME")
seasonal_changes = [900 if date.month == 8 and date.year <= 2020 else (100 if date.month == 8 else 10)
                    for date in seasonal_dates]
seasonal_levels = pd.Series(seasonal_changes, index=seasonal_dates).cumsum()
seasonal_delta, seasonal_confidence = F._seasonal_tga_change(seasonal_levels, "2026-08-31")
assert seasonal_delta == 100, "TGA 同月份季節性只能使用最近五年歷史"
assert seasonal_confidence == "medium"

# 準備金公式中的 Fed 資產等項目也要採用月度季節變動，不能以日趨勢外插。
component_seasonal_dates = pd.date_range("2021-01-31", "2026-07-31", freq="ME")
component_seasonal_changes = [120 if date.month == 8 else 10 for date in component_seasonal_dates]
component_seasonal_levels = pd.Series(component_seasonal_changes, index=component_seasonal_dates).cumsum()
component_delta, component_confidence = F._trend_change(component_seasonal_levels, "2026-08-31")
assert component_delta == 120, "準備金的底層帳務項目應採歷史同月份月增減"
assert component_confidence == "medium"
assert len(terminal["factors"]) == 6
assert {factor["id"] for factor in terminal["factors"]} == {
    "tga", "walcl", "rrp", "currency", "fima_other", "treasury_events"
}
terminal_factors = {factor["id"]: factor for factor in terminal["factors"]}
assert terminal_factors["tga"]["forecast"][-1]["value"] == 850000
assert terminal_factors["tga"]["forecast"][-1]["source_type"] == "official"
assert all(key in terminal_factors["walcl"]["forecast"][-1]
           for key in ("value", "change", "source_type", "confidence"))
assert all("confidence" in point for point in terminal["tga"]["forecast"])
assert set(terminal) >= {"tga", "reserves", "full_liquidity", "factors", "targets"}

result = F.build_levels(sample, "2026-08-20T00:00:00Z")
assert result["status"] == "ok"
assert result["model_version"] == "levels-v1"
assert result["tga"]["values"][-1] == 615000
assert result["reserves"]["values"][-1] == 2830000
assert result["tga"]["as_of"] == "2026-04-22"
assert F.build_levels({"WTREGEN": pd.Series(dtype=float)})["status"] == "insufficient_data"

# 會在解析 Treasury 官方季末現金假設時失敗：若月份轉季末、單位換算或官方標記錯誤，
# 這個可直接由公告文字推導的資料契約必須失敗。
treasury_html = (
    "During the October–December 2026 quarter, Treasury assumes an "
    "end-of-December cash balance of $850 billion."
)
expected_target = [{
    "date": "2026-12-31", "value": 850000, "source_type": "official", "confidence": "high"
}]
assert F.parse_treasury_tga_targets(treasury_html) == expected_target

# 會在未確認 FIMA 序列、用零填補或略過空序列時失敗：空資料必須明確降級。
assert F.factor_status(pd.Series(dtype=float)) == "missing"
assert F.factor_status(pd.Series([1.0], index=pd.to_datetime(["2026-08-19"]))) == "available"

# 會在抓取錯誤的 FIMA 代號（例如 WLFN，它其實是流通中的聯準會鈔票）時失敗。
factor_fixture = {
    "WTREGEN": sample["WTREGEN"], "WRESBAL": sample["WRESBAL"],
    "WALCL": sample_series()["WALCL"], "RRPONTSYD": sample_series()["RRPONTSYD"],
    "CURRCIR": sample_series()["CURRCIR"], "WLRRAFOIAL": sample_series()["WLRRAFOIAL"],
}
factors = F.fetch_factor_series(lambda series_id: factor_fixture.get(series_id, pd.Series(dtype=float)))
assert set(factors) == set(factor_fixture)
assert factors["WLRRAFOIAL"].iloc[-1] == factor_fixture["WLRRAFOIAL"].iloc[-1]

# 會在「最新融資文件 → Financing Estimates → 官方公告」鏈結斷裂時失敗。
listing_html = '<a href="/news/press-releases/sb0000">Financing Estimates: Test</a>'
def fake_http_get(url):
    return treasury_html if url.endswith("sb0000") else listing_html
assert F.fetch_treasury_tga_targets(fake_http_get) == expected_target

# 匯出入口必須整合所有六項 FRED 因子和 Treasury 官方目標，不能再退回舊版兩線資料。
live_contract = F.build_from_fred(
    lambda series_id: factor_fixture.get(series_id, pd.Series(dtype=float)),
    fake_http_get,
    "2026-08-20T00:00:00Z",
)
assert live_contract["status"] == "ok"
assert all(key in live_contract for key in ("tga", "reserves", "full_liquidity", "factors"))
assert all("confidence" in point for point in live_contract["tga"]["forecast"])

# GitHub Actions 已提供 FRED_API_KEY 時，資料引擎必須使用官方 API 回應，
# 不能只能依賴在 runner 上可能逾時的公開 CSV 端點。
fred_api_payload = json.dumps({"observations": [
    {"date": "2026-08-12", "value": "963950"},
    {"date": "2026-08-19", "value": "."},
]})
fred_api_series = F.parse_fred_api_observations("WTREGEN", fred_api_payload)
assert fred_api_series.index[-1].strftime("%Y-%m-%d") == "2026-08-12"
assert fred_api_series.iloc[-1] == 963950.0

# 會在把 TGA、ON RRP、流通貨幣或 FIMA/其他負債漏扣、重複扣除或方向相反時失敗。
# 預期值是依資產負債表公式手算：10,000 - 5,000 - (-2,000) - 3,000 - 1,000 = 3,000。
components = {"walcl": 10000, "tga": 5000, "rrp": -2000, "currency": 3000, "fima_other": 1000}
assert F.reserve_change(components) == 3000
assert F.full_liquidity_change(components) == 3000
assert F.reserve_change({**components, "tga": 10000}) == -2000

# 會在把準備金與完整淨流動性相加，或把 TGA 在任一水位重複計入時失敗。
levels = {"walcl": 10000, "tga": 5000, "rrp": 2000, "currency": 3000, "fima_other": 1000}
assert F.full_liquidity_value(levels) == -1000

component_series = {
    "WTREGEN": pd.Series([100], index=pd.to_datetime(["2026-08-19"])),
    "WRESBAL": pd.Series([500], index=pd.to_datetime(["2026-08-19"])),
    "WALCL": pd.Series([10000], index=pd.to_datetime(["2026-08-19"])),
    "RRPONTSYD": pd.Series([2], index=pd.to_datetime(["2026-08-19"])),
    "CURRCIR": pd.Series([3000], index=pd.to_datetime(["2026-08-19"])),
    "WLRRAFOIAL": pd.Series([1000], index=pd.to_datetime(["2026-08-19"])),
}
component_targets = [{
    "date": "2026-08-31", "value": 200, "source_type": "official",
    "confidence": "high", "as_of": "2026-08-19",
}]
component_forecasts = F.forecast_components(component_series, component_targets)
assert component_forecasts[0]["change"] == {
    "walcl": 0, "tga": 100, "rrp": 0, "currency": 0, "fima_other": 0,
}
reserve_forecasts = F.forecast_reserves(component_series, component_forecasts)
liquidity_forecasts = F.forecast_full_liquidity(component_forecasts)
assert reserve_forecasts[0]["value"] == 400
assert reserve_forecasts[0]["change"] == -100
assert liquidity_forecasts[0]["value"] == 3800
assert liquidity_forecasts[0]["change"] == -100
assert reserve_forecasts[0]["source_type"] == "model"
assert liquidity_forecasts[0]["source_type"] == "model"
print("liquidity levels tests passed")

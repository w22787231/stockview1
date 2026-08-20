# -*- coding: utf-8 -*-
import pandas as pd
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
        "WLFN": pd.Series([250000 + i * 250 for i in range(len(weekly))], index=weekly),
    }


terminal = F.build_terminal_forecast(sample_series(), [
    {"date": "2026-12-31", "value": 850000, "source_type": "official"}
], "2026-08-20T00:00:00Z")
assert terminal["status"] == "ok"
assert terminal["tga"]["forecast"][-1]["value"] == 850000
assert terminal["tga"]["forecast"][-1]["source_type"] == "official"
assert len(terminal["factors"]) == 6
assert {factor["id"] for factor in terminal["factors"]} == {
    "tga", "walcl", "rrp", "currency", "fima_other", "treasury_events"
}
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
    "CURRCIR": sample_series()["CURRCIR"], "WLRRAFOIAL": sample_series()["WLFN"],
}
factors = F.fetch_factor_series(lambda series_id: factor_fixture.get(series_id, pd.Series(dtype=float)))
assert set(factors) == set(factor_fixture)
assert factors["WLRRAFOIAL"].iloc[-1] == factor_fixture["WLRRAFOIAL"].iloc[-1]

# 會在「最新融資文件 → Financing Estimates → 官方公告」鏈結斷裂時失敗。
listing_html = '<a href="/news/press-releases/sb0000">Financing Estimates: Test</a>'
def fake_http_get(url):
    return treasury_html if url.endswith("sb0000") else listing_html
assert F.fetch_treasury_tga_targets(fake_http_get) == expected_target
print("liquidity levels tests passed")

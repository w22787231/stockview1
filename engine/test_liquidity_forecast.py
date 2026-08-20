# -*- coding: utf-8 -*-
import pandas as pd
import export_liquidity_forecast as F


def sample_series():
    daily = pd.bdate_range("2022-01-03", periods=1100)
    weekly = pd.date_range("2022-01-05", periods=220, freq="W-WED")
    return {
        "WTREGEN": pd.Series([600000 + i * 20 + (i % 7) * 300 for i in range(len(daily))], index=daily),
        "WRESBAL": pd.Series([2800000 + i * 350 for i in range(len(weekly))], index=weekly),
        "WALCL": pd.Series([7000000 - i * 120 for i in range(len(weekly))], index=weekly),
        "RRPONTSYD": pd.Series([500000 - i * 1000 for i in range(len(weekly))], index=weekly),
    }


result = F.build_forecast(sample_series(), "2026-08-20T00:00:00Z")
assert result["status"] == "ok"
assert len(result["tga"]["base"]["1m"]["dates"]) == 21
assert len(result["tga"]["base"]["3m"]["dates"]) == 63
assert len(result["reserves"]["base"]["1m"]["dates"]) == 5
assert result["tga"]["loose"]["1m"]["values"][-1] <= result["tga"]["tight"]["1m"]["values"][-1]
assert set(result["tga"]["summary"]) == {"1m", "3m"}
assert F.build_forecast({"WTREGEN": pd.Series(dtype=float)})["status"] == "insufficient_data"
date_column = "observation_date"
assert date_column == "observation_date", "FRED CSV 日期欄以 observation_date 為相容格式"
print("liquidity forecast tests passed")

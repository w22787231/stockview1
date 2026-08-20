# -*- coding: utf-8 -*-
import pandas as pd
import export_liquidity_forecast as F


weekly = pd.date_range("2026-01-07", periods=16, freq="W-WED")
sample = {
    "WTREGEN": pd.Series([600000 + i * 1000 for i in range(len(weekly))], index=weekly),
    "WRESBAL": pd.Series([2800000 + i * 2000 for i in range(len(weekly))], index=weekly),
}
result = F.build_levels(sample, "2026-08-20T00:00:00Z")
assert result["status"] == "ok"
assert result["model_version"] == "levels-v1"
assert result["tga"]["values"][-1] == 615000
assert result["reserves"]["values"][-1] == 2830000
assert result["tga"]["as_of"] == "2026-04-22"
assert F.build_levels({"WTREGEN": pd.Series(dtype=float)})["status"] == "insufficient_data"
print("liquidity levels tests passed")

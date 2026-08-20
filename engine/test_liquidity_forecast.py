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
assert set(terminal) >= {"tga", "reserves", "full_liquidity", "factors", "targets"}

result = F.build_levels(sample, "2026-08-20T00:00:00Z")
assert result["status"] == "ok"
assert result["model_version"] == "levels-v1"
assert result["tga"]["values"][-1] == 615000
assert result["reserves"]["values"][-1] == 2830000
assert result["tga"]["as_of"] == "2026-04-22"
assert F.build_levels({"WTREGEN": pd.Series(dtype=float)})["status"] == "insufficient_data"
print("liquidity levels tests passed")

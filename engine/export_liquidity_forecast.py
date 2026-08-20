# -*- coding: utf-8 -*-
"""輸出 TGA 與銀行準備金的官方歷史水位；不做預測或累加。"""
import datetime as dt
import io
import json
import os
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "liquidity_forecast.json")
START = "2018-01-01"


def fred_series(series_id, start=START):
    """讀取 FRED 官方 CSV，回傳原始觀測值與日期。"""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s" % (series_id, start)
    req = urllib.request.Request(url, headers={"User-Agent": "stockview1/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            df = pd.read_csv(io.StringIO(response.read().decode("utf-8")))
        date_col = "DATE" if "DATE" in df.columns else "observation_date"
        if date_col not in df.columns or series_id not in df.columns:
            raise ValueError("FRED CSV missing required columns")
        values = pd.to_numeric(df[series_id].replace(".", np.nan), errors="coerce")
        return pd.Series(values.values, index=pd.to_datetime(df[date_col]), dtype=float).dropna().sort_index()
    except Exception as exc:
        print("[liquidity-levels] FRED %s failed: %s" % (series_id, exc))
        return pd.Series(dtype=float)


def _block(series):
    series = series.dropna().astype(float).sort_index()
    return {
        "dates": [date.strftime("%Y-%m-%d") for date in series.index],
        "values": [round(float(value), 3) for value in series.values],
        "as_of": series.index[-1].strftime("%Y-%m-%d"),
        "latest": round(float(series.iloc[-1]), 3),
    }


FACTOR_CONTRACT = (
    ("tga", "TGA"),
    ("walcl", "Fed assets"),
    ("rrp", "ON RRP"),
    ("currency", "Currency in circulation"),
    ("fima_other", "FIMA / other liabilities"),
    ("treasury_events", "Treasury cash-flow events"),
)


def terminal_dates(as_of, months=6):
    """Return the monthly endpoints used by the terminal forecast contract."""
    end = pd.Timestamp(as_of) + pd.offsets.MonthEnd(1)
    return [date.strftime("%Y-%m-%d") for date in pd.date_range(end, periods=months, freq="ME")]


def _points(series):
    series = series.dropna().astype(float).sort_index()
    return [{"date": date.strftime("%Y-%m-%d"), "value": round(float(value), 3),
             "source_type": "actual", "confidence": "high",
             "as_of": date.strftime("%Y-%m-%d")}
            for date, value in series.items()]


def _forecast_point(date, value, source_type, as_of):
    return {"date": date, "value": round(float(value), 3),
            "change": round(float(value), 3), "source_type": source_type,
            "confidence": "high" if source_type == "official" else "medium",
            "as_of": as_of}


def build_terminal_forecast(series_map, tga_targets, generated_at=None):
    """Build the stable JSON envelope; forecasting methods are added in later tasks."""
    required = ("WTREGEN", "WRESBAL")
    if any(key not in series_map or series_map[key] is None or series_map[key].dropna().empty for key in required):
        return {"status": "insufficient_data", "generated_at": generated_at,
                "tga": {}, "reserves": {}, "full_liquidity": {},
                "factors": [], "targets": []}

    as_of = pd.Timestamp(series_map["WTREGEN"].dropna().index[-1]).strftime("%Y-%m-%d")
    dates = terminal_dates(as_of)
    official_targets = {target["date"]: target for target in tga_targets
                        if target.get("source_type") == "official"}
    dates = sorted(set(dates) | set(official_targets))
    tga_latest = float(series_map["WTREGEN"].dropna().iloc[-1])
    tga_forecast = []
    for date in dates:
        target = official_targets.get(date)
        value = target["value"] if target else tga_latest
        source_type = "official" if target else "model"
        point = _forecast_point(date, value, source_type, as_of)
        point["change"] = round(float(value) - tga_latest, 3)
        tga_forecast.append(point)

    def line(series_key):
        series = series_map.get(series_key, pd.Series(dtype=float))
        return {"actual": _points(series), "forecast": []}

    tga = line("WTREGEN")
    tga["forecast"] = tga_forecast
    return {
        "status": "ok",
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tga": tga,
        "reserves": line("WRESBAL"),
        "full_liquidity": line("FULL_LIQUIDITY"),
        "factors": [{"id": factor_id, "name": name} for factor_id, name in FACTOR_CONTRACT],
        "targets": tga_forecast,
    }


def build_levels(series_map, generated_at=None):
    required = ("WTREGEN", "WRESBAL")
    if any(key not in series_map or series_map[key] is None or len(series_map[key].dropna()) < 2 for key in required):
        return {"generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "insufficient_data", "tga": {}, "reserves": {}}
    return {
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
        "model_version": "levels-v1",
        "sources": {"tga": "FRED WTREGEN", "reserves": "FRED WRESBAL"},
        "tga": _block(series_map["WTREGEN"]),
        "reserves": _block(series_map["WRESBAL"]),
    }


def build_from_fred():
    return build_levels({key: fred_series(key) for key in ("WTREGEN", "WRESBAL")})


if __name__ == "__main__":
    payload = build_from_fred()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("[liquidity-levels] %s -> %s" % (payload["status"], OUT))

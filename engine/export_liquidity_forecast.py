# -*- coding: utf-8 -*-
"""輸出 TGA 與銀行準備金的情境預估；數字是模型預估，不是官方預測。"""
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
HORIZONS = {"1m": 21, "3m": 63}


def fred_series(series_id, start=START):
    """優先使用官方 FRED CSV，避免前端資料更新依賴瀏覽器或私有金鑰。"""
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
        print("[liquidity-forecast] FRED %s failed: %s" % (series_id, exc))
        return pd.Series(dtype=float)


def _block(series):
    s = series.dropna().astype(float)
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index], "values": [round(float(v), 3) for v in s.values]}


def _accumulate(start, changes):
    return np.asarray(start + np.cumsum(changes), dtype=float)


def _prior_changes(changes, future_date, years=3):
    values = []
    for year in range(1, years + 1):
        target = future_date - pd.DateOffset(years=year)
        value = changes.asof(target)
        if pd.notna(value):
            values.append(float(value))
    return values


def tga_paths(tga, days):
    tga = tga.dropna().astype(float).sort_index()
    future = pd.bdate_range(tga.index[-1] + pd.offsets.BDay(), periods=days)
    changes = tga.diff().dropna()
    scenario_changes = {"base": [], "loose": [], "tight": []}
    fallback = changes.tail(63)
    for date in future:
        samples = _prior_changes(changes, date)
        if len(samples) < 2:
            samples = fallback.tolist()
        scenario_changes["base"].append(float(np.median(samples)))
        scenario_changes["loose"].append(float(np.quantile(samples, .25)))
        scenario_changes["tight"].append(float(np.quantile(samples, .75)))
    return {name: {"dates": [d.strftime("%Y-%m-%d") for d in future], "values": [round(float(v), 3) for v in _accumulate(tga.iloc[-1], delta)]}
            for name, delta in scenario_changes.items()}


def _weekly_change(series):
    return series.dropna().astype(float).resample("W-WED").last().diff().dropna()


def reserve_paths(reserves, walcl, rrp, tga_path, weeks):
    reserves = reserves.dropna().astype(float).resample("W-WED").last().dropna()
    walcl_delta = _weekly_change(walcl).tail(13).median()
    rrp_delta = _weekly_change(rrp).tail(13).median()
    # 將無法從三條主要帳戶解釋的近期中位數列為校正項，避免假裝會計恆等式完全精準。
    aligned = pd.concat([reserves.diff().rename("res"), _weekly_change(walcl).rename("walcl"), _weekly_change(rrp).rename("rrp")], axis=1).dropna()
    # 對齊的歷史 TGA 週變動在呼叫端傳入，避免不同頻率直接相減。
    hist_tga = tga_path["historical"].resample("W-WED").last().diff().rename("tga")
    aligned = aligned.join(hist_tga, how="inner").dropna().tail(13)
    residual = (aligned["res"] - aligned["walcl"] + aligned["tga"] + aligned["rrp"]).median()
    dates = pd.date_range(reserves.index[-1] + pd.offsets.Week(weekday=2), periods=weeks, freq="W-WED")
    out = {}
    for scenario in ("base", "loose", "tight"):
        tga = pd.Series(tga_path[scenario]["values"], index=pd.to_datetime(tga_path[scenario]["dates"]))
        weekly_tga = tga.resample("W-WED").last().reindex(dates, method="ffill")
        weekly_tga = pd.concat([pd.Series([tga_path[scenario]["values"][0]], index=[reserves.index[-1]]), weekly_tga])
        tga_delta = weekly_tga.diff().iloc[1:].to_numpy()
        rrp_level = max(float(rrp.dropna().iloc[-1]), 0.0)
        values = []
        current = float(reserves.iloc[-1])
        for change in tga_delta:
            rrp_level = max(0.0, rrp_level + float(rrp_delta))
            current += float(walcl_delta) - float(change) - float(rrp_delta) + float(residual)
            values.append(round(current, 3))
        out[scenario] = {"dates": [d.strftime("%Y-%m-%d") for d in dates], "values": values}
    return out


def _summary(actual, paths):
    latest = float(actual.dropna().iloc[-1])
    return {window: {"value": paths["base"][window]["values"][-1], "change": round(paths["base"][window]["values"][-1] - latest, 3)}
            for window in HORIZONS}


def build_forecast(series_map, generated_at=None):
    required = ("WTREGEN", "WRESBAL", "WALCL", "RRPONTSYD")
    if any(key not in series_map or series_map[key] is None or len(series_map[key].dropna()) < 80 for key in required):
        return {"generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "insufficient_data", "tga": {}, "reserves": {}}
    tga, reserves, walcl, rrp = (series_map[key].dropna().astype(float).sort_index() for key in required)
    tga_out = {"actual": _block(tga.tail(520))}
    reserve_out = {"actual": _block(reserves.tail(260))}
    for window, days in HORIZONS.items():
        tpaths = tga_paths(tga, days)
        for scenario, block in tpaths.items():
            tga_out.setdefault(scenario, {})[window] = block
        weeks = int(np.ceil(days / 5))
        tpaths["historical"] = tga
        rpaths = reserve_paths(reserves, walcl, rrp, tpaths, weeks)
        for scenario, block in rpaths.items():
            reserve_out.setdefault(scenario, {})[window] = block
    tga_out["summary"] = _summary(tga, tga_out)
    reserve_out["summary"] = _summary(reserves, reserve_out)
    return {"generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "ok",
            "model_version": "seasonal-v1", "as_of": {key: series_map[key].dropna().index[-1].strftime("%Y-%m-%d") for key in required},
            "assumptions": {"tga_years": 3, "reserve_weeks": 13, "sources": {"tga": "FRED WTREGEN", "reserves": "FRED WRESBAL", "walcl": "FRED WALCL", "rrp": "FRED RRPONTSYD"}},
            "tga": tga_out, "reserves": reserve_out}


def build_from_fred():
    data = {key: fred_series(key) for key in ("WTREGEN", "WRESBAL", "WALCL", "RRPONTSYD")}
    # RRPONTSYD 的 FRED 單位是十億美元，其餘三條帳戶皆為百萬美元。
    data["RRPONTSYD"] = data["RRPONTSYD"] * 1000
    return build_forecast(data)


if __name__ == "__main__":
    payload = build_from_fred()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("[liquidity-forecast] %s -> %s" % (payload["status"], OUT))

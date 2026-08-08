# -*- coding: utf-8 -*-
"""每日市場檢查表資料 → data/daily_checklist.json。"""
import datetime as dt
import io
import json
import os
import urllib.request

import numpy as np
import pandas as pd

import fetch_pi as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "daily_checklist.json")
START = "2020-01-01"


def change(values, periods):
    valid = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(valid) <= periods:
        return None
    return round(valid[-1] - valid[-1 - periods], 2)


def relative_return(asset, benchmark, periods):
    if len(asset) <= periods or len(benchmark) <= periods:
        return None
    a0, a1, b0, b1 = asset[-1 - periods], asset[-1], benchmark[-1 - periods], benchmark[-1]
    if any(v is None or pd.isna(v) or float(v) == 0 for v in (a0, a1, b0, b1)):
        return None
    return round(((float(a1) / float(a0) - 1) - (float(b1) / float(b0) - 1)) * 100, 2)


def to_bps(value):
    return None if value is None or pd.isna(value) else round(float(value) * 100, 1)


def ratio(numerator, denominator):
    if numerator is None or denominator is None or pd.isna(numerator) or pd.isna(denominator) or float(denominator) == 0:
        return None
    return round(float(numerator) / float(denominator), 3)


def fred_series(series_id):
    series = P.fetch_fred(series_id, START)
    if series is not None and len(series.dropna()):
        return series
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s" % (series_id, START)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # 本機未設 FRED_API_KEY 時會逐個走備援；短逾時避免單次匯出被失效網路拖住。
        with urllib.request.urlopen(req, timeout=8) as response:
            df = pd.read_csv(io.StringIO(response.read().decode("utf-8")))
        value = pd.to_numeric(df[series_id].replace(".", np.nan), errors="coerce")
        return pd.Series(value.values, index=pd.to_datetime(df["DATE"]), dtype=float).sort_index()
    except Exception as exc:
        print("[daily-checklist] FRED %s 失敗: %s" % (series_id, exc))
        return None


def row(key, label, series, unit, source, frequency="日", change_unit="pt"):
    values = [] if series is None else series.dropna().astype(float).tolist()
    last = values[-1] if values else None
    def diff(periods):
        value = change(values, periods)
        return to_bps(value) if value is not None and change_unit == "bps" else value
    return {"key": key, "label": label, "unit": unit, "source": source, "frequency": frequency,
            "available": last is not None, "last": None if last is None else round(last, 3),
            "change_unit": change_unit,
            "changes": {"today": diff(1), "d1": diff(1), "d5": diff(5), "d20": diff(20)},
            "as_of": None if series is None or series.dropna().empty else str(series.dropna().index[-1].date())}


def chart_series(series, keep=520):
    """前端圖表用的日期和值；來源缺失時仍回傳空序列。"""
    if series is None:
        return {"dates": [], "values": []}
    s = series.dropna().astype(float).tail(keep)
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "values": [round(float(v), 3) for v in s.values]}


def relative_row(symbol, asset, benchmark):
    if asset is None or benchmark is None:
        values, as_of = [], None
    else:
        aligned = pd.concat([asset.rename("asset"), benchmark.rename("benchmark")], axis=1).dropna()
        values = aligned
        as_of = str(aligned.index[-1].date()) if len(aligned) else None
    def rel(periods):
        if not isinstance(values, pd.DataFrame) or len(values) <= periods:
            return None
        return relative_return(values["asset"].tolist(), values["benchmark"].tolist(), periods)
    return {"key": symbol.lower() + "_spy", "label": symbol + " / SPY", "unit": "%pt",
            "source": "Yahoo Finance", "frequency": "日", "available": isinstance(values, pd.DataFrame) and len(values) > 1,
            "last": rel(1), "change_unit": "%pt", "changes": {"today": rel(1), "d1": rel(1), "d5": rel(5), "d20": rel(20)},
            "as_of": as_of, "note": "相對 SPY 報酬"}


def build():
    bei, hy, ig, y2, y10, y30, tips = (fred_series(x) for x in (
        "T10YIE", "BAMLH0A0HYM2", "BAMLC0A0CM", "DGS2", "DGS10", "DGS30", "DFII10"))
    prices = P.fetch_yf_close(["^MOVE", "^VIX", "^VIX3M", "^VIX9D", "SPY", "RSP", "IWM", "KRE"], START)
    col = lambda name: P._col(prices, name)
    groups = [
        {"title": "利率／通膨", "rows": [
            row("y2", "2Y 名目利率", y2, "%", "FRED DGS2", change_unit="bps"),
            row("y10", "10Y 名目利率", y10, "%", "FRED DGS10", change_unit="bps"),
            row("y30", "30Y 名目利率", y30, "%", "FRED DGS30", change_unit="bps"),
            row("tips10", "10Y TIPS", tips, "%", "FRED DFII10", change_unit="bps"),
            row("bei10", "10Y BEI", bei, "%", "FRED T10YIE", change_unit="bps"),
            row("hy_oas", "HY OAS", hy, "%", "FRED BAMLH0A0HYM2", change_unit="bps"),
            row("ig_oas", "IG OAS", ig, "%", "FRED BAMLC0A0CM", change_unit="bps")]},
        {"title": "信用／波動", "rows": [row("move", "MOVE", col("^MOVE"), "pt", "Yahoo Finance ^MOVE"), row("vix", "VIX", col("^VIX"), "pt", "Yahoo Finance ^VIX"), row("vix3m", "VIX3M", col("^VIX3M"), "pt", "Yahoo Finance ^VIX3M"), row("vix9d", "VIX9D", col("^VIX9D"), "pt", "Yahoo Finance ^VIX9D")]},
    ]
    spy = col("SPY")
    rel = [relative_row(sym, col(sym), spy) for sym in ("RSP", "IWM", "KRE")]
    groups.append({"title": "股票內部", "rows": rel})
    return {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "groups": groups,
            "charts": {
                "rates": {"title": "利率結構", "series": {"2Y 名目": chart_series(y2), "10Y 名目": chart_series(y10), "30Y 名目": chart_series(y30), "10Y TIPS": chart_series(tips), "10Y BEI": chart_series(bei)}},
                "risk": {"title": "波動與信用壓力", "series": {"MOVE": chart_series(col("^MOVE")), "VIX": chart_series(col("^VIX")), "VIX9D": chart_series(col("^VIX9D")), "HY OAS": chart_series(hy)}},
                "internals": {"title": "股票內部相對強弱", "series": {"SPY": chart_series(spy), "RSP": chart_series(col("RSP")), "IWM": chart_series(col("IWM")), "KRE": chart_series(col("KRE"))}},
            }}


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("[daily-checklist] -> data/daily_checklist.json")

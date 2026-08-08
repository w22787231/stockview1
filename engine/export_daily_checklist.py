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


def percentile(values):
    """最新有效值在至少二十筆有效歷史觀測中的百分位。"""
    valid = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(valid) < 20:
        return None
    return round(sum(v <= valid[-1] for v in valid) / len(valid) * 100)


def _level(values):
    value = percentile(values)
    if value is None:
        return None
    band = "高" if value >= 80 else ("低" if value <= 20 else "中")
    return "%s %d%%" % (band, value)


def judgment(values, kind):
    """依單列五日變化產生判讀；各列刻意獨立，不做加總。"""
    valid = [float(v) for v in values if v is not None and not pd.isna(v)]
    if not valid:
        return {"score": None, "level": None, "signal": "資料待補", "note": "資料不足"}

    level = _level(valid)
    # relative 傳入的是已算好的 5D 相對 SPY 報酬序列；其他類型才是原始數值序列。
    delta5 = valid[-1] if kind == "relative" and len(valid) >= 6 else change(valid, 5)
    if kind in ("vix", "move"):
        if len(valid) < 21:
            return {"score": None, "level": level, "signal": "資料待補", "note": "資料不足"}
        baseline = sum(valid[-21:-1]) / 20
        if baseline == 0:
            return {"score": None, "level": level, "signal": "資料待補", "note": "基準值不可為零"}
        move = (valid[-1] / baseline - 1) * 100
        threshold = 20 if kind == "vix" else 15
        if move >= threshold:
            return {"score": -2, "level": level, "signal": "避險升溫", "note": "%s 相對20日均值上升 %.1f%%" % (kind.upper(), move)}
        if move <= -threshold:
            return {"score": 2, "level": level, "signal": "壓力緩解", "note": "%s 相對20日均值下降 %.1f%%" % (kind.upper(), abs(move))}
        return {"score": 0, "level": level, "signal": "橫盤", "note": "%s 相對20日均值變化有限" % kind.upper()}

    if delta5 is None:
        return {"score": None, "level": level, "signal": "資料待補", "note": "資料不足"}

    thresholds = {"tips": 0.15, "bei": 0.12, "yield": 0.15, "oas": 0.20, "relative": 1.0}
    threshold = thresholds.get(kind)
    if threshold is None:
        return {"score": None, "level": level, "signal": "資料待補", "note": "未知判讀類型"}
    negative_notes = {"tips": "估值壓力", "bei": "通膨升溫", "yield": "利率壓力", "oas": "信用利差擴大", "relative": "內部轉弱"}
    positive_notes = {"tips": "估值壓力緩解", "bei": "通膨降溫", "yield": "利率壓力緩解", "oas": "信用利差收斂", "relative": "內部轉強"}
    if delta5 >= threshold:
        signal = "↑ 加速" if kind != "relative" else "↑ 轉強"
        score = 2 if kind == "relative" else -2
        note = positive_notes[kind] if kind == "relative" else negative_notes[kind]
    elif delta5 <= -threshold:
        signal = "↓ 緩解" if kind != "relative" else "↓ 轉弱"
        score = -2 if kind == "relative" else 2
        note = negative_notes[kind] if kind == "relative" else positive_notes[kind]
    else:
        score, signal, note = 0, "橫盤", "五日變化有限"
    return {"score": score, "level": level, "signal": signal, "note": note}


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


def row(key, label, series, unit, source, frequency="日", change_unit="pt", kind=None):
    values = [] if series is None else series.dropna().astype(float).tolist()
    last = values[-1] if values else None
    def diff(periods):
        value = change(values, periods)
        return to_bps(value) if value is not None and change_unit == "bps" else value
    result = {"key": key, "label": label, "unit": unit, "source": source, "frequency": frequency,
            "available": last is not None, "last": None if last is None else round(last, 3),
            "change_unit": change_unit,
            "changes": {"today": diff(1), "d1": diff(1), "d5": diff(5), "d20": diff(20)},
            "as_of": None if series is None or series.dropna().empty else str(series.dropna().index[-1].date())}
    return dict(result, **judgment(values, kind))


def ratio_series(numerator, denominator):
    """依共同交易日對齊兩個序列，回傳分子／分母比值。"""
    if numerator is None or denominator is None:
        return pd.Series(dtype=float)
    aligned = pd.concat([numerator.rename("numerator"), denominator.rename("denominator")], axis=1).dropna()
    aligned = aligned[aligned["denominator"] != 0]
    return (aligned["numerator"] / aligned["denominator"]).round(3)


def vix9d_row(vix9d, vix):
    """VIX9D 列以短端期限結構倒掛覆蓋自身波動判讀。"""
    result = row("vix9d", "VIX9D", vix9d, "pt", "Yahoo Finance ^VIX9D", kind="vix")
    term = ratio_series(vix9d, vix)
    latest = None if term.empty else round(float(term.iloc[-1]), 3)
    result["term_structure_ratio"] = latest
    if latest is None:
        return result
    if latest > 1:
        return dict(result, score=-2, signal="避險升溫", note="VIX9D/VIX %.3f > 1，短期避險升溫" % latest)
    return dict(result, note="%s；VIX9D/VIX %.3f" % (result["note"], latest))


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
    if isinstance(values, pd.DataFrame):
        asset_values = values["asset"].tolist()
        benchmark_values = values["benchmark"].tolist()
        judgment_values = [relative_return(asset_values[:i + 1], benchmark_values[:i + 1], 5)
                           for i in range(5, len(values))]
    else:
        judgment_values = []
    result = {"key": symbol.lower() + "_spy", "label": symbol + " / SPY", "unit": "%pt",
            "source": "Yahoo Finance", "frequency": "日", "available": isinstance(values, pd.DataFrame) and len(values) > 1,
            "last": rel(1), "change_unit": "%pt", "changes": {"today": rel(1), "d1": rel(1), "d5": rel(5), "d20": rel(20)},
            "as_of": as_of, "note": "相對 SPY 報酬"}
    return dict(result, **judgment(judgment_values, "relative"))


def build():
    bei, hy, ig, y2, y10, y30, tips = (fred_series(x) for x in (
        "T10YIE", "BAMLH0A0HYM2", "BAMLC0A0CM", "DGS2", "DGS10", "DGS30", "DFII10"))
    prices = P.fetch_yf_close(["^MOVE", "^VIX", "^VIX3M", "^VIX9D", "SPY", "RSP", "IWM", "KRE"], START)
    col = lambda name: P._col(prices, name)
    groups = [
        {"title": "利率／通膨", "rows": [
            row("y2", "2Y 名目利率", y2, "%", "FRED DGS2", change_unit="bps", kind="yield"),
            row("y10", "10Y 名目利率", y10, "%", "FRED DGS10", change_unit="bps", kind="yield"),
            row("y30", "30Y 名目利率", y30, "%", "FRED DGS30", change_unit="bps", kind="yield"),
            row("tips10", "10Y TIPS", tips, "%", "FRED DFII10", change_unit="bps", kind="tips"),
            row("bei10", "10Y BEI", bei, "%", "FRED T10YIE", change_unit="bps", kind="bei"),
            row("hy_oas", "HY OAS", hy, "%", "FRED BAMLH0A0HYM2", change_unit="bps", kind="oas"),
            row("ig_oas", "IG OAS", ig, "%", "FRED BAMLC0A0CM", change_unit="bps", kind="oas")]},
        {"title": "信用／波動", "rows": [row("move", "MOVE", col("^MOVE"), "pt", "Yahoo Finance ^MOVE", kind="move"), row("vix", "VIX", col("^VIX"), "pt", "Yahoo Finance ^VIX", kind="vix"), row("vix3m", "VIX3M", col("^VIX3M"), "pt", "Yahoo Finance ^VIX3M", kind="vix"), vix9d_row(col("^VIX9D"), col("^VIX"))]},
    ]
    spy = col("SPY")
    rel = [relative_row(sym, col(sym), spy) for sym in ("RSP", "IWM", "KRE")]
    groups.append({"title": "股票內部", "rows": rel})
    return {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "groups": groups,
            "charts": {
                "rates": {"title": "利率結構", "series": {"2Y 名目": chart_series(y2), "10Y 名目": chart_series(y10), "30Y 名目": chart_series(y30), "10Y TIPS": chart_series(tips), "10Y BEI": chart_series(bei)}},
                "risk": {"title": "波動與信用壓力", "series": {"MOVE": chart_series(col("^MOVE")), "VIX": chart_series(col("^VIX")), "VIX9D": chart_series(col("^VIX9D")), "VIX9D/VIX": chart_series(ratio_series(col("^VIX9D"), col("^VIX"))), "HY OAS": chart_series(hy)}},
                "internals": {"title": "股票內部相對強弱", "series": {"SPY": chart_series(spy), "RSP": chart_series(col("RSP")), "IWM": chart_series(col("IWM")), "KRE": chart_series(col("KRE"))}},
            }}


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("[daily-checklist] -> data/daily_checklist.json")

# -*- coding: utf-8 -*-
"""輸出 TGA 與銀行準備金的官方歷史水位；不做預測或累加。"""
import datetime as dt
import io
import json
import os
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "liquidity_forecast.json")
START = "2018-01-01"
TREASURY_REFUNDING_LATEST_URL = (
    "https://home.treasury.gov/policy-issues/financing-the-government/"
    "quarterly-refunding/most-recent-quarterly-refunding-documents"
)

# All FRED series below are quoted in millions of U.S. dollars except the daily
# ON RRP series, which is in billions and is scaled only by the forecast layer.
# WLRRAFOIAL is the H.4.1 foreign-official RRP account (the verifiable FIMA
# proxy); WLFN is deliberately not used because it is Federal Reserve notes.
FACTOR_SPECS = {
    "tga": {"series": "WTREGEN", "sign": -1, "source": "FRED WTREGEN"},
    "walcl": {"series": "WALCL", "sign": 1, "source": "FRED WALCL"},
    "rrp": {"series": "RRPONTSYD", "sign": -1, "scale": 1000, "source": "FRED RRPONTSYD"},
    "currency": {"series": "CURRCIR", "sign": -1, "source": "FRED CURRCIR"},
    "fima_other": {
        "series": "WLRRAFOIAL", "sign": -1,
        "source": "FRED WLRRAFOIAL (H.4.1 foreign official RRP)",
    },
}
FACTOR_SERIES_IDS = ("WTREGEN", "WRESBAL", "WALCL", "RRPONTSYD", "CURRCIR", "WLRRAFOIAL")


class _FinancingEstimateLinkParser(HTMLParser):
    """Find the current Treasury Financing Estimates link without a third-party parser."""

    def __init__(self):
        HTMLParser.__init__(self)
        self.href = None
        self._current_href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.href is None:
            self._current_href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or self._current_href is None:
            return
        if "financing estimates" in "".join(self._text).lower():
            self.href = self._current_href
        self._current_href = None
        self._text = []


def _read_url_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "stockview1/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def _month_end(year, month_name):
    month = dt.datetime.strptime(month_name, "%B").month
    if month == 12:
        return dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def parse_treasury_tga_targets(html):
    """Extract Treasury's official quarterly end-of-quarter cash assumptions."""
    pattern = re.compile(
        r"During\s+(?:the\s+)?([A-Z][a-z]+)\s*(?:–|-)\s*([A-Z][a-z]+)\s+(\d{4})\s+quarter"
        r".*?end-of-([A-Z][a-z]+)\s+cash\s+balance\s+of\s+\$([0-9,.]+)\s+"
        r"(billion|trillion)",
        re.IGNORECASE | re.DOTALL,
    )
    targets = []
    for _start_month, _end_month, year, target_month, amount, unit in pattern.findall(html):
        value = float(amount.replace(",", ""))
        multiplier = 1000000 if unit.lower() == "trillion" else 1000
        date = _month_end(int(year), target_month.title()).isoformat()
        targets.append({
            "date": date,
            "value": round(value * multiplier, 3),
            "source_type": "official",
            "confidence": "high",
        })
    return sorted(targets, key=lambda target: target["date"])


def _financing_estimates_url(listing_html):
    parser = _FinancingEstimateLinkParser()
    parser.feed(listing_html)
    return parser.href


def fetch_treasury_tga_targets(http_get=_read_url_text):
    """Fetch targets only from Treasury's latest Financing Estimates announcement.

    A failed document discovery or download returns no targets, so callers must
    use their model fallback rather than presenting an unverified number as
    official.
    """
    try:
        href = _financing_estimates_url(http_get(TREASURY_REFUNDING_LATEST_URL))
        if not href:
            return []
        return parse_treasury_tga_targets(http_get(urljoin(TREASURY_REFUNDING_LATEST_URL, href)))
    except Exception as exc:
        print("[liquidity-levels] Treasury TGA targets failed: %s" % exc)
        return []


def factor_status(series):
    """Return a truthful availability status; missing values are never zero-filled."""
    if not isinstance(series, pd.Series) or series.dropna().empty:
        return "missing"
    return "available"


def fetch_factor_series(series_reader=None):
    """Retrieve all Task 2 source series while retaining explicit empty failures."""
    series_reader = series_reader or fred_series
    series_map = {}
    for series_id in FACTOR_SERIES_IDS:
        try:
            series = series_reader(series_id)
        except Exception as exc:
            print("[liquidity-levels] factor %s failed: %s" % (series_id, exc))
            series = pd.Series(dtype=float)
        if not isinstance(series, pd.Series):
            series = pd.Series(dtype=float)
        series_map[series_id] = series.dropna().astype(float).sort_index()
    return series_map


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


def reserve_change(delta):
    """Return the reserve-balance change implied by each liability change once."""
    return (delta["walcl"] - delta["tga"] - delta["rrp"]
            - delta["currency"] - delta["fima_other"])


def full_liquidity_change(delta):
    """Use the same balance-sheet change equation for the liquidity proxy."""
    return reserve_change(delta)


def full_liquidity_value(levels):
    """Return the independent full-liquidity level from its five account levels."""
    return (levels["walcl"] - levels["tga"] - levels["rrp"]
            - levels["currency"] - levels["fima_other"])


def _confidence_min(*values):
    order = {"high": 2, "medium": 1, "low": 0}
    return min(values, key=lambda value: order.get(value, -1)) if values else "low"


def _factor_level(series_map, factor_id):
    spec = FACTOR_SPECS[factor_id]
    series = series_map.get(spec["series"], pd.Series(dtype=float))
    if factor_status(series) == "missing":
        return None, None
    scale = spec.get("scale", 1)
    return float(series.iloc[-1]) * scale, pd.Timestamp(series.index[-1]).strftime("%Y-%m-%d")


def _trend_change(series, target_date, scale=1):
    """Project a component's level with its available trailing trend.

    One observation has no observable trend, so its conservative projection is
    unchanged and low confidence rather than an invented cash-flow estimate.
    """
    series = series.dropna().astype(float).sort_index()
    if series.empty:
        return None, "low"
    if len(series) < 2:
        return 0.0, "low"
    history = series.iloc[-13:]
    elapsed_days = (history.index[-1] - history.index[0]).days
    future_days = (pd.Timestamp(target_date) - history.index[-1]).days
    if elapsed_days <= 0 or future_days <= 0:
        return 0.0, "medium"
    daily_changes = np.diff(history.values) / np.diff(history.index.values).astype("timedelta64[D]").astype(float)
    return float(np.median(daily_changes) * future_days * scale), "medium"


def forecast_components(series_map, tga_forecast):
    """Build one projected set of balance-sheet component levels per target date."""
    base_levels = {}
    as_of_dates = []
    for factor_id, spec in FACTOR_SPECS.items():
        level, as_of = _factor_level(series_map, factor_id)
        base_levels[factor_id] = level
        if as_of:
            as_of_dates.append(as_of)

    forecasts = []
    for tga_point in tga_forecast:
        levels = dict(base_levels)
        changes = {factor_id: None for factor_id in FACTOR_SPECS}
        confidence = []
        tga_level = tga_point.get("value")
        if base_levels["tga"] is None or tga_level is None:
            levels["tga"] = None
            confidence.append("low")
        else:
            levels["tga"] = float(tga_level)
            changes["tga"] = levels["tga"] - base_levels["tga"]
            confidence.append(tga_point.get("confidence", "low"))

        factor_points = {
            "tga": {
                "value": levels["tga"], "change": changes["tga"],
                "source_type": tga_point.get("source_type", "model"),
                "confidence": tga_point.get("confidence", "low"),
            }
        }
        for factor_id, spec in FACTOR_SPECS.items():
            if factor_id == "tga":
                continue
            series = series_map.get(spec["series"], pd.Series(dtype=float))
            change, factor_confidence = _trend_change(series, tga_point["date"], spec.get("scale", 1))
            if base_levels[factor_id] is None or change is None:
                levels[factor_id] = None
                changes[factor_id] = None
            else:
                changes[factor_id] = change
                levels[factor_id] = base_levels[factor_id] + change
            confidence.append(factor_confidence)
            factor_points[factor_id] = {
                "value": levels[factor_id], "change": changes[factor_id],
                "source_type": "model", "confidence": factor_confidence,
            }

        forecasts.append({
            "date": tga_point["date"], "as_of": min(as_of_dates) if as_of_dates else None,
            "levels": levels, "base_levels": base_levels, "change": changes,
            "factors": factor_points, "source_type": "model",
            "confidence": _confidence_min(*confidence),
        })
    return forecasts


def _derived_forecast_point(component, value, change):
    return {
        "date": component["date"],
        "value": None if value is None else round(float(value), 3),
        "change": None if change is None else round(float(change), 3),
        "source_type": "model", "confidence": component["confidence"],
        "as_of": component["as_of"],
    }


def forecast_reserves(series_map, component_forecasts):
    """Forecast reserve levels without using the full-liquidity level as an input."""
    reserves = series_map.get("WRESBAL", pd.Series(dtype=float))
    if factor_status(reserves) == "missing":
        return [_derived_forecast_point(component, None, None) for component in component_forecasts]
    latest = float(reserves.iloc[-1])
    forecasts = []
    for component in component_forecasts:
        changes = component["change"]
        if any(changes[factor_id] is None for factor_id in FACTOR_SPECS):
            forecasts.append(_derived_forecast_point(component, None, None))
            continue
        change = reserve_change(changes)
        forecasts.append(_derived_forecast_point(component, latest + change, change))
    return forecasts


def forecast_full_liquidity(component_forecasts):
    """Forecast the liquidity proxy directly from account levels, never reserves."""
    forecasts = []
    for component in component_forecasts:
        levels = component["levels"]
        changes = component["change"]
        if any(levels[factor_id] is None for factor_id in FACTOR_SPECS):
            forecasts.append(_derived_forecast_point(component, None, None))
            continue
        forecasts.append(_derived_forecast_point(
            component, full_liquidity_value(levels), full_liquidity_change(changes)))
    return forecasts


def forecast_factor_blocks(component_forecasts):
    """Expose each component forecast without turning factor cards into another sum."""
    blocks = {factor_id: [] for factor_id in FACTOR_SPECS}
    for component in component_forecasts:
        for factor_id, factor in component["factors"].items():
            blocks[factor_id].append({
                "date": component["date"], "value": factor["value"],
                "change": factor["change"], "source_type": factor["source_type"],
                "confidence": factor["confidence"], "as_of": component["as_of"],
            })
    return [
        {"id": factor_id, "name": name,
         "forecast": blocks.get(factor_id, [])}
        if factor_id in blocks else
        {"id": factor_id, "name": name, "forecast": []}
        for factor_id, name in FACTOR_CONTRACT
    ]


def _full_liquidity_actual(series_map):
    """Expose the latest complete balance-sheet proxy using the forecast account set."""
    levels = {}
    as_of_dates = []
    for factor_id in FACTOR_SPECS:
        level, as_of = _factor_level(series_map, factor_id)
        if level is None:
            return []
        levels[factor_id] = level
        as_of_dates.append(as_of)
    as_of = min(as_of_dates)
    return [{"date": as_of, "value": round(full_liquidity_value(levels), 3),
             "source_type": "actual", "confidence": "high", "as_of": as_of}]


def build_terminal_forecast(series_map, tga_targets, generated_at=None):
    """Build independent TGA, reserve and full-liquidity terminal levels."""
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

    component_forecasts = forecast_components(series_map, tga_forecast)

    def line(series_key):
        series = series_map.get(series_key, pd.Series(dtype=float))
        return {"actual": _points(series), "forecast": []}

    tga = line("WTREGEN")
    tga["forecast"] = tga_forecast
    reserves = line("WRESBAL")
    reserves["forecast"] = forecast_reserves(series_map, component_forecasts)
    full_liquidity = {
        "actual": _full_liquidity_actual(series_map),
        "forecast": forecast_full_liquidity(component_forecasts),
    }
    return {
        "status": "ok",
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tga": tga,
        "reserves": reserves,
        "full_liquidity": full_liquidity,
        "factors": forecast_factor_blocks(component_forecasts),
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

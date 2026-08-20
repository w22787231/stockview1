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

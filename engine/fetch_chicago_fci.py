# -*- coding: utf-8 -*-
"""Chicago Fed NFCI + S&P 500 series for StockView."""
import csv
import datetime as _dt
import io
import json
import os
import urllib.parse
import urllib.request

try:
    import yfinance as yf
except Exception:
    yf = None

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI"
SP500_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"


def _num(x):
    try:
        if x in (None, "", "."):
            return None
        return float(x)
    except Exception:
        return None


def parse_fred_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for r in rows:
        date = (r.get("observation_date") or r.get("DATE") or r.get("Date") or "").strip()
        val = _num(r.get("NFCI"))
        if date and val is not None:
            out.append({"date": date, "nfci": round(val, 4)})
    out.sort(key=lambda r: r["date"])
    return out


def parse_fred_api(raw):
    data = json.loads(raw)
    out = []
    for r in data.get("observations") or []:
        val = _num(r.get("value"))
        date = (r.get("date") or "").strip()
        if date and val is not None:
            out.append({"date": date, "nfci": round(val, 4)})
    out.sort(key=lambda r: r["date"])
    return out


def parse_sp500_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    out = {}
    for r in rows:
        date = (r.get("observation_date") or r.get("DATE") or r.get("Date") or "").strip()
        val = _num(r.get("SP500"))
        if date and val is not None:
            out[date] = round(val, 2)
    return out


def parse_sp500_api(raw):
    data = json.loads(raw)
    out = {}
    for r in data.get("observations") or []:
        date = (r.get("date") or "").strip()
        val = _num(r.get("value"))
        if date and val is not None:
            out[date] = round(val, 2)
    return out


def fetch_nfci(start="2015-01-01"):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        qs = urllib.parse.urlencode({
            "series_id": "NFCI",
            "api_key": key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        })
        raw = urllib.request.urlopen(urllib.request.Request(
            FRED_API + "?" + qs, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
        ).read().decode("utf-8")
        recs = parse_fred_api(raw)
        if recs:
            return recs, "FRED API NFCI"

    raw = urllib.request.urlopen(urllib.request.Request(
        FRED_CSV, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
    ).read().decode("utf-8-sig")
    recs = [r for r in parse_fred_csv(raw) if r["date"] >= start]
    return recs, "FRED NFCI csv"


def fetch_sp500_fred(start):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        qs = urllib.parse.urlencode({
            "series_id": "SP500",
            "api_key": key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        })
        raw = urllib.request.urlopen(urllib.request.Request(
            FRED_API + "?" + qs, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
        ).read().decode("utf-8")
        data = parse_sp500_api(raw)
        if data:
            return data, "FRED SP500"

    raw = urllib.request.urlopen(urllib.request.Request(
        SP500_CSV, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
    ).read().decode("utf-8-sig")
    data = {k: v for k, v in parse_sp500_csv(raw).items() if k >= start}
    return data, "FRED SP500 csv"


def fetch_sp500_yahoo(start):
    if yf is None:
        raise RuntimeError("missing yfinance")
    df = yf.download("^GSPC", start=start, progress=False, threads=False, auto_adjust=False)
    if df is None or getattr(df, "empty", True):
        return {}
    close = df["Close"]
    if getattr(close, "ndim", 1) > 1:
        close = close.iloc[:, 0]
    out = {}
    for idx, val in close.dropna().items():
        out[idx.strftime("%Y-%m-%d")] = round(float(val), 2)
    return out, "Yahoo Finance ^GSPC"


def fetch_sp500(start):
    try:
        data, src = fetch_sp500_fred(start)
        if data:
            return data, src
    except Exception:
        pass
    return fetch_sp500_yahoo(start)


def align_ffill(dates, values_by_date):
    keys = sorted(values_by_date)
    out, j, last = [], 0, None
    for d in dates:
        while j < len(keys) and keys[j] <= d:
            last = values_by_date[keys[j]]
            j += 1
        out.append(last)
    return out


def build_json(nfci_recs, sp500_map, source, keep=560):
    nfci_recs = nfci_recs[-keep:]
    dates = [r["date"] for r in nfci_recs]
    nfci = [r["nfci"] for r in nfci_recs]
    sp500 = align_ffill(dates, sp500_map)
    cur = nfci[-1] if nfci else None
    prev = nfci[-2] if len(nfci) >= 2 else None
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "series_id": "NFCI",
        "label": "Chicago Fed National Financial Conditions Index",
        "as_of": dates[-1] if dates else None,
        "current": cur,
        "weekly_change": round(cur - prev, 4) if cur is not None and prev is not None else None,
        "windows": ["3m", "6m", "1y", "3y", "5y", "10y"],
        "default_window": "1y",
        "series": {"dates": dates, "nfci": nfci, "sp500": sp500},
        "note": "NFCI>0 表示金融狀況比歷史平均更緊，NFCI<0 表示更寬鬆。",
    }


def build_live():
    start = (_dt.date.today() - _dt.timedelta(days=365 * 11)).isoformat()
    nfci, src = fetch_nfci(start)
    if not nfci:
        raise RuntimeError("missing NFCI")
    spx, spx_src = fetch_sp500(nfci[0]["date"])
    return build_json(nfci, spx, src + " + " + spx_src)

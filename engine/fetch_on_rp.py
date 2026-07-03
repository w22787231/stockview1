# -*- coding: utf-8 -*-
"""Federal Reserve overnight reverse repo operations (ON RRP)."""
import csv
import datetime as _dt
import io
import json
import os
import urllib.parse
import urllib.request

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RRPONTSYD"


def _num(x):
    try:
        if x in (None, "", "."):
            return None
        return float(x)
    except Exception:
        return None


def moving_avg(vals, n):
    out = []
    for i in range(len(vals)):
        if i + 1 < n:
            out.append(None)
            continue
        win = [v for v in vals[i + 1 - n:i + 1] if v is not None]
        out.append(round(sum(win) / len(win), 3) if win else None)
    return out


def parse_fred_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for r in rows:
        date = (r.get("observation_date") or r.get("DATE") or r.get("Date") or "").strip()
        val = _num(r.get("RRPONTSYD"))
        if date and val is not None:
            out.append({"date": date, "value": round(val, 3)})
    out.sort(key=lambda r: r["date"])
    return out


def parse_fred_api(raw):
    data = json.loads(raw)
    out = []
    for r in data.get("observations") or []:
        date = (r.get("date") or "").strip()
        val = _num(r.get("value"))
        if date and val is not None:
            out.append({"date": date, "value": round(val, 3)})
    out.sort(key=lambda r: r["date"])
    return out


def fetch_on_rp(start="2015-01-01"):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        qs = urllib.parse.urlencode({
            "series_id": "RRPONTSYD",
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
            return recs, "FRED API RRPONTSYD"

    raw = urllib.request.urlopen(urllib.request.Request(
        FRED_CSV, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
    ).read().decode("utf-8-sig")
    recs = [r for r in parse_fred_csv(raw) if r["date"] >= start]
    return recs, "FRED RRPONTSYD csv"


def build_json(recs, source, keep=2800):
    recs = recs[-keep:]
    dates = [r["date"] for r in recs]
    vals = [r["value"] for r in recs]
    ma20 = moving_avg(vals, 20)
    ma60 = moving_avg(vals, 60)
    cur = vals[-1] if vals else None
    prev = vals[-2] if len(vals) >= 2 else None
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "series_id": "RRPONTSYD",
        "label": "Overnight Reverse Repurchase Agreements",
        "as_of": dates[-1] if dates else None,
        "current": cur,
        "daily_change": round(cur - prev, 3) if cur is not None and prev is not None else None,
        "ma20_last": ma20[-1] if ma20 else None,
        "ma60_last": ma60[-1] if ma60 else None,
        "unit": "十億美元",
        "windows": ["3m", "6m", "1y", "3y", "5y", "10y"],
        "default_window": "1y",
        "series": {"dates": dates, "value": vals, "ma20": ma20, "ma60": ma60},
        "note": "ON RRP 上升通常代表資金停泊在聯準會、流動性被吸收；下降通常代表資金釋回市場體系。",
    }


def build_live():
    start = (_dt.date.today() - _dt.timedelta(days=365 * 11)).isoformat()
    recs, src = fetch_on_rp(start)
    if not recs:
        raise RuntimeError("missing RRPONTSYD")
    return build_json(recs, src)

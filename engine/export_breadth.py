# -*- coding: utf-8 -*-
"""Advance/Decline breadth export for StockView macro page.

Outputs ../data/breadth.json with a US advance/decline breadth section.
US uses the existing S&P 500 pool and builds a 10-year A/D line.
"""
import datetime as _dt
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import warnings
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    import adr_screen as eng
except Exception:
    yf = None
    eng = None

DATA_DIR = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA_DIR, "breadth.json")


def _num(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace("--", "")
    s = s.replace("X", "").replace("除權息", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _round(x, n=2):
    try:
        return round(float(x), n)
    except Exception:
        return None


def _safe_ratio(a, b):
    return None if not b else round(a / b, 2)


def _with_core_fields(label, dates, ad_diff, index_series, today_counts, source, notes=None):
    ad_line = []
    cur = 0
    for v in ad_diff:
        cur += int(v or 0)
        ad_line.append(cur)
    divs = _detect_divergences(dates, index_series, ad_line)
    adv = today_counts.get("advancers", 0)
    dec = today_counts.get("decliners", 0)
    unch = today_counts.get("unchanged", 0)
    return {
        "label": label,
        "date": dates[-1] if dates else None,
        "advancers": adv,
        "decliners": dec,
        "unchanged": unch,
        "ad_diff": adv - dec,
        "ad_ratio": _safe_ratio(adv, dec),
        "dates": dates,
        "ad_diffs": ad_diff,
        "ad_line": ad_line,
        "index_series": index_series,
        "divergences": divs,
        "source": source,
        "notes": notes or "",
    }


def _detect_divergences(dates, index_series, ad_line, window=20):
    points = []
    for date, idx, breadth in zip(dates, index_series, ad_line):
        idx = _num(idx)
        breadth = _num(breadth)
        if idx is not None and breadth is not None:
            points.append((date, idx, breadth))
    if len(points) < window:
        return [{"type": "pending", "date": dates[-1] if dates else None,
                 "message": "資料累積中"}]
    recent = points[-window:]
    idx = [p[1] for p in recent]
    breadth = [p[2] for p in recent]
    latest_date = recent[-1][0]
    latest_i = idx[-1]
    latest_b = breadth[-1]
    prev_idx_hi = max(idx[:-1])
    prev_idx_lo = min(idx[:-1])
    prev_b_hi = max(breadth[:-1])
    prev_b_lo = min(breadth[:-1])
    out = []
    if latest_i >= prev_idx_hi and latest_b < prev_b_hi:
        out.append({"type": "bearish", "date": latest_date,
                    "message": "頂背離：指數創高，但騰落線未同步創高"})
    if latest_i <= prev_idx_lo and latest_b > prev_b_lo:
        out.append({"type": "bullish", "date": latest_date,
                    "message": "底背離：指數創低，但騰落線未同步創低"})
    return out


def _close_series(df, sym=None):
    if df is None or df.empty:
        return None
    cols = getattr(df, "columns", None)
    if getattr(cols, "nlevels", 1) > 1:
        try:
            if "Close" in cols.get_level_values(0):
                close = df["Close"]
            else:
                close = df.xs("Close", axis=1, level=-1)
            if getattr(close, "ndim", 1) == 1:
                return close
            if sym and sym in close.columns:
                return close[sym]
            return close.iloc[:, 0]
        except Exception:
            return None
    if "Close" not in df:
        return None
    return df["Close"]


def _download_us(symbols, period="10y"):
    if yf is None:
        return None
    return yf.download(symbols, period=period, interval="1d", group_by="ticker",
                       progress=False, auto_adjust=False, threads=True)


def _us_close_map(df, symbols):
    out = {}
    if df is None or df.empty or getattr(df.columns, "nlevels", 1) <= 1:
        return out
    for sym in symbols:
        try:
            sub = eng._sub(df, symbols, sym) if eng else df[sym].dropna()
            if "Close" not in sub or len(sub) < 2:
                continue
            closes = sub["Close"].dropna()
            if len(closes) >= 2:
                out[sym] = {dt.strftime("%Y-%m-%d"): float(val) for dt, val in closes.items()}
        except Exception:
            continue
    return out


def build_us(pool="sp500"):
    symbols = eng.load_pool(pool) if eng else _load_pool(pool)
    symbols = symbols or []
    df = _download_us(symbols)
    if df is None:
        return _with_core_fields("美股騰落", [], [], [], {}, "yfinance S&P500 pool",
                                 "本機缺 yfinance；GitHub Actions 會產生完整美股資料")
    idx = yf.download("^GSPC", period="10y", interval="1d", progress=False, auto_adjust=False)
    dates = []
    diffs = []
    adv_series = []
    dec_series = []
    unch_series = []
    idx_series = []
    index_by_date = {}
    closes = _close_series(idx, "^GSPC")
    if closes is not None:
        try:
            for dt, val in closes.dropna().items():
                index_by_date[dt.strftime("%Y-%m-%d")] = _round(val, 2)
        except Exception:
            pass
    close_by_symbol = _us_close_map(df, symbols)
    if not close_by_symbol:
        return _with_core_fields("美股騰落", [], [], [], {}, "yfinance S&P500 pool")

    all_dates = sorted({d.strftime("%Y-%m-%d") for d in df.index})
    prev_by_symbol = {}
    for day in all_dates:
        a = d = u = 0
        for sym, closes in close_by_symbol.items():
            try:
                if day not in closes:
                    continue
                close = closes[day]
                prev = prev_by_symbol.get(sym)
                if prev is not None:
                    if close > prev:
                        a += 1
                    elif close < prev:
                        d += 1
                    else:
                        u += 1
                prev_by_symbol[sym] = close
            except Exception:
                continue
        if a + d + u:
            dates.append(day)
            adv_series.append(a)
            dec_series.append(d)
            unch_series.append(u)
            diffs.append(a - d)
            idx_series.append(index_by_date.get(day))
    counts = {
        "advancers": adv_series[-1] if adv_series else 0,
        "decliners": dec_series[-1] if dec_series else 0,
        "unchanged": unch_series[-1] if unch_series else 0,
    }
    return _with_core_fields(
        "美股騰落",
        dates,
        diffs,
        idx_series,
        counts,
        "yfinance S&P500 pool + ^GSPC",
        "美股使用目前 sp500 股池回推10年，不額外掃描全市場；歷史資料有存活者偏差",
    )


def _load_pool(pool):
    path = os.path.join(HERE, "universe", f"{pool}.txt")
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def build():
    payload = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "us": build_us(),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[breadth] -> data/breadth.json",
          "US", payload["us"].get("advancers"), "/", payload["us"].get("decliners"),
          "days", len(payload["us"].get("dates") or []))


if __name__ == "__main__":
    build()

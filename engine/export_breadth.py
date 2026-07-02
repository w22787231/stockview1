# -*- coding: utf-8 -*-
"""Advance/Decline breadth export for StockView macro page.

Outputs ../data/breadth.json with separate Taiwan and US sections.
Taiwan uses official TWSE/TPEx daily close rows and appends to the live file.
US uses the existing S&P 500 pool and builds a 60-session A/D line.
"""
import datetime as _dt
import io
import json
import os
import re
import ssl
import sys
import urllib.request

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
LIVE_URL = "https://stockview1.pages.dev/data/breadth.json"
UA = {"User-Agent": "Mozilla/5.0"}

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


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


def _date_iso_tw(s):
    """ROC yyyMMdd or yyyyMMdd -> yyyy-mm-dd."""
    s = str(s or "").strip()
    if len(s) == 7 and s.isdigit():
        y = int(s[:3]) + 1911
        return f"{y:04d}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


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
    if len(dates) < window or len(index_series) < window or len(ad_line) < window:
        return [{"type": "pending", "date": dates[-1] if dates else None,
                 "message": "資料累積中"}]
    idx = index_series[-window:]
    breadth = ad_line[-window:]
    latest_i = idx[-1]
    latest_b = breadth[-1]
    prev_idx_hi = max(idx[:-1])
    prev_idx_lo = min(idx[:-1])
    prev_b_hi = max(breadth[:-1])
    prev_b_lo = min(breadth[:-1])
    out = []
    if latest_i is not None and latest_b is not None:
        if latest_i >= prev_idx_hi and latest_b < prev_b_hi:
            out.append({"type": "bearish", "date": dates[-1],
                        "message": "頂背離：指數創高，但騰落線未同步創高"})
        if latest_i <= prev_idx_lo and latest_b > prev_b_lo:
            out.append({"type": "bullish", "date": dates[-1],
                        "message": "底背離：指數創低，但騰落線未同步創低"})
    return out


def _load_live():
    try:
        return _get_json(LIVE_URL, timeout=12)
    except Exception:
        return {}


def _tw_rows():
    rows = []
    try:
        for r in _get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=25):
            code = str(r.get("Code") or r.get("證券代號") or "").strip()
            if re.fullmatch(r"\d{4}", code):
                rows.append({
                    "date": r.get("Date") or r.get("日期"),
                    "code": code,
                    "close": _num(r.get("ClosingPrice") or r.get("收盤價")),
                    "change": _num(r.get("Change") or r.get("漲跌價差")),
                })
    except Exception as e:
        print("[breadth] TWSE failed:", e)
    try:
        for r in _get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", timeout=25):
            code = str(r.get("SecuritiesCompanyCode") or "").strip()
            if re.fullmatch(r"\d{4}", code):
                rows.append({
                    "date": r.get("Date"),
                    "code": code,
                    "close": _num(r.get("Close")),
                    "change": _num(r.get("Change")),
                })
    except Exception as e:
        print("[breadth] TPEx failed:", e)
    return [r for r in rows if r["close"] is not None and r["change"] is not None]


def _latest_index(sym):
    if yf is None:
        return None
    try:
        df = yf.download(sym, period="10d", interval="1d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        return _round(float(df["Close"].dropna().iloc[-1]), 2)
    except Exception:
        return None


def build_tw(live):
    rows = _tw_rows()
    counts = {"advancers": 0, "decliners": 0, "unchanged": 0}
    for r in rows:
        ch = r["change"]
        if ch > 0:
            counts["advancers"] += 1
        elif ch < 0:
            counts["decliners"] += 1
        else:
            counts["unchanged"] += 1
    date = _date_iso_tw(next((r["date"] for r in rows if r.get("date")), None)) or _dt.date.today().isoformat()
    prev = (live or {}).get("tw") or {}
    dates = list(prev.get("dates") or [])
    diffs = list(prev.get("ad_diffs") or [])
    idxs = list(prev.get("index_series") or [])
    if dates and dates[-1] == date:
        dates = dates[:-1]; diffs = diffs[:-1]; idxs = idxs[:-1]
    dates.append(date)
    diffs.append(counts["advancers"] - counts["decliners"])
    idxs.append(_latest_index("^TWII") or (idxs[-1] if idxs else None))
    return _with_core_fields(
        "台股騰落",
        dates[-90:],
        diffs[-90:],
        idxs[-90:],
        counts,
        "TWSE STOCK_DAY_ALL + TPEx daily close quotes",
        "上市與上櫃4碼股票；歷史線由每日部署逐步累積",
    )


def _download_us(symbols):
    if yf is None:
        return None
    return yf.download(symbols, period="4mo", interval="1d", group_by="ticker",
                       progress=False, auto_adjust=False, threads=True)


def build_us(pool="sp500", limit=60):
    symbols = eng.load_pool(pool) if eng else _load_pool(pool)
    symbols = symbols or []
    df = _download_us(symbols)
    if df is None:
        return _with_core_fields("美股騰落", [], [], [], {}, "yfinance S&P500 pool",
                                 "本機缺 yfinance；GitHub Actions 會產生完整美股資料")
    idx = yf.download("^GSPC", period="4mo", interval="1d", progress=False, auto_adjust=False)
    dates = []
    diffs = []
    adv_series = []
    dec_series = []
    unch_series = []
    idx_series = []
    index_by_date = {}
    try:
        for dt, row in idx.dropna().iterrows():
            index_by_date[dt.strftime("%Y-%m-%d")] = _round(row["Close"], 2)
    except Exception:
        pass
    if getattr(df.columns, "nlevels", 1) <= 1:
        return _with_core_fields("美股騰落", [], [], [], {}, "yfinance S&P500 pool")

    all_dates = sorted({d.strftime("%Y-%m-%d") for d in df.index})
    for day in all_dates[-limit:]:
        a = d = u = 0
        for sym in symbols:
            try:
                sub = eng._sub(df, symbols, sym).dropna()
                if len(sub) < 2:
                    continue
                sub_dates = [x.strftime("%Y-%m-%d") for x in sub.index]
                if day not in sub_dates:
                    continue
                pos = sub_dates.index(day)
                if pos <= 0:
                    continue
                close = float(sub["Close"].iloc[pos])
                prev = float(sub["Close"].iloc[pos - 1])
                if close > prev:
                    a += 1
                elif close < prev:
                    d += 1
                else:
                    u += 1
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
        "美股使用既有 sp500 股池，不額外掃描全市場",
    )


def _load_pool(pool):
    path = os.path.join(HERE, "universe", f"{pool}.txt")
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def build():
    live = _load_live()
    payload = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tw": build_tw(live),
        "us": build_us(),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[breadth] -> data/breadth.json",
          "TW", payload["tw"].get("advancers"), "/", payload["tw"].get("decliners"),
          "US", payload["us"].get("advancers"), "/", payload["us"].get("decliners"))


if __name__ == "__main__":
    build()

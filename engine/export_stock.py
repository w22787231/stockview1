# -*- coding: utf-8 -*-
"""個股詳情匯出：為指定代號產生 K線(1年OHLC) + 基本面評語 + 財務三表。
輸出 ../data/stock/<SYM>.json（檔名把 . 換成 _，例 2330.TW -> 2330_TW.json）。

用法:
  python export_stock.py NVDA MRVL 2330.TW      指定代號
  python export_stock.py --from-pool ndx100 30  某池主表 Top N（依現有引擎排序）
"""
import sys, os, io, json, math, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import adr_screen as eng

OUT_DIR = os.path.join(HERE, "..", "data", "stock")


def _safe(x):
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


def _fname(sym):
    return sym.replace(".", "_").upper() + ".json"


def candles(tk):
    """1年日K → list of {t,o,h,l,c,v} + MA20/MA60。"""
    h = tk.history(period="1y", interval="1d", auto_adjust=False)
    if h is None or h.empty:
        return [], {}
    closes = list(h["Close"])
    out = []
    for idx, row in h.iterrows():
        out.append({
            "t": idx.strftime("%Y-%m-%d"),
            "o": _safe(row["Open"]), "h": _safe(row["High"]),
            "l": _safe(row["Low"]), "c": _safe(row["Close"]),
            "v": _safe(row["Volume"]),
        })

    def ma(n):
        res = []
        for i in range(len(closes)):
            if i + 1 < n:
                continue
            window = closes[i + 1 - n:i + 1]
            res.append({"t": out[i]["t"], "v": _safe(sum(window) / n)})
        return res

    return out, {"ma20": ma(20), "ma60": ma(60)}


def fundamentals(info):
    """從 yfinance .info 抽關鍵基本面 + 規則式評語。"""
    g = lambda k: info.get(k)
    pe = _safe(g("trailingPE"))
    rev_g = _safe(g("revenueGrowth"))
    earn_g = _safe(g("earningsGrowth"))
    roe = _safe(g("returnOnEquity"))
    pm = _safe(g("profitMargins"))
    de = _safe(g("debtToEquity"))
    fcf = _safe(g("freeCashflow"))
    metrics = {
        "name": g("longName") or g("shortName"),
        "sector": g("sector"), "industry": g("industry"),
        "price": _safe(g("currentPrice")) or _safe(g("regularMarketPrice")),
        "mktcap": _safe(g("marketCap")),
        "pe": pe, "forwardPe": _safe(g("forwardPE")),
        "ps": _safe(g("priceToSalesTrailing12Months")),
        "pb": _safe(g("priceToBook")),
        "roe": roe, "profit_margin": pm, "rev_growth": rev_g,
        "earn_growth": earn_g, "debt_to_equity": de,
        "fcf": fcf, "div_yield": _safe(g("dividendYield")),
        "high52": _safe(g("fiftyTwoWeekHigh")), "low52": _safe(g("fiftyTwoWeekLow")),
        "ma50": _safe(g("fiftyDayAverage")), "ma200": _safe(g("twoHundredDayAverage")),
    }
    notes = []

    def add(tag, level, text):
        notes.append({"tag": tag, "level": level, "text": text})

    if pe is not None:
        if pe > 35:
            add("估值", "warn", f"PE {pe:.1f}，估值偏高，需要對應的成長性支撐")
        elif pe < 12:
            add("估值", "good", f"PE {pe:.1f}，估值偏低")
        else:
            add("估值", "mid", f"PE {pe:.1f}，估值合理")
    if rev_g is not None:
        p = rev_g * 100
        if p >= 15:
            add("營收", "good", f"年增 {p:+.1f}%，成長強勁")
        elif p >= 3:
            add("營收", "mid", f"年增 {p:+.1f}%，成長緩慢")
        else:
            add("營收", "warn", f"年增 {p:+.1f}%，成長停滯/衰退")
    if earn_g is not None:
        p = earn_g * 100
        if p >= 15:
            add("獲利", "good", f"年增 {p:+.1f}%，獲利強勁")
        elif p >= 0:
            add("獲利", "mid", f"年增 {p:+.1f}%，獲利平穩")
        else:
            add("獲利", "warn", f"年增 {p:+.1f}%，獲利衰退")
    if pm is not None:
        p = pm * 100
        if p >= 20:
            add("利潤率", "good", f"淨利率 {p:.1f}%，獲利能力強")
        elif p >= 8:
            add("利潤率", "mid", f"淨利率 {p:.1f}%，中等")
        else:
            add("利潤率", "warn", f"淨利率 {p:.1f}%，偏薄")
    if roe is not None:
        p = roe * 100
        if p >= 15:
            add("ROE", "good", f"ROE {p:.1f}%，資本運用佳")
        elif p >= 8:
            add("ROE", "mid", f"ROE {p:.1f}%，中等")
        else:
            add("ROE", "warn", f"ROE {p:.1f}%，偏低")
    if de is not None:
        if de < 50:
            add("負債", "good", f"負債/權益 {de:.0f}%，財務穩健")
        elif de < 120:
            add("負債", "mid", f"負債/權益 {de:.0f}%，中等")
        else:
            add("負債", "warn", f"負債/權益 {de:.0f}%，槓桿偏高")
    if fcf is not None:
        if fcf > 0:
            add("現金流", "good", "自由現金流為正，財務健康")
        else:
            add("現金流", "warn", "自由現金流為負，留意燒錢")
    score = sum(1 for n in notes if n["level"] == "good") - sum(1 for n in notes if n["level"] == "warn")
    overall = "強" if score >= 3 else ("中" if score >= -1 else "弱")
    return metrics, notes, overall


def statements(tk):
    """財務三表(最近最多 4 期)。"""
    def grab(df, rows_keep):
        if df is None or getattr(df, "empty", True):
            return None
        cols = [c.strftime("%Y-%m") if hasattr(c, "strftime") else str(c) for c in df.columns][:4]
        out = {"periods": cols, "rows": []}
        for label in rows_keep:
            if label in df.index:
                vals = [_safe(v) for v in list(df.loc[label])[:4]]
                out["rows"].append({"label": label, "vals": vals})
        return out if out["rows"] else None

    inc = grab(getattr(tk, "financials", None),
               ["Total Revenue", "Gross Profit", "Operating Income", "Net Income", "Diluted EPS"])
    bal = grab(getattr(tk, "balance_sheet", None),
               ["Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity",
                "Cash And Cash Equivalents", "Total Debt"])
    cf = grab(getattr(tk, "cashflow", None),
              ["Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow", "Free Cash Flow"])
    return {"income": inc, "balance": bal, "cashflow": cf}


def export_one(sym):
    tk = yf.Ticker(sym)
    try:
        info = tk.info or {}
    except Exception:
        info = {}
    cdl, mas = candles(tk)
    if not cdl:
        return False, "no price"
    metrics, notes, overall = fundamentals(info)
    stmts = statements(tk)
    nm = eng._TW_NAMES.get(sym.upper())
    payload = {
        "sym": sym.upper(), "name_zh": nm,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance",
        "metrics": metrics, "notes": notes, "overall": overall,
        "candles": cdl, "ma": mas, "statements": stmts,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUT_DIR, _fname(sym)), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return True, f"{len(cdl)} bars, {len(notes)} notes"


def resolve_targets(args):
    if args and args[0] == "--from-pool":
        pool = args[1]
        topn = int(args[2]) if len(args) > 2 and args[2].isdigit() else 30
        syms = eng.load_pool(pool) or []
        rows, _ = eng.compute_trend(syms)
        rows = sorted(rows, key=lambda r: r["score"], reverse=True)[:topn]
        return [r["sym"] for r in rows]
    return [a.upper() for a in args]


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python export_stock.py <SYM...> | --from-pool <pool> [N]")
        raise SystemExit(1)
    targets = resolve_targets(args)
    ok = fail = 0
    index = []
    for s in targets:
        try:
            good, msg = export_one(s)
        except Exception as e:
            good, msg = False, repr(e)[:50]
        if good:
            ok += 1
            index.append(s.upper())
            print(f"[stock] {s}  OK  ({msg})", flush=True)
        else:
            fail += 1
            print(f"[stock] {s}  FAIL  ({msg})", flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    idx_path = os.path.join(OUT_DIR, "_index.json")
    existing = []
    if os.path.exists(idx_path):
        try:
            existing = json.load(io.open(idx_path, encoding="utf-8")).get("syms", [])
        except Exception:
            existing = []
    allsyms = sorted(set(existing) | set(index))
    json.dump({"syms": allsyms,
               "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
              io.open(idx_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[stock] done. ok={ok} fail={fail}, index={len(allsyms)} syms")


if __name__ == "__main__":
    main()

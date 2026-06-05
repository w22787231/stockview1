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
import time
warnings.filterwarnings("ignore")
import yfinance as yf
import adr_screen as eng

OUT_DIR = os.path.join(HERE, "..", "data", "stock")

# 雲端(GitHub Actions)上 yfinance 的 .info 常被 Yahoo 擋 → 重試 + 判斷是否真有料。
INFO_RETRIES = 3
INFO_SLEEP = 1.2  # 秒；每檔之間/重試之間稍歇，降低被限流機率


def fetch_info(tk):
    """重試取 .info；回傳 (info, ok)。ok=有抓到實質基本面欄位。"""
    last = {}
    for attempt in range(INFO_RETRIES):
        try:
            info = tk.info or {}
        except Exception:
            info = {}
        # 判斷是否真有料：市值或 PE 或營收成長任一存在即視為成功
        if any(info.get(k) not in (None, "") for k in
               ("marketCap", "trailingPE", "forwardPE", "priceToSalesTrailing12Months", "revenueGrowth")):
            return info, True
        last = info
        if attempt < INFO_RETRIES - 1:
            time.sleep(INFO_SLEEP)
    return last, False


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
    """財務三表(季報，最近 5 季)+ 各項最新季的 YoY(與去年同季比)。"""
    def grab(df, rows_keep):
        if df is None or getattr(df, "empty", True):
            return None
        # 季報欄位通常已由新到舊排序。取最近 5 季顯示；YoY 需與 +4 季前(去年同季)比。
        all_cols = list(df.columns)
        show = all_cols[:5]
        cols = [c.strftime("%Y-%m") if hasattr(c, "strftime") else str(c) for c in show]
        out = {"periods": cols, "rows": []}
        for label in rows_keep:
            if label not in df.index:
                continue
            series = list(df.loc[label])
            vals = [_safe(v) for v in series[:5]]
            # YoY：最新季(index 0) vs 去年同季(index 4)
            yoy = None
            if len(series) >= 5:
                cur, prev = _safe(series[0]), _safe(series[4])
                if cur is not None and prev not in (None, 0):
                    yoy = (cur / prev - 1.0) * 100.0
            out["rows"].append({"label": label, "vals": vals, "yoy": _safe(yoy)})
        return out if out["rows"] else None

    inc = grab(getattr(tk, "quarterly_financials", None),
               ["Total Revenue", "Gross Profit", "Operating Income", "Net Income", "Diluted EPS"])
    bal = grab(getattr(tk, "quarterly_balance_sheet", None),
               ["Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity",
                "Cash And Cash Equivalents", "Total Debt"])
    cf = grab(getattr(tk, "quarterly_cashflow", None),
              ["Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow", "Free Cash Flow"])
    return {"income": inc, "balance": bal, "cashflow": cf, "period_type": "quarterly"}


def get_news(tk, limit=10):
    """最近新聞：標題/出版商/時間/連結。yfinance .news 結構在不同版本略異，盡量容錯。"""
    try:
        raw = tk.news or []
    except Exception:
        return []
    out = []
    for item in raw[:limit * 2]:
        # 新版 yfinance 把內容包在 item['content']；舊版直接平鋪。
        c = item.get("content", item) if isinstance(item, dict) else {}
        title = c.get("title") or item.get("title")
        if not title:
            continue
        # 連結
        link = None
        cu = c.get("canonicalUrl") or c.get("clickThroughUrl")
        if isinstance(cu, dict):
            link = cu.get("url")
        link = link or item.get("link")
        # 出版商
        prov = c.get("provider")
        publisher = (prov.get("displayName") if isinstance(prov, dict) else None) or item.get("publisher")
        # 時間
        pub = c.get("pubDate") or c.get("displayTime")
        if not pub and item.get("providerPublishTime"):
            try:
                pub = datetime.datetime.fromtimestamp(
                    item["providerPublishTime"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pub = None
        out.append({"title": title, "publisher": publisher, "time": pub, "link": link})
        if len(out) >= limit:
            break
    return out


def get_events(tk, info):
    """法說/財報相關日期 + 官方連結(讓使用者自行查看，不做 AI 解讀)。"""
    ev = {}
    # 下次/最近財報日
    try:
        cal = tk.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, list) and ed:
                ev["next_earnings"] = str(ed[0])
            elif ed:
                ev["next_earnings"] = str(ed)
    except Exception:
        pass
    if not ev.get("next_earnings") and info.get("earningsTimestamp"):
        try:
            ev["next_earnings"] = datetime.datetime.fromtimestamp(
                info["earningsTimestamp"], datetime.timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass
    # 官方連結(投資人關係/官網)
    site = info.get("website")
    ev["links"] = []
    if site:
        ev["links"].append({"label": "公司官網", "url": site})
    sym_u = info.get("symbol") or ""
    # Yahoo Finance 該股的法說/財報頁(逐字稿、簡報常在此彙整)
    if sym_u:
        ev["links"].append({"label": "Yahoo 財報/法說", "url": f"https://finance.yahoo.com/quote/{sym_u}/press-releases"})
    return ev


def export_one(sym):
    tk = yf.Ticker(sym)
    cdl, mas = candles(tk)
    if not cdl:
        return False, "no price"
    info, info_ok = fetch_info(tk)
    metrics, notes, overall = fundamentals(info)
    stmts = statements(tk)
    news = get_news(tk, 10)
    events = get_events(tk, info if isinstance(info, dict) else {})
    # has_fundamentals：前端據此決定要不要顯示指標卡/評語(避免一堆空「–」)
    has_fund = info_ok and metrics.get("mktcap") is not None
    nm = eng._TW_NAMES.get(sym.upper())
    payload = {
        "sym": sym.upper(), "name_zh": nm,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance",
        "has_fundamentals": bool(has_fund),
        "metrics": metrics, "notes": notes, "overall": overall,
        "candles": cdl, "ma": mas, "statements": stmts,
        "news": news, "events": events,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUT_DIR, _fname(sym)), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return True, f"{len(cdl)} bars, {'基本面✓' if has_fund else '基本面✗'}, {len(news)} news"


def resolve_targets(args):
    if args and args[0] == "--from-pool":
        pool = args[1]
        # 無 N 或 N=all → 全池；否則主表 Top N
        topn = None
        if len(args) > 2 and args[2].isdigit():
            topn = int(args[2])
        syms = eng.load_pool(pool) or []
        if topn is None:
            return [s.upper() for s in syms]   # 全池(不必先算 trend)
        rows, _ = eng.compute_trend(syms)
        rows = sorted(rows, key=lambda r: r["score"], reverse=True)[:topn]
        return [r["sym"] for r in rows]
    if args and args[0] == "--from-themes":
        spec = json.load(io.open(os.path.join(HERE, "universe", "tw_themes.json"), encoding="utf-8"))
        out = []
        for grp in spec["groups"]:
            for th in grp["themes"]:
                for m in th["members"]:
                    if m.get("sym"):
                        out.append(m["sym"].upper())
        return sorted(set(out))
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

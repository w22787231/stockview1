# -*- coding: utf-8 -*-
"""
資金流向資料匯出 → data/capital.json
台股(籌碼面,TWSE 免費):
  - 大盤三大法人買賣超(BFI82U,僅最新 → 以 live 舊檔累積近 60 交易日趨勢)
  - 個股外資/投信 買超/賣超 Top 榜(T86,上市,單位:張)
  - 融資融券大盤餘額 + 增減(MI_MARGN → 同樣累積趨勢)
美股(流動性/輪動,FRED + Yahoo):
  - Fed 淨流動性 = WALCL − TGA(WTREGEN) − RRP(RRPONTSYD)
  - 高收益債利差 HY spread(BAMLH0A0HYM2)
  - 貨幣市場基金規模 MMF(RMFSL,場邊資金)
  - 11 類股 ETF 輪動(1/5/20 日 + 相對 SPY)
"""
import os, re, csv, io, json, ssl, time, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "capital.json")
LIVE = "https://stockview1.pages.dev/data/capital.json"
NAMES_PATH = os.path.join(HERE, "universe", "tw_names.json")
FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url, data=None, timeout=30):
    raw = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA),
                                 timeout=timeout, context=_SSL).read()
    return raw.decode("utf-8", "ignore")


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except Exception:
        return 0.0


def load_names():
    try:
        with open(NAMES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def name_of(code, names):
    for k in (code + ".TW", code + ".TWO", code):
        if names.get(k):
            return names[k]
    return ""


# ── 找最近有資料的交易日(往前找,T86 stat=OK)──
def latest_trading_date(now):
    d = now.date()
    for _ in range(10):
        ds = d.strftime("%Y%m%d")
        try:
            j = json.loads(_get("https://www.twse.com.tw/rwd/zh/fund/T86?date=%s&selectType=ALL&response=json" % ds))
            if j.get("stat") == "OK" and j.get("data"):
                return ds, j
        except Exception:
            pass
        d -= datetime.timedelta(days=1)
    return None, None


# ── 大盤三大法人(BFI82U,單位→億元)──
def fetch_inst_market():
    try:
        j = json.loads(_get("https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json"))
    except Exception:
        return None
    if j.get("stat") != "OK":
        return None
    foreign = trust = dealer = 0.0
    for row in j.get("data", []):
        nm = row[0]; diff = _num(row[3]) / 1e8  # 元 → 億元
        if "投信" in nm:
            trust += diff
        elif "外資" in nm or "陸資" in nm:
            foreign += diff
        elif "自營" in nm:
            dealer += diff
    dd = j.get("date", "")
    date = "%s-%s-%s" % (dd[:4], dd[4:6], dd[6:8]) if len(dd) == 8 else dd
    return {"date": date, "foreign": round(foreign, 1), "trust": round(trust, 1),
            "dealer": round(dealer, 1), "total": round(foreign + trust + dealer, 1)}


# ── 個股外資/投信買賣超 Top(T86,股→張)──
def fetch_t86_ranks(t86, names, topn=15):
    rows = []
    for r in t86.get("data", []):
        code = r[0].strip()
        if not re.fullmatch(r"\d{4,6}[A-Z]?", code):
            continue
        foreign = _num(r[4]) / 1000.0    # 外陸資買賣超(不含外資自營)
        trust = _num(r[10]) / 1000.0     # 投信買賣超
        rows.append({"code": code, "name": name_of(code, names), "f": round(foreign), "t": round(trust)})

    def top(key, rev):
        s = sorted(rows, key=lambda x: x[key], reverse=rev)
        out = [x for x in s if (x[key] > 0 if rev else x[key] < 0)][:topn]
        return [{"code": x["code"], "name": x["name"], "net": x[key]} for x in out]

    return {
        "foreign_buy": top("f", True), "foreign_sell": top("f", False),
        "trust_buy": top("t", True), "trust_sell": top("t", False),
    }


# ── 融資融券大盤(MI_MARGN,Big5;位置解析:row0=融資張 row1=融券張 row2=融資金額仟元)──
def _margin_one(ds):
    try:
        j = json.loads(_get("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=%s&selectType=MS&response=json" % ds))
    except Exception:
        return None
    if j.get("stat") != "OK":
        return None
    rows = ((j.get("tables") or [{}])[0]).get("data", [])
    if len(rows) < 3:
        return None
    # 欄位:項目, 買進, 賣出, 現金(券)償還, 前日餘額, 今日餘額
    short_today = _num(rows[1][5]); short_prev = _num(rows[1][4])      # 融券張
    val_today = _num(rows[2][5]); val_prev = _num(rows[2][4])          # 融資金額(仟元)
    dd = j.get("date", ds)
    date = "%s-%s-%s" % (dd[:4], dd[4:6], dd[6:8]) if len(dd) == 8 else dd
    return {"date": date,
            "margin_bal": round(val_today / 1e5, 1),                   # 仟元 → 億元
            "margin_chg": round((val_today - val_prev) / 1e5, 1),
            "short_bal": round(short_today), "short_chg": round(short_today - short_prev)}


def fetch_margin(now):
    d = now.date()
    for _ in range(6):
        r = _margin_one(d.strftime("%Y%m%d"))
        if r:
            return r
        d -= datetime.timedelta(days=1)
    return None


# ── FRED ──
def fred(sid, limit=400):
    if not FRED_KEY:
        return []
    u = ("https://api.stlouisfed.org/fred/series/observations?series_id=%s&api_key=%s"
         "&file_type=json&sort_order=desc&limit=%d" % (sid, FRED_KEY, limit))
    for _ in range(3):
        try:
            d = json.loads(_get(u))
            obs = [(o["date"], _num(o["value"])) for o in d.get("observations", [])
                   if o.get("value") not in ("", ".", None)]
            obs.reverse()  # 舊→新
            return obs
        except Exception:
            time.sleep(1)
    return []


def fetch_fed_liquidity():
    walcl = fred("WALCL", 120)            # 週,百萬美元
    tga = dict(fred("WTREGEN", 600))      # 日,百萬
    rrp = dict(fred("RRPONTSYD", 600))    # 日,十億
    if not walcl:
        return []

    def nearest(dct, date):
        if date in dct:
            return dct[date]
        best = None
        for k in dct:
            if k <= date and (best is None or k > best):
                best = k
        return dct.get(best, 0.0) if best else 0.0

    out = []
    for date, w in walcl[-60:]:
        liq = w / 1000.0 - nearest(tga, date) / 1000.0 - nearest(rrp, date)  # → 十億美元
        out.append({"date": date, "val": round(liq / 1000.0, 2)})           # → 兆美元
    return out


# ── 11 類股 ETF 輪動(Yahoo)──
SECTORS = [("XLK", "科技"), ("XLC", "通訊"), ("XLY", "非必需消費"), ("XLF", "金融"),
           ("XLV", "醫療保健"), ("XLI", "工業"), ("XLP", "必需消費"), ("XLE", "能源"),
           ("XLU", "公用事業"), ("XLB", "原物料"), ("XLRE", "房地產")]


def _yc(sym):
    try:
        d = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=2mo" % sym))
        c = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [x for x in c if x is not None]
    except Exception:
        return []


def _ret(c, n):
    return round((c[-1] / c[-1 - n] - 1) * 100, 2) if len(c) > n else None


def fetch_sectors():
    spy = _yc("SPY")
    spy20 = _ret(spy, 20) or 0
    out = []
    for sym, nm in SECTORS:
        c = _yc(sym)
        if not c:
            continue
        r20 = _ret(c, 20)
        out.append({"etf": sym, "name": nm, "r1": _ret(c, 1), "r5": _ret(c, 5),
                    "r20": r20, "rs": (round(r20 - spy20, 2) if r20 is not None else None)})
    out.sort(key=lambda x: (x["r20"] if x["r20"] is not None else -99), reverse=True)
    return {"spy_r20": spy20, "list": out}


def load_prev():
    try:
        if os.path.exists(OUT):
            return json.load(open(OUT, encoding="utf-8"))
    except Exception:
        pass
    try:
        return json.loads(_get(LIVE, timeout=20))
    except Exception:
        return {}


def append_hist(prev, key_path, entry, cap=60):
    """prev[tw][key] 累積歷史:同日覆蓋、新日 append、留近 cap 筆。"""
    if not entry:
        return []
    hist = (((prev or {}).get(key_path[0]) or {}).get(key_path[1])) or []
    hist = [h for h in hist if h.get("date") != entry.get("date")]
    hist.append(entry)
    hist.sort(key=lambda h: h.get("date", ""))
    return hist[-cap:]


def main():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)  # 台北
    prev = load_prev()
    names = load_names()

    ds, t86 = latest_trading_date(now)
    inst = fetch_inst_market()
    ranks = fetch_t86_ranks(t86, names) if t86 else {}
    margin = fetch_margin(now)

    inst_entry = None
    if inst:
        inst_entry = {"date": inst["date"], "foreign": inst["foreign"],
                      "trust": inst["trust"], "dealer": inst["dealer"]}
    margin_entry = None
    if margin and "margin_bal" in margin:
        margin_entry = {"date": margin["date"], "margin_bal": margin["margin_bal"],
                        "short_bal": margin.get("short_bal")}

    tw = {
        "inst_today": inst,
        "inst_hist": append_hist(prev, ("tw", "inst_hist"), inst_entry),
        "ranks": ranks,
        "margin_today": margin,
        "margin_hist": append_hist(prev, ("tw", "margin_hist"), margin_entry),
    }

    us = {
        "fed_liq": fetch_fed_liquidity(),
        "hy_spread": [{"date": d, "val": v} for d, v in fred("BAMLH0A0HYM2", 180)[-120:]],
        "mmf": [{"date": d, "val": round(v, 1)} for d, v in fred("RMFSL", 36)[-24:]],
        "sectors": fetch_sectors(),
    }

    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "tw": tw, "us": us}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("[capital] -> data/capital.json  法人%s 融資%s 法人榜%d 板塊%d FedLiq%d" % (
        (inst["date"] if inst else "—"), (margin["date"] if margin else "—"),
        len(ranks.get("foreign_buy", [])), len(us["sectors"].get("list", [])), len(us["fed_liq"])))


if __name__ == "__main__":
    main()

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


# ── 大盤三大法人(BFI82U;dayDate 可抓歷史,單位→億元)──
def _bfi(day=""):
    url = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json"
    if day:
        url += "&dayDate=" + day
    try:
        j = json.loads(_get(url))
    except Exception:
        return None
    if j.get("stat") != "OK" or not j.get("data"):
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
    dd = j.get("date", day)
    date = "%s-%s-%s" % (dd[:4], dd[4:6], dd[6:8]) if len(dd) == 8 else dd
    return {"date": date, "foreign": round(foreign, 1), "trust": round(trust, 1),
            "dealer": round(dealer, 1), "total": round(foreign + trust + dealer, 1)}


def fetch_inst_hist(now, n=60):
    """回補近 n 交易日大盤三大法人(往前掃 ~95 日,略過假日)。"""
    out, d, tries = [], now.date(), 0
    while len(out) < n and tries < 95:
        r = _bfi(d.strftime("%Y%m%d"))
        if r and r.get("date"):
            out.append({"date": r["date"], "foreign": r["foreign"],
                        "trust": r["trust"], "dealer": r["dealer"], "total": r["total"]})
        d -= datetime.timedelta(days=1); tries += 1; time.sleep(0.25)
    return out


def merge_hist(prev_list, new_list, cap=60):
    """以日期為鍵 union(新資料覆蓋舊),容忍單次抓取失敗 → 歷史不會被清空。"""
    m = {}
    for r in (prev_list or []):
        if r.get("date"):
            m[r["date"]] = r
    for r in (new_list or []):
        if r.get("date"):
            m[r["date"]] = r
    return [m[k] for k in sorted(m)][-cap:]


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


def fetch_margin_hist(now, n=60):
    out, d, tries = [], now.date(), 0
    while len(out) < n and tries < 95:
        r = _margin_one(d.strftime("%Y%m%d"))
        if r:
            out.append({"date": r["date"], "margin_bal": r["margin_bal"], "short_bal": r["short_bal"]})
        d -= datetime.timedelta(days=1); tries += 1; time.sleep(0.3)
    return out


# ── 期貨籌碼(TAIFEX,Big5,日期區間):大台外資/投信/自營未平倉 + 微台散戶多空比 ──
def _taifex_post(path, params):
    return urllib.request.urlopen(urllib.request.Request(
        "https://www.taifex.com.tw/cht/3/" + path,
        data=urllib.parse.urlencode(params).encode(), headers=UA),
        timeout=45, context=_SSL).read().decode("big5", "ignore")


def fetch_futures(now, days=95):
    end = now.date(); start = end - datetime.timedelta(days=days)
    rng = {"queryStartDate": start.strftime("%Y/%m/%d"), "queryEndDate": end.strftime("%Y/%m/%d")}
    tx = {"foreign": [], "trust": [], "dealer": []}
    micro_inst = {}     # date -> 微型臺指 三大法人未平倉淨額合計(口)
    small_inst = {}     # date -> 小型臺指 三大法人未平倉淨額合計(口)
    try:
        rows = list(csv.reader(io.StringIO(_taifex_post(
            "futContractsDateDown", dict(rng, down_type="1", commodity_id="TX")))))
        for r in rows:
            if len(r) < 14:
                continue
            dt = r[0].replace("/", "-").strip()
            if not re.match(r"\d{4}-\d{2}-\d{2}", dt):
                continue
            prod = r[1].strip(); who = r[2]; net = _num(r[13])
            if prod == "臺股期貨":              # 大台 TX 三大法人未平倉淨額
                if "外資" in who or "陸資" in who:
                    tx["foreign"].append({"date": dt, "oi": round(net)})
                elif "投信" in who:
                    tx["trust"].append({"date": dt, "oi": round(net)})
                elif "自營" in who:
                    tx["dealer"].append({"date": dt, "oi": round(net)})
            elif prod == "微型臺指期貨":
                micro_inst[dt] = micro_inst.get(dt, 0) + net
            elif prod == "小型臺指期貨":
                small_inst[dt] = small_inst.get(dt, 0) + net
    except Exception:
        pass
    for k in tx:
        tx[k] = sorted(tx[k], key=lambda x: x["date"])[-60:]

    def _oi_by_date(cid):   # futDataDown 區間上限 ~1 月 → 分 25 天段;一般時段各月加總
        oi = {}; cs = start
        while cs <= end:
            ce = min(cs + datetime.timedelta(days=24), end)
            try:
                rows = list(csv.reader(io.StringIO(_taifex_post("futDataDown", {
                    "down_type": "1", "commodity_id": cid,
                    "queryStartDate": cs.strftime("%Y/%m/%d"),
                    "queryEndDate": ce.strftime("%Y/%m/%d")}))))
                for r in rows:
                    if len(r) < 18:
                        continue
                    dt = r[0].replace("/", "-").strip()
                    if not re.match(r"\d{4}-\d{2}-\d{2}", dt) or "盤後" in r[17]:
                        continue
                    try:
                        oi[dt] = oi.get(dt, 0) + float(r[11].replace(",", ""))
                    except Exception:
                        pass
            except Exception:
                pass
            cs = ce + datetime.timedelta(days=1)
        return oi

    def _retail(inst, oi):   # 散戶多空比% = 散戶淨/總OI;散戶淨 = −三大法人淨
        out = []
        for dt in sorted(set(inst) & set(oi)):
            if oi[dt] > 0:
                out.append({"date": dt, "ratio": round(-inst[dt] / oi[dt] * 100, 2),
                            "net": round(-inst[dt])})
        return out[-60:]

    return {"tx": tx,
            "retail": _retail(micro_inst, _oi_by_date("TMF")),
            "retail_small": _retail(small_inst, _oi_by_date("MTX"))}


# ── 千張大戶(TDCC 集保股權分散;分級15=1,000張以上;週頻,prev 週累積算變化)──
def fetch_large_holders(prev, topn=20):
    try:
        raw = _get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=70)
    except Exception:
        return None
    cur = {}; date = ""
    for r in csv.reader(io.StringIO(raw.lstrip("﻿"))):
        if len(r) < 6 or r[2].strip() == "持股分級":
            continue
        if r[2].strip() == "15":               # 1,000,001 股以上(千張大戶)
            date = r[0].strip()
            cur[r[1].strip()] = round(_num(r[5]), 2)   # 占集保庫存比例 %
    if not cur:
        return None
    names = load_names()
    prevm = (((prev or {}).get("tw") or {}).get("large") or {}).get("ratios") or {}
    rows = []
    for code, ratio in cur.items():
        if not re.fullmatch(r"\d{4}", code):    # 只留一般 4 位股票
            continue
        nm = name_of(code, names)
        if not nm or ratio >= 99.5:             # 過濾無名稱/單一股東(100%)的冷門股
            continue
        chg = round(ratio - prevm[code], 2) if code in prevm else None
        rows.append({"code": code, "name": nm, "ratio": ratio, "chg": chg})
    concentrated = sorted(rows, key=lambda x: x["ratio"], reverse=True)[:topn]
    has_chg = [x for x in rows if x["chg"] is not None]
    rising = sorted(has_chg, key=lambda x: x["chg"], reverse=True)[:topn]
    falling = sorted(has_chg, key=lambda x: x["chg"])[:topn]
    dd = date
    if len(dd) == 8:
        dd = "%s-%s-%s" % (dd[:4], dd[4:6], dd[6:8])
    return {"date": dd, "ratios": cur, "concentrated": concentrated,
            "rising": rising, "falling": falling, "has_chg": bool(has_chg)}


# ── 借券賣出餘額(TWSE TWT93U,逐檔加總 col12 今日餘額,股→張;每日累積)──
def fetch_borrow(now):
    d = now.date()
    for _ in range(6):
        ds = d.strftime("%Y%m%d")
        try:
            j = json.loads(_get("https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=%s&response=json" % ds))
            if j.get("stat") == "OK" and j.get("data"):
                tot = 0.0
                for r in j["data"]:
                    if len(r) > 12:
                        tot += _num(r[12])
                dd = j.get("date", ds)
                date = "%s-%s-%s" % (dd[:4], dd[4:6], dd[6:8]) if len(dd) == 8 else dd
                return {"date": date, "balance": round(tot / 1000)}   # 股 → 張
        except Exception:
            pass
        d -= datetime.timedelta(days=1)
    return None


# ── 匯率/熱錢:USD/TWD + 美元指數 DXY(Yahoo)──
def fetch_fx():
    out = {}
    for key, sym in [("usdtwd", "TWD=X"), ("dxy", "DX-Y.NYB")]:
        try:
            d = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=1y" % sym))
            res = d["chart"]["result"][0]
            ts = res["timestamp"]; cl = res["indicators"]["quote"][0]["close"]
            ser = []
            for i in range(len(ts)):
                if cl[i] is not None:
                    dt = datetime.datetime.utcfromtimestamp(ts[i]).strftime("%Y-%m-%d")
                    ser.append({"date": dt, "val": round(cl[i], 3)})
            out[key] = ser[-180:]
        except Exception:
            out[key] = []
    return out


# ── COT(CFTC Traders in Financial Futures;E-MINI S&P 500)──
def fetch_cot(weeks=26):
    url = ("https://publicreporting.cftc.gov/resource/gpe5-46if.json?"
           "$where=" + urllib.parse.quote("market_and_exchange_names like 'E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE'") +
           "&$order=" + urllib.parse.quote("report_date_as_yyyy_mm_dd DESC") + "&$limit=%d" % weeks)
    try:
        d = json.loads(_get(url, timeout=40))
    except Exception:
        return []
    out = []
    for r in d:
        try:
            out.append({
                "date": r["report_date_as_yyyy_mm_dd"][:10],
                "lev_net": int(r.get("lev_money_positions_long", 0)) - int(r.get("lev_money_positions_short", 0)),
                "am_net": int(r.get("asset_mgr_positions_long", 0)) - int(r.get("asset_mgr_positions_short", 0)),
                "dealer_net": int(r.get("dealer_positions_long_all", 0)) - int(r.get("dealer_positions_short_all", 0)),
                "oi": int(r.get("open_interest_all", 0)),
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["date"])
    return out


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
    walcl = fred("WALCL", 320)            # 週,百萬美元(~6年)
    tga = dict(fred("WTREGEN", 2200))     # 日,百萬
    rrp = dict(fred("RRPONTSYD", 2200))   # 日,十億
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
    for date, w in walcl[-260:]:          # 近 ~5 年(週)
        liq = w / 1000.0 - nearest(tga, date) / 1000.0 - nearest(rrp, date)  # → 十億美元
        out.append({"date": date, "val": round(liq / 1000.0, 2)})           # → 兆美元
    return out


# ── 11 類股 ETF 輪動(Yahoo)──
SECTORS = [("XLK", "科技"), ("XLC", "通訊"), ("XLY", "非必需消費"), ("XLF", "金融"),
           ("XLV", "醫療保健"), ("XLI", "工業"), ("XLP", "必需消費"), ("XLE", "能源"),
           ("XLU", "公用事業"), ("XLB", "原物料"), ("XLRE", "房地產")]


def _yc(sym):
    """回 (closes, volumes)。"""
    try:
        d = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=3mo" % sym))
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        c = q["close"]; v = q.get("volume", [])
        pair = [(c[i], (v[i] if i < len(v) else None)) for i in range(len(c)) if c[i] is not None]
        return [p[0] for p in pair], [p[1] for p in pair if p[1] is not None]
    except Exception:
        return [], []


def _ret(c, n):
    return round((c[-1] / c[-1 - n] - 1) * 100, 2) if len(c) > n else None


def _volr(v):
    """近5日均量 / 近20日均量(>1=量能放大,資金流入)。"""
    if len(v) < 20:
        return None
    a5 = sum(v[-5:]) / 5.0; a20 = sum(v[-20:]) / 20.0
    return round(a5 / a20, 2) if a20 else None


def fetch_sectors():
    spy, _ = _yc("SPY")
    spy20 = _ret(spy, 20) or 0
    out = []
    for sym, nm in SECTORS:
        c, v = _yc(sym)
        if not c:
            continue
        r20 = _ret(c, 20)
        out.append({"etf": sym, "name": nm, "r1": _ret(c, 1), "r5": _ret(c, 5),
                    "r20": r20, "rs": (round(r20 - spy20, 2) if r20 is not None else None),
                    "volr": _volr(v)})
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
    ranks = fetch_t86_ranks(t86, names) if t86 else {}
    pv = (prev or {}).get("tw") or {}
    inst_hist = merge_hist(pv.get("inst_hist"), fetch_inst_hist(now, 60))
    inst_today = inst_hist[-1] if inst_hist else None
    time.sleep(3)   # 兩段 TWSE 歷史掃描間暫停,避免限流
    margin_hist = merge_hist(pv.get("margin_hist"), fetch_margin_hist(now, 60))
    margin_today = margin_hist[-1] if margin_hist else None
    fut = fetch_futures(now, 95)
    tx_oi = fut["tx"]; retail = fut["retail"]; retail_small = fut["retail_small"]
    large = fetch_large_holders(prev)
    time.sleep(2)
    borrow = fetch_borrow(now)
    borrow_hist = merge_hist(pv.get("borrow_hist"),
                             [{"date": borrow["date"], "balance": borrow["balance"]}] if borrow else [])

    # 融資今日增減(由歷史末兩筆)
    if margin_today and len(margin_hist) >= 2:
        p = margin_hist[-2]
        margin_today = dict(margin_today)
        margin_today["margin_chg"] = round(margin_today["margin_bal"] - p["margin_bal"], 1)
        margin_today["short_chg"] = round(margin_today["short_bal"] - p["short_bal"])

    tw = {
        "inst_today": inst_today, "inst_hist": inst_hist, "ranks": ranks,
        "margin_today": margin_today, "margin_hist": margin_hist,
        "tx_oi": tx_oi, "retail": retail, "retail_small": retail_small,
        "borrow_today": borrow, "borrow_hist": borrow_hist, "large": large,
    }
    us = {
        "fed_liq": fetch_fed_liquidity(),
        "hy_spread": [{"date": d, "val": v} for d, v in fred("BAMLH0A0HYM2", 1500)[::5][-260:]],
        "mmf": [{"date": d, "val": round(v, 1)} for d, v in fred("RMFSL", 72)[-60:]],
        "sectors": fetch_sectors(),
        "cot": fetch_cot(26),
    }
    fx = fetch_fx()

    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "tw": tw, "us": us, "fx": fx}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("[capital] 法人%d 融資%d 微台散戶%d 小台散戶%d 借券%s 大戶%s 板塊%d FedLiq%d COT%d FX(twd%d dxy%d)" % (
        len(inst_hist), len(margin_hist), len(retail), len(retail_small),
        (borrow["date"] if borrow else "—"), (large["date"] if large else "—"),
        len(us["sectors"].get("list", [])), len(us["fed_liq"]), len(us["cot"]),
        len(fx.get("usdtwd", [])), len(fx.get("dxy", []))))


if __name__ == "__main__":
    main()

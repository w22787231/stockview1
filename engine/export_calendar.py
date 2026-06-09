# -*- coding: utf-8 -*-
"""財報/數據 行事曆匯出 → ../data/calendar.json。
三塊(皆篩未來 ~35 天、時間一律換算台北時間 UTC+8 顯示):
- econ      : 美股重要總經數據(內建 2026 官方排程;ET 釋出時刻→台北)。
- earnings_us: 美股大型股下次財報日(yfinance)。
- earnings_tw: 台股法人說明會(公開資訊觀測站 MOPS)。
總經排程需「每年手動更新一次」(可靠、不爬蟲的取捨)。
"""
import sys, os, io, json, re, ssl, csv, datetime
import urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")

DATA_DIR = os.path.join(HERE, "..", "data")
HORIZON_DAYS = 35           # 抓未來 35 天(前端顯示 30,留緩衝)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE   # MOPS 憑證鏈在部分環境驗不過 → 容錯


def _now_tpe():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)


# ── 美東時間 → 台北時間(手動處理美國日光節約,免 tzdata 依賴)──
# 2026 美國 DST:3/8 ~ 11/1 為 EDT(UTC-4)→ 台北=ET+12h;其餘 EST(UTC-5)→ 台北=ET+13h。
_DST_START = datetime.date(2026, 3, 8)
_DST_END = datetime.date(2026, 11, 1)
def _et_to_tpe(d, hhmm):
    hh, mm = (int(x) for x in hhmm.split(":"))
    off = 12 if (_DST_START <= d < _DST_END) else 13
    return datetime.datetime.combine(d, datetime.time(hh, mm)) + datetime.timedelta(hours=off)


# ── 內建美股總經 2026 排程(ET 日期 + ET 釋出時刻);imp: high/mid。以官方公布為準。──
# FOMC 決議 14:00 ET;就業報告(非農)/CPI/PPI/PCE/零售 多為 08:30 ET;GDP 08:30 ET。
ECON_2026 = [
    # 月份, 日, ET時刻, 名稱, 重要度
    (1, 9,  "08:30", "非農就業報告", "high"),
    (1, 14, "08:30", "CPI 消費者物價", "high"),
    (1, 16, "08:30", "零售銷售", "mid"),
    (1, 28, "14:00", "FOMC 利率決議", "high"),
    (1, 30, "08:30", "核心 PCE 物價", "high"),
    (2, 6,  "08:30", "非農就業報告", "high"),
    (2, 11, "08:30", "CPI 消費者物價", "high"),
    (2, 13, "08:30", "零售銷售", "mid"),
    (2, 27, "08:30", "核心 PCE 物價", "high"),
    (3, 6,  "08:30", "非農就業報告", "high"),
    (3, 11, "08:30", "CPI 消費者物價", "high"),
    (3, 18, "14:00", "FOMC 利率決議", "high"),
    (3, 27, "08:30", "核心 PCE 物價", "high"),
    (4, 3,  "08:30", "非農就業報告", "high"),
    (4, 10, "08:30", "CPI 消費者物價", "high"),
    (4, 29, "14:00", "FOMC 利率決議", "high"),
    (4, 30, "08:30", "Q1 GDP 初值", "high"),
    (5, 8,  "08:30", "非農就業報告", "high"),
    (5, 13, "08:30", "CPI 消費者物價", "high"),
    (5, 15, "08:30", "零售銷售", "mid"),
    (6, 5,  "08:30", "非農就業報告", "high"),
    (6, 10, "08:30", "CPI 消費者物價", "high"),
    (6, 17, "14:00", "FOMC 利率決議", "high"),
    (6, 26, "08:30", "核心 PCE 物價", "high"),
    (7, 2,  "08:30", "非農就業報告", "high"),
    (7, 15, "08:30", "CPI 消費者物價", "high"),
    (7, 29, "14:00", "FOMC 利率決議", "high"),
    (7, 30, "08:30", "Q2 GDP 初值", "high"),
    (8, 7,  "08:30", "非農就業報告", "high"),
    (8, 12, "08:30", "CPI 消費者物價", "high"),
    (9, 4,  "08:30", "非農就業報告", "high"),
    (9, 11, "08:30", "CPI 消費者物價", "high"),
    (9, 16, "14:00", "FOMC 利率決議", "high"),
    (10, 2, "08:30", "非農就業報告", "high"),
    (10, 13, "08:30", "CPI 消費者物價", "high"),
    (10, 28, "14:00", "FOMC 利率決議", "high"),
    (11, 6, "08:30", "非農就業報告", "high"),
    (11, 13, "08:30", "CPI 消費者物價", "high"),
    (12, 4, "08:30", "非農就業報告", "high"),
    (12, 9, "14:00", "FOMC 利率決議", "high"),
    (12, 10, "08:30", "CPI 消費者物價", "high"),
]


def build_econ(now_tpe, end_tpe):
    out = []
    for mo, dd, hhmm, name, imp in ECON_2026:
        try:
            d_et = datetime.date(2026, mo, dd)
        except ValueError:
            continue
        dt = _et_to_tpe(d_et, hhmm)            # 台北 naive datetime
        out.append({
            "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M"),
            "name": name, "importance": imp, "et": hhmm + " ET", "region": "US",
        })
    nd = now_tpe.date(); ed = end_tpe.date()
    out = [e for e in out if nd <= datetime.date.fromisoformat(e["date"]) <= ed]
    out.sort(key=lambda e: (e["date"], e["time"]))
    return out


# ── 美股大型股(精選權值);yfinance 取下次財報日 ──
US_BIG = [
    ("NVDA", "輝達"), ("AAPL", "蘋果"), ("MSFT", "微軟"), ("AMZN", "亞馬遜"),
    ("GOOGL", "Alphabet"), ("META", "Meta"), ("TSLA", "特斯拉"), ("AVGO", "博通"),
    ("JPM", "摩根大通"), ("V", "Visa"), ("WMT", "沃爾瑪"), ("XOM", "埃克森美孚"),
    ("UNH", "聯合健康"), ("LLY", "禮來"), ("JNJ", "嬌生"), ("ORCL", "甲骨文"),
    ("NFLX", "網飛"), ("AMD", "超微"), ("COST", "好市多"), ("HD", "家得寶"),
    ("BAC", "美國銀行"), ("CRM", "Salesforce"), ("KO", "可口可樂"), ("PEP", "百事"),
    ("ADBE", "Adobe"), ("QCOM", "高通"), ("MU", "美光"), ("INTC", "英特爾"),
    ("DIS", "迪士尼"), ("PYPL", "PayPal"), ("PLTR", "Palantir"), ("SMCI", "美超微"),
]


def _us_session(ts):
    """由財報時間(美東)判斷:盤前(BMO)/盤後(AMC)/空(未定)。"""
    try:
        et = ts.tz_convert("America/New_York") if getattr(ts, "tzinfo", None) else ts
        h = et.hour
    except Exception:
        h = 0
    if h <= 0:
        return ""
    return "盤前" if h < 12 else "盤後"


def _nasdaq_earn(day):
    """Nasdaq 財報行事曆(單日);回 [{symbol,time,...}]。time=time-pre-market/after-hours/not-supplied。"""
    try:
        req = urllib.request.Request(
            "https://api.nasdaq.com/api/calendar/earnings?date=" + day,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                     "Accept-Language": "en-US,en;q=0.9"})
        j = json.loads(urllib.request.urlopen(req, timeout=20, context=_SSL).read().decode("utf-8", "ignore"))
        return ((j.get("data") or {}).get("rows")) or []
    except Exception:
        return None


def build_earnings_us(now_tpe, end_tpe):
    nd = now_tpe.date(); ed = end_tpe.date()
    universe = {s for s, _ in US_BIG}; zhmap = dict(US_BIG)
    found = {}            # sym -> (date, 時段)
    nasdaq_ok = False
    d = nd
    while d <= ed:
        rows = _nasdaq_earn(d.strftime("%Y-%m-%d"))
        if rows is not None:
            nasdaq_ok = True
            for r in rows:
                s = (r.get("symbol") or "").strip().upper()
                if s in universe and s not in found:
                    t = r.get("time") or ""
                    sess = "盤前" if "pre-market" in t else ("盤後" if "after-hours" in t else "")
                    found[s] = (d, sess)
        d += datetime.timedelta(days=1)
    # 備援:Nasdaq 全擋時用 yfinance .calendar 補日期(無時段)
    if not nasdaq_ok:
        try:
            import yfinance as yf
            for sym in universe:
                if sym in found:
                    continue
                try:
                    cal = yf.Ticker(sym).calendar
                    eds = cal.get("Earnings Date") if isinstance(cal, dict) else None
                    cand = [x.date() if hasattr(x, "date") else x for x in (eds or [])]
                    cand = [x for x in cand if isinstance(x, datetime.date) and nd <= x <= ed]
                    if cand:
                        found[sym] = (min(cand), "")
                except Exception:
                    continue
        except Exception:
            pass
    out = [{"sym": s, "name": zhmap.get(s, s), "date": dt.strftime("%Y-%m-%d"),
            "region": "US", "estimated": True, "session": sess}
           for s, (dt, sess) in found.items()]
    out.sort(key=lambda e: (e["date"], e.get("session") or "z"))
    return out


# ── 台股法人說明會(公開資訊觀測站 MOPS t100sb02_1)──
def _mops(typek, roc_year, month):
    url = "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1"
    data = urllib.parse.urlencode({
        "encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
        "TYPEK": typek, "year": str(roc_year), "month": "%02d" % month,
    }).encode()
    raw = urllib.request.urlopen(urllib.request.Request(
        url, data=data, headers={"User-Agent": "Mozilla/5.0"}), timeout=25, context=_SSL).read()
    return raw.decode("utf-8", "ignore")


def build_earnings_tw(now_tpe, end_tpe):
    nd = now_tpe.date(); ed = end_tpe.date()
    months = {(now_tpe.year, now_tpe.month), (end_tpe.year, end_tpe.month)}
    seen, out = set(), []
    for (yy, mm) in months:
        roc = yy - 1911
        for typek in ("sii", "otc"):
            try:
                html = _mops(typek, roc, mm)
            except Exception:
                continue
            for block in re.split(r"</tr>", html, flags=re.I):
                cells = [re.sub(r"<[^>]*>", "", c).replace("　", " ").strip()
                         for c in re.split(r"</td>", block, flags=re.I)]
                cells = [c for c in cells if c]
                code = next((c for c in cells if re.fullmatch(r"\d{4}", c)), None)
                dm = next((re.match(r"(\d{3})/(\d{2})/(\d{2})", c) for c in cells
                           if re.match(r"\d{3}/\d{2}/\d{2}", c)), None)
                if not code or not dm:
                    continue
                yyyy = int(dm.group(1)) + 1911
                try:
                    d = datetime.date(yyyy, int(dm.group(2)), int(dm.group(3)))
                except ValueError:
                    continue
                key = (code, d)
                if not (nd <= d <= ed) or key in seen:
                    continue
                full = " ".join(cells)
                # 受邀參加券商會議/NDR/論壇 → 標記 inv=True(前端可切換顯示),非公司自辦正式法說
                invited = ("受邀" in full) or bool(re.search(r"受.{0,10}邀請", full))
                ci = cells.index(code)
                name = cells[ci + 1] if ci + 1 < len(cells) and not re.fullmatch(r"\d{4}", cells[ci + 1]) else ""
                tm = next((c for c in cells if re.fullmatch(r"\d{2}:\d{2}", c)), "")
                seen.add(key)
                out.append({"sym": code, "name": name, "date": d.strftime("%Y-%m-%d"),
                            "time": tm, "region": "TW",
                            "kind": "受邀論壇" if invited else "法說會", "inv": invited})
    out.sort(key=lambda e: (e["date"], e.get("time") or ""))
    return out


# ── 美股實際經濟數據(FRED 免費):實際/前期/MoM/YoY。預期(consensus)無免費源,前端標「—」。──
def _fred(sid):
    """回 [(date, value_str), ...](舊→新)。優先用 FRED 官方 API(需 env FRED_API_KEY,雲端 CI 不被擋),
    無金鑰時退回 fredgraph.csv(本地可用,但雲端 IP 常被 FRED 擋 → 改用金鑰)。"""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        u = ("https://api.stlouisfed.org/fred/series/observations?series_id=" + sid +
             "&api_key=" + key + "&file_type=json")
        for _ in range(3):
            try:
                d = json.loads(urllib.request.urlopen(urllib.request.Request(
                    u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
                ).read().decode("utf-8", "ignore"))
                obs = [[o["date"], o["value"]] for o in d.get("observations", [])
                       if o.get("value") not in ("", ".", None)]
                if obs:
                    return obs                    # 已是舊→新
            except Exception:
                continue
    u = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + sid
    for _ in range(3):
        try:
            d = urllib.request.urlopen(urllib.request.Request(
                u, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv"}), timeout=30
            ).read().decode("utf-8", "ignore")
            rows = [r for r in csv.reader(io.StringIO(d)) if r and r[-1] not in ("", ".")]
            return rows[1:]                       # [(date, value), ...]
        except Exception:
            continue
    return None


# (中文標籤, FRED 代號, 類型)。infl=通膨(實際=YoY,補充MoM,用NSA對齊官方);retail=實際MoM補充YoY;
# jobs=月增K;claims=水準K;rate=%水準;gdp=年化%。YoY 一律「同月去年」精確比對。
US_MACRO = [
    ("CPI 消費者物價", "CPIAUCNS", "infl"),      # NSA → 對齊官方頭條年增
    ("核心 CPI", "CPILFENS", "infl"),
    ("核心 PCE 物價", "PCEPILFE", "infl"),
    ("PPI 生產者物價", "PPIFIS", "infl"),
    ("零售銷售", "RSAFS", "retail"),
    ("非農就業", "PAYEMS", "jobs"),
    ("失業率", "UNRATE", "rate"),
    ("初領失業金", "ICSA", "claims"),
    ("GDP 年化季增", "A191RL1Q225SBEA", "gdp"),
]


def fetch_us_macro_data():
    out = []
    for label, sid, kind in US_MACRO:
        r = _fred(sid)
        if not r or len(r) < 2:
            continue
        try:
            m = {row[0]: float(row[1]) for row in r}          # {date: value}
            dates = [row[0] for row in r]
            d0, d1 = dates[-1], dates[-2]
            v0, v1 = m[d0], m[d1]
            period = d0[:7]

            def yoy(d):                                       # 同月去年精確比對
                dy = "%d%s" % (int(d[:4]) - 1, d[4:])
                return (m[d] / m[dy] - 1) * 100 if dy in m else None

            actual = prev = extra = None
            if kind == "infl":
                y0, y1 = yoy(d0), yoy(d1)
                actual = "%+.2f%%" % y0 if y0 is not None else None
                prev = "%+.2f%%" % y1 if y1 is not None else None
                extra = "月增 %+.2f%%" % ((v0 / v1 - 1) * 100)
            elif kind == "retail":
                actual = "%+.2f%%" % ((v0 / v1 - 1) * 100)
                if len(dates) >= 3:
                    prev = "%+.2f%%" % ((v1 / m[dates[-3]] - 1) * 100)
                y0 = yoy(d0)
                extra = "年增 %+.2f%%" % y0 if y0 is not None else None
            elif kind == "jobs":
                actual = "{:+,.0f}K".format(v0 - v1)         # 注意:逗號千分位旗標只 .format 支援,% 格式化會丟例外
                if len(dates) >= 3:
                    prev = "{:+,.0f}K".format(v1 - m[dates[-3]])
            elif kind == "claims":
                actual = "{:,.0f}K".format(v0 / 1000.0); prev = "{:,.0f}K".format(v1 / 1000.0)
            elif kind == "rate":
                actual = "%.2f%%" % v0; prev = "%.2f%%" % v1
            elif kind == "gdp":
                actual = "%+.1f%%" % v0; prev = "%+.1f%%" % v1
            out.append({"label": label, "period": period, "actual": actual,
                        "prev": prev, "extra": extra, "kind": kind})
        except Exception:
            continue
    return out or None


def build():
    now = _now_tpe()
    end = now + datetime.timedelta(days=HORIZON_DAYS)
    econ = build_econ(now, end)
    eus = build_earnings_us(now, end)
    etw = build_earnings_tw(now, end)
    us_data = fetch_us_macro_data()
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz": "Asia/Taipei (UTC+8)",
        "horizon_days": HORIZON_DAYS,
        "econ": econ,
        "earnings_us": eus,
        "earnings_tw": etw,
        "us_data": us_data,
        "note": "時間為台北時間。美股總經為內建官方排程(以官方公布為準);財報日多為預估、可能變動。美股實際數據來源 FRED。",
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "calendar.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[calendar] -> data/calendar.json  econ %d, US財報 %d, 台股法說 %d, 美股數據 %d"
          % (len(econ), len(eus), len(etw), len(us_data or [])))


if __name__ == "__main__":
    build()

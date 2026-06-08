# -*- coding: utf-8 -*-
"""財報/數據 行事曆匯出 → ../data/calendar.json。
三塊(皆篩未來 ~35 天、時間一律換算台北時間 UTC+8 顯示):
- econ      : 美股重要總經數據(內建 2026 官方排程;ET 釋出時刻→台北)。
- earnings_us: 美股大型股下次財報日(yfinance)。
- earnings_tw: 台股法人說明會(公開資訊觀測站 MOPS)。
總經排程需「每年手動更新一次」(可靠、不爬蟲的取捨)。
"""
import sys, os, io, json, re, ssl, datetime
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


def build_earnings_us(now_tpe, end_tpe):
    try:
        import yfinance as yf
    except Exception:
        return []
    nd = now_tpe.date(); ed = end_tpe.date()
    out = []
    for sym, zh in US_BIG:
        try:
            cal = yf.Ticker(sym).calendar
            ed_dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if not ed_dates:
                continue
            cand = []
            for x in ed_dates:
                dx = x.date() if hasattr(x, "date") else x
                if isinstance(dx, datetime.date) and nd <= dx <= ed:
                    cand.append(dx)
            if not cand:
                continue
            d = min(cand)
            out.append({"sym": sym, "name": zh, "date": d.strftime("%Y-%m-%d"),
                        "region": "US", "estimated": True})
        except Exception:
            continue
    out.sort(key=lambda e: e["date"])
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
                if not (nd <= d <= ed) or code in seen:
                    continue
                full = " ".join(cells)
                if "受邀" in full or re.search(r"受.{0,10}邀請", full):
                    continue        # 濾掉「受邀參加外資券商會議/NDR」,只留公司自辦正式法說會
                ci = cells.index(code)
                name = cells[ci + 1] if ci + 1 < len(cells) and not re.fullmatch(r"\d{4}", cells[ci + 1]) else ""
                tm = next((c for c in cells if re.fullmatch(r"\d{2}:\d{2}", c)), "")
                seen.add(code)
                out.append({"sym": code, "name": name, "date": d.strftime("%Y-%m-%d"),
                            "time": tm, "region": "TW", "kind": "法說會"})
    out.sort(key=lambda e: (e["date"], e.get("time") or ""))
    return out


def build():
    now = _now_tpe()
    end = now + datetime.timedelta(days=HORIZON_DAYS)
    econ = build_econ(now, end)
    eus = build_earnings_us(now, end)
    etw = build_earnings_tw(now, end)
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz": "Asia/Taipei (UTC+8)",
        "horizon_days": HORIZON_DAYS,
        "econ": econ,
        "earnings_us": eus,
        "earnings_tw": etw,
        "note": "時間為台北時間。美股總經為內建官方排程(以官方公布為準);財報日多為預估、可能變動。",
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "calendar.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[calendar] -> data/calendar.json  econ %d, US財報 %d, 台股法說 %d"
          % (len(econ), len(eus), len(etw)))


if __name__ == "__main__":
    build()

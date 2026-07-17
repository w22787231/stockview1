# -*- coding: utf-8 -*-
"""七雄資本支出(Capex)二階導 → data/capex_2nd_deriv.json。
一階導=YoY(年增率，對比去年同季，避開capex的財年/採購時點季節性)；
二階導=短期動能(近2季YoY均)−長期動能(近6季YoY均)，正=加速、負=減緩(比照個股二階導e5/e20邏輯)。

MSFT/META/GOOGL/AMZN: SEC XBRL companyconcept API，10-Q單季直接揭露 +
  半年/9個月/全年累計反推缺口季度，可拉到長連續季度序列。
TSM/ASML: 境外私人發行人僅申報20-F(年報)，SEC 無結構化季度資料；改用 yfinance
  季度現金流量表(原幣別TWD/EUR，以即期匯率換算美元)，僅近5季，標記 mode="limited"。

抓取全失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_capex_2nd_deriv.py"""
import sys, os, json, datetime, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import warnings
warnings.filterwarnings("ignore")
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "capex_2nd_deriv.json")
LIVE = "https://stockview1.pages.dev/data/capex_2nd_deriv.json"


def _load_old():
    """CI 每次都是乾淨 checkout，本機沒有舊檔；抓取失敗/不足時改回讀「線上目前這份」
    當備援，避免單次 API 限流/故障就讓整個區塊從網站消失。"""
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0 Chrome/124"})
        old = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        print("[capex] 本機無檔，改用線上 capex_2nd_deriv.json 當備援(%d 家公司)"
              % len(old.get("companies") or []))
        return old
    except Exception as e:
        print("[capex] 線上回讀失敗:", e)
        return None

SEC_HEADERS = {"User-Agent": "stockview-research contact@example.com"}
SEC_COMPANIES = {
    "MSFT": ("0000789019", "Microsoft", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "META": ("0001326801", "Meta", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "GOOGL": ("0001652044", "Google", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "AMZN": ("0001018724", "Amazon", "PaymentsToAcquireProductiveAssets"),
}
YF_COMPANIES = {
    "TSM": ("台積電", "TWD"),
    "ASML": ("ASML", "EUR"),
}
SHORT_N = 2
LONG_N = 6


def _fetch_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _dedup_bucket(facts, lo, hi):
    """依 end 日期去重(同期間取filed最新一筆)，回 {end: val}。"""
    q = {}
    for x in facts:
        s = datetime.date.fromisoformat(x["start"])
        e = datetime.date.fromisoformat(x["end"])
        days = (e - s).days
        if lo <= days <= hi:
            prev = q.get(x["end"])
            if prev is None or x.get("filed", "") >= prev.get("filed", ""):
                q[x["end"]] = x
    return {k: v["val"] for k, v in q.items()}


def _nearest_before(d, end_date, target_days=91, tol=15):
    ed = datetime.date.fromisoformat(end_date)
    best = None
    for k, v in d.items():
        kd = datetime.date.fromisoformat(k)
        diff = (ed - kd).days
        if abs(diff - target_days) <= tol:
            if best is None or abs(diff - target_days) < best[0]:
                best = (abs(diff - target_days), v)
    return best[1] if best else None


def _build_quarterly_from_sec(facts):
    """把 10-Q單季直接揭露 + 半年/9個月/全年累計 反推成連續單季序列。"""
    q1 = _dedup_bucket(facts, 80, 100)
    h1 = _dedup_bucket(facts, 170, 195)
    m9 = _dedup_bucket(facts, 260, 285)
    fy = _dedup_bucket(facts, 350, 380)
    quarterly = dict(q1)
    for e2, v2 in h1.items():
        if e2 in quarterly:
            continue
        base = _nearest_before(quarterly, e2)
        if base is not None:
            quarterly[e2] = v2 - base
    for e3, v3 in m9.items():
        if e3 in quarterly:
            continue
        base = _nearest_before(h1, e3) or _nearest_before(quarterly, e3, target_days=61, tol=15)
        if base is not None:
            quarterly[e3] = v3 - base
    for e4, v4 in fy.items():
        if e4 in quarterly:
            continue
        base = _nearest_before(m9, e4) or _nearest_before(quarterly, e4, target_days=91, tol=15)
        if base is not None:
            quarterly[e4] = v4 - base
    return quarterly


def _qlabel(dt):
    y, m = dt[2:4], dt[5:7]
    q = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}[m]
    return y + q


def fetch_sec_company(cik, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    d = _fetch_json(url, SEC_HEADERS)
    units = d["units"]
    key = "USD" if "USD" in units else list(units.keys())[0]
    quarterly = _build_quarterly_from_sec(units[key])
    dates = sorted(quarterly.keys())[-13:]
    capex = [round(quarterly[d_] / 1e9, 3) for d_ in dates]
    return dates, capex


def fetch_yf_fx():
    import yfinance as yf
    twd_usd = float(yf.Ticker("TWD=X").history(period="5d")["Close"].iloc[-1])
    eur_usd = float(yf.Ticker("EURUSD=X").history(period="5d")["Close"].iloc[-1])
    return twd_usd, eur_usd


def fetch_yf_company(ticker, ccy, twd_usd, eur_usd):
    import yfinance as yf
    tk = yf.Ticker(ticker)
    qcf = tk.quarterly_cashflow
    row = qcf.loc["Capital Expenditure"].dropna().sort_index()
    dates = [d.strftime("%Y-%m-%d") for d in row.index]
    vals_native = [abs(float(v)) for v in row.values]

    def to_usd(v):
        if ccy == "TWD":
            return v / twd_usd
        if ccy == "EUR":
            return v * eur_usd
        return v

    capex = [round(to_usd(v) / 1e9, 3) for v in vals_native]
    return dates, capex


def compute_metrics(dates, capex, mode):
    labels = [_qlabel(d) for d in dates]
    n = len(capex)
    yoy = [None] * min(4, n) + [
        round((capex[i] / capex[i - 4] - 1.0) * 100.0, 2) for i in range(4, n)
    ]
    qoq = [None] + [round((capex[i] / capex[i - 1] - 1.0) * 100.0, 2) for i in range(1, n)]

    short_avg = long_avg = second_deriv = None
    if mode != "limited":
        valid_yoy = [v for v in yoy if v is not None]
        if len(valid_yoy) >= 4:
            short_avg = round(sum(valid_yoy[-SHORT_N:]) / len(valid_yoy[-SHORT_N:]), 2)
            long_slice = valid_yoy[-LONG_N:]
            long_avg = round(sum(long_slice) / len(long_slice), 2)
            second_deriv = round(short_avg - long_avg, 2)
    elif len(capex) >= 5:
        # TSM/ASML:首尾剛好差4季，只能算1個YoY點，無法算短期/長期均值
        pass

    return {
        "dates": dates, "labels": labels, "capex": capex,
        "yoy": yoy, "qoq": qoq,
        "short_avg": short_avg, "long_avg": long_avg, "second_deriv": second_deriv,
    }


def build_live():
    out = []
    for ticker, (cik, name, tag) in SEC_COMPANIES.items():
        try:
            dates, capex = fetch_sec_company(cik, tag)
            if len(dates) < 5:
                print(f"[capex] {ticker} SEC資料不足({len(dates)}季)，略過")
                continue
            m = compute_metrics(dates, capex, "yoy")
            out.append({"ticker": ticker, "name": name, "ccy": "USD", "mode": "yoy", **m})
            print(f"[capex] {ticker} OK: {len(dates)}季，二階導={m['second_deriv']}")
        except Exception as e:
            print(f"[capex] {ticker} SEC抓取失敗: {e}")
        time.sleep(0.2)

    try:
        twd_usd, eur_usd = fetch_yf_fx()
    except Exception as e:
        print(f"[capex] 匯率抓取失敗，TSM/ASML略過: {e}")
        twd_usd = eur_usd = None

    if twd_usd is not None:
        for ticker, (name, ccy) in YF_COMPANIES.items():
            try:
                dates, capex = fetch_yf_company(ticker, ccy, twd_usd, eur_usd)
                if len(dates) < 5:
                    print(f"[capex] {ticker} yfinance資料不足({len(dates)}季)，略過")
                    continue
                m = compute_metrics(dates, capex, "limited")
                out.append({"ticker": ticker, "name": name, "ccy": ccy, "mode": "limited", **m})
                print(f"[capex] {ticker} OK(限量): {len(dates)}季")
            except Exception as e:
                print(f"[capex] {ticker} yfinance抓取失敗: {e}")

    return out


def main():
    print("=== 抓取七雄資本支出二階導 ===", flush=True)
    rows = None
    try:
        rows = build_live()
    except Exception as e:
        print("[capex] 抓取失敗:", e)
    if not rows or len(rows) < 4:
        print("[!] 資料不足(<4家公司) → 嘗試沿用線上 last-good")
        old = _load_old()
        if isinstance(old, dict) and len(old.get("companies") or []) >= 4:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(old, f, ensure_ascii=False, indent=1)
            print(f"✓ capex_2nd_deriv.json 沿用線上舊資料：{len(old['companies'])} 家公司")
        else:
            print("[!] 無可用資料(新舊皆失敗) → 不寫檔")
        return
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "short_n": SHORT_N, "long_n": LONG_N,
        "companies": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"✓ capex_2nd_deriv.json 已更新：{len(rows)} 家公司")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""大科技 ROIC(投入資本回報率)逐季線圖 → data/roic.json。

口徑(比照 export_capex_2nd_deriv.py 的 SEC XBRL 反推手法，另加 TTM 年化):
  NOPAT(TTM) = 近4季營業利益(OperatingIncomeLoss)加總 × (1 − 近4季有效稅率)
  有效稅率   = 近4季所得稅費用(IncomeTaxExpenseBenefit) ÷ 近4季稅前淨利
  投入資本   = 股東權益(StockholdersEquity) + 付息負債(長期負債+短期到期部位) − 現金及約當現金
  ROIC       = NOPAT(TTM) ÷ 平均投入資本(本季末、與4季前那一季末的平均) × 100%
  用 TTM 而非單季×4，是因為 AMZN 等公司單季營業利益季節性很強(Q4假期旺季)，
  單季直接年化會讓線圖劇烈鋸齒，TTM 能還原真實趨勢(比照個股回測慣例用滾動窗口)。

公司:AAPL/MSFT/GOOGL/AMZN/META/NVDA，皆為 SEC 10-Q 直接申報者，用 XBRL companyconcept API。
部分公司稅前淨利/短期付息負債的 XBRL 標籤不同，見 PRETAX_TAG_OVERRIDE / DEBT_CURRENT_TAG。

抓取全失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_roic.py"""
import sys, os, json, datetime, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import warnings
warnings.filterwarnings("ignore")
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "roic.json")
LIVE = "https://stockview1.pages.dev/data/roic.json"

SEC_HEADERS = {"User-Agent": "stockview-research contact@example.com"}

COMPANIES = {
    "AAPL":  ("0000320193", "Apple"),
    "MSFT":  ("0000789019", "Microsoft"),
    "GOOGL": ("0001652044", "Google"),
    "AMZN":  ("0001018724", "Amazon"),
    "META":  ("0001326801", "Meta"),
    "NVDA":  ("0001045810", "Nvidia"),
}

PRETAX_TAG_DEFAULT = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
PRETAX_TAG_OVERRIDE = {
    # AMZN 沒有揭露上面那個標籤，改用這個口徑相同的替代標籤(已用 SEC API 逐一測試過存在)
    "AMZN": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
}
# 「一年內到期長期負債」標籤各家不同；META 沒有獨立揭露此項(併入長期負債揭露)，以 0 計入
# (低估其付息負債一小塊，META 槓桿本來就低，影響有限，UI 會註明此簡化)
DEBT_CURRENT_TAG = {
    "AAPL": "LongTermDebtCurrent",
    "MSFT": "LongTermDebtCurrent",
    "GOOGL": "DebtCurrent",
    "AMZN": "LongTermDebtCurrent",
    "META": None,
    "NVDA": "DebtCurrent",
}
# 長期負債(非流動)標籤：多數公司「LongTermDebtNoncurrent」單一標籤即可涵蓋全部歷史季度；
# GOOGL 在 2025Q2 之前改用過「LongTermDebtAndCapitalLeaseObligations」這個舊標籤，
# 兩個標籤合併(主標籤優先、缺的日期用備援標籤補)才能拉出完整的連續季度序列。
DEBT_NONCUR_TAG_CANDIDATES = {
    "GOOGL": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
}
DEBT_NONCUR_TAG_DEFAULT = ["LongTermDebtNoncurrent"]

TTM_LOOKBACK = 17  # 抓最近17季原始資料，才能算出13個TTM顯示點(17-4)
MIN_DATES_NEEDED = 8  # 至少要有8季原始資料(才能算出≥4個TTM顯示點)，不夠就整家公司跳過


def _fetch_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


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
        print("[roic] 本機無檔，改用線上 roic.json 當備援(%d 家公司)" % len(old.get("companies") or []))
        return old
    except Exception as e:
        print("[roic] 線上回讀失敗:", e)
        return None


def _dedup_bucket(facts, lo, hi):
    """依 end 日期去重(同期間取filed最新一筆)，回 {end: val}。duration型(有start)用。"""
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


def _dedup_instant(facts):
    """依 end 日期去重(同期間取filed最新一筆)，回 {end: val}。instant型(無start，資產負債表科目)用。"""
    q = {}
    for x in facts:
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
    """把 10-Q單季直接揭露 + 半年/9個月/全年累計 反推成連續單季序列(比照 capex 腳本邏輯)。"""
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


_QEND_CANDIDATES = [(3, 31), (6, 30), (9, 30), (12, 31)]


def _qlabel(dt):
    """取離財報結算日最近的標準季末(3/31,6/30,9/30,12/31)當標籤(純日曆標籤，不代表公司官方財季編號)。
    不能直接用「月份所屬季度」分組：像 AAPL 這種 4-4-5 週財年，結算日常落在月初(例如「2023-07-01」
    其實是對應6月底那一季)，用月份分組會誤判成下一季，導致連續兩季顯示同一個標籤。"""
    d = datetime.date.fromisoformat(dt)
    cands = [datetime.date(y, m, day) for y in (d.year - 1, d.year, d.year + 1) for m, day in _QEND_CANDIDATES]
    nearest = min(cands, key=lambda c: abs((c - d).days))
    q = {3: 1, 6: 2, 9: 3, 12: 4}[nearest.month]
    return f"{str(nearest.year)[2:]}Q{q}"


def fetch_concept(cik, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    d = _fetch_json(url, SEC_HEADERS)
    units = d["units"]
    key = "USD" if "USD" in units else list(units.keys())[0]
    return units[key]


def fetch_quarterly_duration(cik, tag):
    return _build_quarterly_from_sec(fetch_concept(cik, tag))


def fetch_instant(cik, tag):
    if tag is None:
        return {}
    return _dedup_instant(fetch_concept(cik, tag))


def fetch_instant_multi(cik, tags):
    """依序嘗試多個候選標籤，合併成一份日期序列(先出現的標籤優先，缺的日期用後面標籤補)。"""
    merged = {}
    for tag in tags:
        try:
            d = fetch_instant(cik, tag)
        except Exception:
            continue
        for k, v in d.items():
            if k not in merged:
                merged[k] = v
        time.sleep(0.15)
    return merged


def compute_company(ticker, cik, name):
    opinc_q = fetch_quarterly_duration(cik, "OperatingIncomeLoss")
    time.sleep(0.15)
    tax_q = fetch_quarterly_duration(cik, "IncomeTaxExpenseBenefit")
    time.sleep(0.15)
    pretax_tag = PRETAX_TAG_OVERRIDE.get(ticker, PRETAX_TAG_DEFAULT)
    pretax_q = fetch_quarterly_duration(cik, pretax_tag)
    time.sleep(0.15)

    equity_i = fetch_instant(cik, "StockholdersEquity")
    time.sleep(0.15)
    cash_i = fetch_instant(cik, "CashAndCashEquivalentsAtCarryingValue")
    time.sleep(0.15)
    ltd_noncur_i = fetch_instant_multi(cik, DEBT_NONCUR_TAG_CANDIDATES.get(ticker, DEBT_NONCUR_TAG_DEFAULT))
    debt_cur_i = fetch_instant(cik, DEBT_CURRENT_TAG.get(ticker))
    time.sleep(0.15)

    common = sorted(set(opinc_q) & set(tax_q) & set(pretax_q) & set(equity_i) & set(cash_i) & set(ltd_noncur_i))
    common = common[-TTM_LOOKBACK:]
    if len(common) < MIN_DATES_NEEDED:
        raise ValueError(f"共同季度數不足({len(common)}季 < {MIN_DATES_NEEDED})")

    def ic_at(d):
        debt = ltd_noncur_i[d] + debt_cur_i.get(d, 0)
        return equity_i[d] + debt - cash_i[d]

    dates, labels, roic_vals, nopat_ttm_vals, ic_avg_vals, etr_vals = [], [], [], [], [], []
    for i in range(4, len(common)):
        window = common[i - 3: i + 1]
        ttm_oi = sum(opinc_q[d] for d in window)
        ttm_tax = sum(tax_q[d] for d in window)
        ttm_pretax = sum(pretax_q[d] for d in window)
        etr = (ttm_tax / ttm_pretax) if ttm_pretax else None
        if etr is None or etr < 0 or etr > 0.6:
            etr = 0.21  # 稅前淨利異常(接近0/負值/稅率離譜)時，退回美國聯邦法定稅率當保守估計
        nopat_ttm = ttm_oi * (1 - etr)

        d_end = common[i]
        d_start = common[i - 4]
        ic_end = ic_at(d_end)
        ic_start = ic_at(d_start)
        ic_avg = (ic_end + ic_start) / 2.0

        roic = round(nopat_ttm / ic_avg * 100.0, 2) if ic_avg and ic_avg > 0 else None

        dates.append(d_end)
        labels.append(_qlabel(d_end))
        roic_vals.append(roic)
        nopat_ttm_vals.append(round(nopat_ttm / 1e9, 2))
        ic_avg_vals.append(round(ic_avg / 1e9, 2))
        etr_vals.append(round(etr * 100.0, 1))

    return {
        "ticker": ticker, "name": name,
        "dates": dates, "labels": labels,
        "roic": roic_vals,
        "nopat_ttm": nopat_ttm_vals,
        "invested_capital_avg": ic_avg_vals,
        "effective_tax_rate": etr_vals,
    }


def build_live():
    out = []
    for ticker, (cik, name) in COMPANIES.items():
        try:
            row = compute_company(ticker, cik, name)
            out.append(row)
            last = row["roic"][-1] if row["roic"] else None
            print(f"[roic] {ticker} OK：{len(row['dates'])}季，最新ROIC(TTM)={last}%")
        except Exception as e:
            print(f"[roic] {ticker} 失敗：{e}")
    return out


def main():
    print("=== 抓取大科技 ROIC(TTM年化)逐季 ===", flush=True)
    rows = None
    try:
        rows = build_live()
    except Exception as e:
        print("[roic] 抓取失敗:", e)
    if not rows or len(rows) < 3:
        print("[!] 資料不足(<3家公司) → 嘗試沿用線上 last-good")
        old = _load_old()
        if isinstance(old, dict) and len(old.get("companies") or []) >= 3:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(old, f, ensure_ascii=False, indent=1)
            print(f"✓ roic.json 沿用線上舊資料：{len(old['companies'])} 家公司")
        else:
            print("[!] 無可用資料(新舊皆失敗) → 不寫檔")
        return
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "NOPAT(TTM)=近4季營業利益x(1-近4季有效稅率)；投入資本=股東權益+付息負債-現金及約當現金；"
            "ROIC=NOPAT(TTM)/平均投入資本(本季末與4季前那季末之平均)。",
        "companies": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"✓ roic.json 已更新：{len(rows)} 家公司")


if __name__ == "__main__":
    main()

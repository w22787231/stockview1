# -*- coding: utf-8 -*-
"""一次性:回補台股大盤融資維持率(上市·含ETF)歷史,產出 tw_margin_ratio_seed.json。

資料源 = TWSE 歷史(免 token,每交易日 2 個呼叫):
  - MI_INDEX?date=&type=ALL           → 全上市個股收盤(分子逐檔市值用)
  - MI_MARGN?date=&selectType=ALL     → 融資金額總額(分母)+ 逐檔融資今日餘額(張)
口徑與每日 fetch_tw_margin_ratio() 一致(含 ETF),seam 錨點 2026-07-06 ≈ 194.55%。
加權指數(^TWII)以 yfinance 對齊。可重跑續補(engine/._twmr_cache.json)。

用法:python backfill_tw_margin_ratio.py            # 回補 250 交易日(至 2026-07-06)
     python backfill_tw_margin_ratio.py --days 30  # 較短
"""
import sys, os, re, json, time, datetime, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tw_margin_ratio as TWMR

BASE_DATE = datetime.date(2026, 7, 6)          # 固定基準日(可重現;不使用 today)
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tw_margin_ratio_seed.json")
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "._twmr_cache.json")


def _get(url, t=40, retries=4):
    for i in range(retries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=t
            ).read().decode("utf-8", "ignore")
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def _title_matches(title, ymd):
    """表格標題含的民國日期需等於 ymd(TWSE 偶爾回傳他日的錯誤表,需擋掉)。"""
    m = re.search(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", str(title))
    if not m:
        return False
    y, mo, d = int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))
    return f"{y:04d}{mo:02d}{d:02d}" == ymd


def _closes(ymd):
    """MI_INDEX 全上市個股收盤 {code: close};非交易日/資料日期不符回 None。"""
    j = json.loads(_get(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALL&response=json"))
    if j.get("stat") != "OK":
        return None
    for tb in j.get("tables", []):
        fields = tb.get("fields") or []
        ci = next((i for i, x in enumerate(fields) if "收盤" in str(x)), None)
        data = tb.get("data") or []
        if ci is not None and len(data) > 200 and _title_matches(tb.get("title"), ymd):
            price = {}
            for row in data:
                if len(row) > ci:
                    c = TWMR._to_float(row[ci])
                    if c:
                        price[row[0].strip()] = c
            return price
    return None


def _margin(ymd):
    """MI_MARGN 融資金額總額(元)+ 逐檔融資今日餘額(張)。非交易日回 (None, {})。"""
    j = json.loads(_get(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json"))
    if j.get("stat") != "OK":
        return None, {}
    tables = j.get("tables", [])
    if len(tables) < 2:
        return None, {}
    loan = None
    for row in tables[0]["data"]:
        if row and "融資金額" in row[0]:
            loan = float(row[5].replace(",", "")) * 1000   # 仟元→元(今日餘額)
    lots = {row[0].strip(): row[6].replace(",", "") for row in tables[1]["data"] if len(row) > 6}
    return loan, lots


def _twii_map(start_iso):
    try:
        import yfinance as yf
        h = yf.Ticker("^TWII").history(start=start_iso, auto_adjust=False)
        return {idx.strftime("%Y%m%d"): round(float(row["Close"]), 2)
                for idx, row in h.iterrows() if row.get("Close") == row.get("Close")}
    except Exception:
        return {}


def backfill(days=250):
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except Exception:
            cache = {}
    start_iso = (BASE_DATE - datetime.timedelta(days=int(days * 1.6) + 20)).isoformat()
    twii = _twii_map(start_iso)

    collected = sum(1 for v in cache.values() if v.get("ratio") is not None)
    d = BASE_DATE
    guard = int(days * 1.7) + 40
    while collected < days and guard > 0:
        guard -= 1
        ymd = d.strftime("%Y%m%d")
        if d.weekday() >= 5 or cache.get(ymd, {}).get("skip"):
            d -= datetime.timedelta(days=1); continue
        if cache.get(ymd, {}).get("ratio") is not None:
            d -= datetime.timedelta(days=1); continue
        try:
            price = _closes(ymd)
            if not price:
                cache[ymd] = {"skip": True}
            else:
                loan, lots = _margin(ymd)
                r = TWMR.compute_ratio(loan, lots, price) if loan else None
                if r is None or not (100 <= r <= 400):   # 大盤維持率合理帶;帶外=資料異常→跳過
                    if r is not None:
                        print(f"  {ymd} = {r}% 超出合理帶,跳過(資料異常)")
                    cache[ymd] = {"skip": True}
                else:
                    cache[ymd] = {"ratio": r, "twii": twii.get(ymd)}
                    collected += 1
                    print(f"  {ymd} = {r}%")
        except Exception as e:
            print(f"  {ymd} ERR {e!r} (retry next run)")
        json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)
        time.sleep(0.4)
        d -= datetime.timedelta(days=1)

    good = sorted(k for k, v in cache.items() if v.get("ratio") is not None)
    good = good[-days:]
    seed = {"method": "上市·含ETF·Σ(融資張×1000×收盤)/融資金額×100 (TWSE MI_INDEX+MI_MARGN 回補)",
            "generated_at": BASE_DATE.isoformat(),
            "dates": good,
            "ratio": [cache[k]["ratio"] for k in good],
            "twii": [cache[k].get("twii") for k in good]}
    json.dump(seed, open(SEED_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    anchor = cache.get("20260706", {}).get("ratio")
    print(f"寫入 {SEED_PATH}: {len(good)} 交易日, {good[0] if good else '-'}->{good[-1] if good else '-'}, "
          f"錨點 20260706={anchor}% (官方 ~194.55)")


if __name__ == "__main__":
    n = 250
    if "--days" in sys.argv:
        n = int(sys.argv[sys.argv.index("--days") + 1])
    backfill(n)

# 大盤融資維持率 大圖 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 stockview1「總體市場」分頁新增一張「台股大盤融資維持率(上市)」大圖,含時間按鈕、更新時間戳記、加權指數疊圖、130% 斷頭警戒線。

**Architecture:** 純計算/合併邏輯抽到新模組 `engine/tw_margin_ratio.py`(可測、無網路);`export_sentiment.py` 每日用 TWSE 資料算今日值並與「一次性 FinMind 回補種子檔」合併,輸出 sentiment.json 的 `tw_margin_ratio` key;前端 `web/index.html` 沿用 reserves/SOFR 的 load/render/draw 三函式模式畫圖。

**Tech Stack:** Python(stdlib urllib + pytest)、FinMind 開放 API(匿名)、yfinance(^TWII)、前端單檔 HTML + ECharts、node DOM-stub 測試。

## Global Constraints

- 口徑固定「上市(TWSE)」:分子排除 ETF(代號 `00` 開頭);分母 = 上市融資金額今日餘額。與每日 TWSE 法一致,seam 驗證錨點 = 2026-07-06 應 ≈ **194.55%**(分母 6,313.45 億)。
- 維持率四捨五入 2 位;歷史以 `YYYYMMDD` 為 key 去重、依日期排序、尾端裁 `cap=750`(≈3 年)。
- FinMind 只在本機回補時使用(匿名、近 1 年);CI 每日更新不需 token。
- 前端日期字串為 `YYYYMMDD`;更新時間戳記重用既有 `updStamp(asOf)`(日頻 → 星期X)。
- 繁體中文 UI 文案。疊圖顏色:維持率 `#0d9488`、加權指數灰虛線 `#94a3b8`、130% 線 `#e11d48`。
- 測試執行:引擎 `cd engine && python -m pytest <file> -v`;前端 `node web/<file>.mjs`(exit 0 = 通過)。

---

### Task 1: 純計算/合併模組 `tw_margin_ratio.py`

**Files:**
- Create: `engine/tw_margin_ratio.py`
- Test: `engine/test_tw_margin_ratio.py`

**Interfaces:**
- Produces:
  - `compute_ratio(loan_yuan: float, lots_by_code: dict, price_by_code: dict, exclude_etf=True) -> float|None`
  - `merge_history(seed: dict|None, prev: dict|None, point: dict|None, cap=750) -> (dates:list, ratio:list, twii:list)`
  - `_to_float(x) -> float|None`

- [ ] **Step 1: Write the failing test**

Create `engine/test_tw_margin_ratio.py`:

```python
# -*- coding: utf-8 -*-
import tw_margin_ratio as M


def test_compute_ratio_basic():
    # 2330: 10 張 × 1000 股 × 1000 元 = 10,000,000 市值;loan 5,000,000 → 200%
    r = M.compute_ratio(5_000_000, {"2330": "10"}, {"2330": 1000.0})
    assert r == 200.0


def test_compute_ratio_excludes_etf():
    # 0050 應被排除,結果與只有 2330 相同
    r = M.compute_ratio(5_000_000, {"2330": 10, "0050": 100}, {"2330": 1000.0, "0050": 50.0})
    assert r == 200.0


def test_compute_ratio_none_when_no_loan_or_value():
    assert M.compute_ratio(0, {"2330": 10}, {"2330": 1000}) is None
    assert M.compute_ratio(5_000_000, {}, {}) is None
    assert M.compute_ratio(5_000_000, {"2330": 10}, {}) is None  # 無價 → 市值 0 → None


def test_merge_history_dedup_sort_cap():
    seed = {"dates": ["20260101", "20260102"], "ratio": [180.0, 181.0], "twii": [20000, 20100]}
    prev = {"dates": ["20260102", "20260103"], "ratio": [181.5, 182.0], "twii": [20150, 20200]}  # d2 覆蓋
    point = {"date": "20260104", "ratio": 183.0, "twii": 20300}
    dates, ratio, twii = M.merge_history(seed, prev, point, cap=3)
    assert dates == ["20260102", "20260103", "20260104"]
    assert ratio == [181.5, 182.0, 183.0]      # d2 取 prev 覆蓋值
    assert twii == [20150, 20200, 20300]


def test_merge_history_point_updates_same_day():
    seed = {"dates": ["20260105"], "ratio": [190.0], "twii": [21000]}
    point = {"date": "20260105", "ratio": 191.0, "twii": 21050}
    dates, ratio, twii = M.merge_history(seed, None, point, cap=750)
    assert dates == ["20260105"]
    assert ratio == [191.0] and twii == [21050]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python -m pytest test_tw_margin_ratio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tw_margin_ratio'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/tw_margin_ratio.py`:

```python
# -*- coding: utf-8 -*-
"""台股大盤融資維持率(上市)純計算/合併工具。
無網路、無重相依,供 export_sentiment.py 與 backfill_tw_margin_ratio.py 共用。
口徑:維持率% = Σ(融資餘額張 × 1000 × 收盤) / 上市融資金額(元) × 100,分子排除 ETF(00 開頭)。"""


def _to_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def compute_ratio(loan_yuan, lots_by_code, price_by_code, exclude_etf=True):
    """loan_yuan: 上市融資金額總額(元)。lots_by_code: {code: 融資餘額張}. price_by_code: {code: 收盤}."""
    loan = _to_float(loan_yuan)
    if not loan or loan <= 0:
        return None
    mv = 0.0
    for code, lots in lots_by_code.items():
        code = str(code).strip()
        if exclude_etf and code.startswith("00"):
            continue
        p = price_by_code.get(code)
        l = _to_float(lots)
        pf = _to_float(p)
        if pf and l:
            mv += l * 1000 * pf
    if mv <= 0:
        return None
    return round(mv / loan * 100, 2)


def merge_history(seed, prev, point, cap=750):
    """合併 種子 + 前版累積 + 今日點,以 YYYYMMDD 去重(後者覆蓋),排序,尾端裁 cap。
    seed/prev: {'dates':[],'ratio':[],'twii':[]} 或 None。point: {'date','ratio','twii'} 或 None。"""
    m = {}

    def _absorb(src):
        if not src:
            return
        ds = src.get("dates") or []
        rs = src.get("ratio") or []
        ts = src.get("twii") or []
        for i, d in enumerate(ds):
            cur = m.get(d, {})
            r = rs[i] if i < len(rs) else None
            t = ts[i] if i < len(ts) else None
            if r is not None:
                cur["ratio"] = r
            if t is not None:
                cur["twii"] = t
            m[d] = cur

    _absorb(seed)
    _absorb(prev)
    if point and point.get("date") and point.get("ratio") is not None:
        cur = m.get(point["date"], {})
        cur["ratio"] = point["ratio"]
        if point.get("twii") is not None:
            cur["twii"] = point["twii"]
        m[point["date"]] = cur

    dates = sorted(m.keys())[-cap:]
    ratio = [m[d].get("ratio") for d in dates]
    twii = [m[d].get("twii") for d in dates]
    return dates, ratio, twii
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python -m pytest test_tw_margin_ratio.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/tw_margin_ratio.py engine/test_tw_margin_ratio.py
git commit -m "feat(engine): pure compute/merge helpers for TW margin maintenance ratio"
```

---

### Task 2: 接線 `export_sentiment.py` → 輸出 `tw_margin_ratio` key

**Files:**
- Modify: `engine/export_sentiment.py`(重寫 `fetch_tw_margin_ratio` 用 Task 1 helpers;於 `build()` 掛上新 key)

**Interfaces:**
- Consumes: `tw_margin_ratio.compute_ratio`, `tw_margin_ratio.merge_history`
- Produces: sentiment.json 新增 `tw_margin_ratio: {as_of, level, diff, dates[], ratio[], twii[], note, read, src, url}`

- [ ] **Step 1: 重寫 `fetch_tw_margin_ratio()`**

在 `engine/export_sentiment.py` 頂部 import 區加入(若尚無):
```python
import os
import tw_margin_ratio as TWMR
```

將現有 `fetch_tw_margin_ratio()`(約 engine/export_sentiment.py:311-370)整段替換為:

```python
def _twii_close_map(start="2023-01-01"):
    """^TWII 日線收盤 {YYYYMMDD: close};失敗回 {}。"""
    try:
        import yfinance as yf
        h = yf.Ticker("^TWII").history(start=start, auto_adjust=False)
        out = {}
        for idx, row in h.iterrows():
            c = row.get("Close")
            if c is not None and c == c:
                out[idx.strftime("%Y%m%d")] = round(float(c), 2)
        return out
    except Exception:
        return {}


def fetch_tw_margin_ratio(seed_path=None):
    """台股大盤融資維持率(上市)= 融資市值 / 融資金額。
    今日值:TWSE STOCK_DAY_ALL(逐檔收盤)+ MI_MARGN(融資金額總額 + 逐檔張)。
    歷史:合併 committed 種子檔 + 前版 published sentiment.json 的 tw_margin_ratio。"""
    def _g(u, t=25):
        return urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=t
        ).read().decode("utf-8", "ignore")

    point = None
    ymd = None
    try:
        sd = json.loads(_g("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"))
        price, roc = {}, ""
        for r in sd:
            c = _safe(r.get("ClosingPrice"))
            if c:
                price[r["Code"]] = c
            roc = r.get("Date", roc)
        if price and roc:
            ymd = str(int(roc[:3]) + 1911) + roc[3:]
            mj = json.loads(_g(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json"))
            tables = mj.get("tables", [])
            loan = None
            for row in tables[0]["data"]:
                if "融資金額" in row[0]:
                    loan = float(row[5].replace(",", "")) * 1000  # 仟元→元
            lots = {}
            if loan and len(tables) > 1:
                for row in tables[1]["data"]:
                    code = row[0].strip()
                    if len(row) > 6:
                        lots[code] = row[6].replace(",", "")
            ratio = TWMR.compute_ratio(loan, lots, price) if loan else None
            if ratio is not None:
                twii_today = _twii_close_map().get(ymd)
                point = {"date": ymd, "ratio": ratio, "twii": twii_today}
    except Exception:
        point = None

    # 種子檔
    seed = None
    seed_path = seed_path or os.path.join(os.path.dirname(__file__), "tw_margin_ratio_seed.json")
    try:
        with open(seed_path, encoding="utf-8") as f:
            seed = json.load(f)
    except Exception:
        seed = None

    # 前版累積
    prev = None
    try:
        pj = json.loads(_g("https://stockview1.pages.dev/data/sentiment.json", 10))
        prev = pj.get("tw_margin_ratio")
    except Exception:
        prev = None

    dates, ratio_s, twii_s = TWMR.merge_history(seed, prev, point, cap=750)
    if not dates:
        return None

    # 補齊缺的 twii(疊圖恆完整):對既有日期用 ^TWII history 補
    if any(t is None for t in twii_s):
        tmap = _twii_close_map()
        twii_s = [twii_s[i] if twii_s[i] is not None else tmap.get(dates[i]) for i in range(len(dates))]

    level = ratio_s[-1]
    diff = round(ratio_s[-1] - ratio_s[-2], 2) if len(ratio_s) >= 2 and ratio_s[-2] is not None else None
    return {
        "as_of": dates[-1], "level": level, "diff": diff,
        "dates": dates, "ratio": ratio_s, "twii": twii_s,
        "note": "上市·不含ETF·斷頭壓力", "unit": "%",
        "read": "<130% 斷頭警戒(常見底部);上市口徑,絕對值略高於含上櫃版",
        "src": "TWSE STOCK_DAY_ALL + MI_MARGN(每日自算)· 歷史回補 FinMind",
        "url": "https://www.macromicro.me/charts/53117/taiwan-taiex-maintenance-margin",
    }
```

- [ ] **Step 2: 於 `build()` 掛上新 key**

在 `engine/export_sentiment.py` 的 `build()` 內(約 export_sentiment.py:1168 附近,`levels, failed = fetch_levels()` 之後、組 output dict 處),加入:

```python
    tw_margin_ratio = fetch_tw_margin_ratio()
```
並在最後回傳/組裝 output 的 dict 裡加一行(找到 `"levels": levels,` 那個 dict,加入):
```python
        "tw_margin_ratio": tw_margin_ratio,
```

- [ ] **Step 3: 語法檢查 + 匯入檢查**

Run: `cd engine && python -c "import ast,sys; ast.parse(open('export_sentiment.py',encoding='utf-8').read()); print('AST_OK')"`
Expected: `AST_OK`

- [ ] **Step 4: Commit**

```bash
git add engine/export_sentiment.py
git commit -m "feat(engine): wire TW margin maintenance ratio into sentiment.json build"
```

*(注:實際跑 export 產出驗證放 Task 5;此處只確保接線與語法。)*

---

### Task 3: 一次性 FinMind 回補腳本 + 產出種子檔

**Files:**
- Create: `engine/backfill_tw_margin_ratio.py`
- Create (產物): `engine/tw_margin_ratio_seed.json`

**Interfaces:**
- Consumes: `tw_margin_ratio.compute_ratio`
- Produces: `tw_margin_ratio_seed.json = {method, generated_at, dates[], ratio[], twii[]}`

**注意:** 本任務含真實網路呼叫(FinMind 匿名 + yfinance),無法純單元測試 → 採「探測 schema → 逐日回補(可續跑)→ seam 驗證」的 run-and-observe。

- [ ] **Step 1: 探測 FinMind 欄位(確認 dataset 欄名/單位)**

Create `engine/backfill_tw_margin_ratio.py`(先只放探測 main;完整版於 Step 2 覆蓋):

```python
# -*- coding: utf-8 -*-
"""一次性:用 FinMind 匿名 API 回補近 1 年台股大盤融資維持率(上市),產出 tw_margin_ratio_seed.json。
本機執行:python backfill_tw_margin_ratio.py --probe   # 先看欄位
         python backfill_tw_margin_ratio.py           # 正式回補(可重跑續補)"""
import sys, json, time, os, urllib.request, urllib.parse

FINMIND = "https://api.finmindtrade.com/api/v4/data"


def fm(dataset, start_date=None, end_date=None, data_id=None, retries=4):
    q = {"dataset": dataset}
    if start_date: q["start_date"] = start_date
    if end_date: q["end_date"] = end_date
    if data_id: q["data_id"] = data_id
    url = FINMIND + "?" + urllib.parse.urlencode(q)
    for i in range(retries):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
            j = json.loads(raw.decode("utf-8", "ignore"))
            if j.get("status") == 200 or j.get("data"):
                return j.get("data", [])
            # 429/限流
            time.sleep(20 * (i + 1))
        except Exception:
            time.sleep(15 * (i + 1))
    return []


def _probe():
    for ds in ["TaiwanStockMarginPurchaseShortSale", "TaiwanStockTotalMarginPurchaseShortSale", "TaiwanStockInfo"]:
        rows = fm(ds, start_date="2026-07-04", end_date="2026-07-06") if ds != "TaiwanStockInfo" else fm(ds)
        print("===", ds, "n=", len(rows))
        if rows:
            print("   欄位:", list(rows[0].keys()))
            print("   sample:", json.dumps(rows[0], ensure_ascii=False)[:300])


if __name__ == "__main__":
    if "--probe" in sys.argv:
        _probe()
```

Run: `cd engine && python backfill_tw_margin_ratio.py --probe`
Expected: 印出三個 dataset 的欄位。**確認**:
- `TaiwanStockMarginPurchaseShortSale` 有 `date, stock_id, MarginPurchaseTodayBalance`(融資今日餘額;確認單位是「張」——與 TWSE MI_MARGN 逐檔張對齊)。
- `TaiwanStockTotalMarginPurchaseShortSale` 有市場合計「融資今日餘額金額」欄(作分母;若單位為元則直接用,為仟元則 ×1000)。
- `TaiwanStockInfo` 有 `type`(twse=上市 / tpex=上櫃)可篩上市。

若欄名/單位與上述不同,於 Step 2 對應調整(見程式內 TODO 標記處)。

- [ ] **Step 2: 完成回補主程式(可續跑)**

覆蓋 `engine/backfill_tw_margin_ratio.py`,在探測版之上加入正式回補(沿用 `fm`):

```python
import datetime as _dt
sys.path.insert(0, os.path.dirname(__file__))
import tw_margin_ratio as TWMR

SEED_PATH = os.path.join(os.path.dirname(__file__), "tw_margin_ratio_seed.json")


def _twse_listed():
    """FinMind 上市(twse)代號集合。"""
    info = fm("TaiwanStockInfo")
    return {r["stock_id"] for r in info if r.get("type") == "twse"}


def _twii_map(start):
    try:
        import yfinance as yf
        h = yf.Ticker("^TWII").history(start=start, auto_adjust=False)
        return {idx.strftime("%Y%m%d"): round(float(row["Close"]), 2)
                for idx, row in h.iterrows() if row.get("Close") == row.get("Close")}
    except Exception:
        return {}


def backfill(days=250):
    listed = _twse_listed()
    end = _dt.date(2026, 7, 6)                 # 固定基準日(避免 Date.now;實跑可改參數)
    start = end - _dt.timedelta(days=int(days * 1.5) + 10)
    s_iso, e_iso = start.isoformat(), end.isoformat()

    # 分母:市場合計融資金額,整段一次抓 → {YYYYMMDD: loan_yuan}
    tot = fm("TaiwanStockTotalMarginPurchaseShortSale", s_iso, e_iso)
    loan_by_day = {}
    for r in tot:
        # TODO(Step1 確認欄名):融資今日餘額金額欄;若單位仟元 ×1000
        v = r.get("MarginPurchaseTodayBalanceAmount") or r.get("TodayBalance") or r.get("MarginPurchaseMoney")
        d = str(r.get("date", "")).replace("-", "")
        if v not in (None, "") and d:
            loan_by_day[d] = float(v)

    # 逐檔融資餘額(整段一次抓,依日分組)
    mg = fm("TaiwanStockMarginPurchaseShortSale", s_iso, e_iso)
    lots_by_day = {}
    for r in mg:
        sid = r.get("stock_id")
        if sid not in listed:
            continue
        d = str(r.get("date", "")).replace("-", "")
        bal = r.get("MarginPurchaseTodayBalance")
        if d and bal not in (None, ""):
            lots_by_day.setdefault(d, {})[sid] = bal

    # 逐檔收盤(整段一次抓,依日分組)
    px = fm("TaiwanStockPrice", s_iso, e_iso)
    price_by_day = {}
    for r in px:
        sid = r.get("stock_id")
        if sid not in listed:
            continue
        d = str(r.get("date", "")).replace("-", "")
        c = r.get("close")
        if d and c not in (None, ""):
            price_by_day.setdefault(d, {})[sid] = c

    twii = _twii_map(s_iso)
    dates = sorted(set(loan_by_day) & set(lots_by_day) & set(price_by_day))
    out_dates, out_ratio, out_twii = [], [], []
    for d in dates:
        r = TWMR.compute_ratio(loan_by_day[d], lots_by_day[d], price_by_day[d])
        if r is not None:
            out_dates.append(d); out_ratio.append(r); out_twii.append(twii.get(d))
    out_dates, out_ratio, out_twii = out_dates[-days:], out_ratio[-days:], out_twii[-days:]
    seed = {"method": "上市·不含ETF·Σ(融資張×1000×close)/融資金額×100 (FinMind 回補)",
            "generated_at": end.isoformat(), "dates": out_dates, "ratio": out_ratio, "twii": out_twii}
    with open(SEED_PATH, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False)
    print(f"寫入 {SEED_PATH}: {len(out_dates)} 日, 最後 {out_dates[-1]}={out_ratio[-1]}%")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        _probe()
    else:
        backfill(250)
```

*若 FinMind 匿名對「整段一次抓」回傳截斷(資料量不足/status≠200),改為逐日迴圈:`for each trading day: fm(ds, d, d, ...)` 並在每日後 `time.sleep(2)`;已成功日寫入暫存 `._twmr_cache.json`,重跑時略過。(逐日退路;整段可行則不需。)*

- [ ] **Step 3: 執行回補**

Run: `cd engine && python backfill_tw_margin_ratio.py`
Expected: 印出「寫入 …: ~250 日, 最後 20260706=<值>%」

- [ ] **Step 4: Seam 驗證(對錨點 194.55%)**

Run:
```bash
cd engine && python -c "
import json; d=json.load(open('tw_margin_ratio_seed.json',encoding='utf-8'))
i=d['dates'].index('20260706'); print('20260706 =', d['ratio'][i], '% (錨點 194.55)')
assert abs(d['ratio'][i]-194.55) < 3, '偏離錨點過大,檢查上市/ETF過濾與分母單位'
print('SEAM_OK')"
```
Expected: `SEAM_OK`(容許 ±3pt;若失敗 → 回 Step 2 檢查 `type=='twse'` 過濾、ETF 排除、分母仟元/元、餘額張/股單位)

- [ ] **Step 5: Commit**

```bash
git add engine/backfill_tw_margin_ratio.py engine/tw_margin_ratio_seed.json
git commit -m "feat(engine): one-time FinMind backfill (1y) + seed for TW margin ratio"
```

---

### Task 4: 前端大圖(load/render/draw + 掛載 + DOM 測試)

**Files:**
- Modify: `web/index.html`(新增三函式、renderSentiment 掛 block、loadSentiment 呼叫)
- Test: `web/test_tw_margin_dom.mjs`

**Interfaces:**
- Consumes: `updStamp(asOf)`(已存在)、sentiment.json `tw_margin_ratio`
- Produces: 全域 `TWMR_DATA/TWMR_WIN`;函式 `loadTwMarginRatio/renderTwMarginRatio/drawTwMarginRatioChart`;DOM `#twMarginRatioBlock` / `#twMarginRatioChart`

- [ ] **Step 1: 寫失敗的 DOM 測試**

Create `web/test_tw_margin_dom.mjs`:

```javascript
// 抽出 renderTwMarginRatio + updStamp,stub 最小 DOM/echarts,斷言輸出含標題/更新時間/130%/現值。
import { readFileSync } from "node:fs";
import assert from "node:assert";
const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
function extract(name){
  const s = html.indexOf("function " + name);
  if (s < 0) throw new Error("缺函式 " + name);
  const o = html.indexOf("{", s);
  let d = 0;
  for (let i = o; i < html.length; i++){
    if (html[i] === "{") d++;
    else if (html[i] === "}"){ d--; if (d===0) return html.slice(s, i+1); }
  }
  throw new Error("不平衡 " + name);
}
const stub = `
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let CAP='';
const $ = sel => ({ set innerHTML(v){ CAP=v; }, get innerHTML(){ return CAP; }, querySelectorAll(){ return []; } });
const document = { getElementById(){ return null; } };  // draw 早退(!el)
const window = {};                                       // 無 echarts → draw 早退
`;
const src = stub + extract("updStamp") + "\nlet TWMR_DATA=null, TWMR_WIN='all';\n"
  + "const TWMR_WINS=[['1m',21,'1M'],['3m',63,'3M'],['6m',126,'6M'],['1y',252,'1Y'],['all',Infinity,'全部']];\n"
  + extract("renderTwMarginRatio") + extract("drawTwMarginRatioChart")
  + "\nrenderTwMarginRatio({as_of:'20260706',level:194.55,diff:-0.8,"
  + "dates:['20260702','20260703','20260706'],ratio:[195.1,195.3,194.55],twii:[23400,23450,23380],"
  + "src:'TWSE'});\nglobalThis.__OUT=CAP;\n";
const fn = new Function(src + "return globalThis.__OUT;");
const out = fn();
assert.ok(out.includes("台股大盤融資維持率"), "缺標題");
assert.ok(out.includes("更新時間:星期"), "缺更新時間戳(星期)");
assert.ok(out.includes("194.55"), "缺現值");
assert.ok(out.includes("130%") || out.includes("斷頭"), "缺 130% 說明");
assert.ok(out.includes("data-twmrw"), "缺時間按鈕");
console.log("TW_MARGIN_DOM_OK");
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `node web/test_tw_margin_dom.mjs`
Expected: FAIL —「缺函式 renderTwMarginRatio」

- [ ] **Step 3: 新增三函式到 `web/index.html`**

在 `renderInsider` 函式結尾之後(約 export 前 web/index.html:2554 附近,即 `function renderInsider(){…}` 區塊之後、`function renderSentiment` 之前的空白處)插入:

```javascript
// ── 台股大盤融資維持率(上市·自算)+ 加權指數疊圖 ──
let TWMR_DATA=null, TWMR_WIN="all";
const TWMR_WINS=[["1m",21,"1M"],["3m",63,"3M"],["6m",126,"6M"],["1y",252,"1Y"],["all",Infinity,"全部"]];
async function loadTwMarginRatio(){
  const box=$("#twMarginRatioBlock"); if(!box) return;
  if(TWMR_DATA){ renderTwMarginRatio(TWMR_DATA); return; }
  try{
    const res=await fetch("data/sentiment.json?t="+Date.now(),{cache:"no-store"});
    if(!res.ok) throw new Error(res.status);
    const j=await res.json();
    TWMR_DATA=j.tw_margin_ratio||null;
    if(TWMR_DATA) renderTwMarginRatio(TWMR_DATA);
  }catch(e){}
}
function renderTwMarginRatio(d){
  const box=$("#twMarginRatioBlock"); if(!box||!d||!d.dates||!d.dates.length) return;
  const cur=d.level, chg=d.diff;
  const chgCls=chg>0?"pos":(chg<0?"neg":"dim");
  const card='border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--panel);display:inline-block;min-width:110px;margin-right:12px';
  const n=d.dates.length;
  const btns=TWMR_WINS.filter(w=>w[1]===Infinity||w[0]==="1m"||w[1]<=n).map(w=>'<button class="ntab'+(TWMR_WIN===w[0]?' on':'')+'" data-twmrw="'+w[0]+'">'+w[2]+'</button>').join("");
  box.innerHTML=
    '<section>'+
      '<div class="sec-head"><h2>台股大盤融資維持率</h2>'+
        '<span class="tag">上市·不含ETF·自算·日頻</span>'+
        '<span class="hint">融資買進股票現值 ÷ 融資金額。越低代表融資戶帳面虧損越大;跌破 130% 近斷頭警戒(常見底部)。</span></div>'+
      updStamp(d.as_of)+
      '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:8px">'+
        '<div style="'+card+'"><div class="cap-lab">最新維持率</div><div class="cap-big" style="color:#0d9488">'+(cur==null?'—':Number(cur).toFixed(2)+'%')+'</div></div>'+
        '<div style="'+card+'"><div class="cap-lab">日變化</div><div class="cap-big '+chgCls+'">'+(chg==null?'—':(chg>0?'+':'')+Number(chg).toFixed(2))+'</div></div>'+
      '</div>'+
      '<div style="margin:6px 0 8px;display:flex;gap:6px;flex-wrap:wrap">'+btns+'</div>'+
      '<div id="twMarginRatioChart" class="cap-chart" style="height:260px"></div>'+
      '<div class="legend" style="margin-top:10px">維持率(左軸,粗線)＋ <b style="color:#94a3b8">灰虛線=加權指數(右軸)</b>。上市口徑、分子不含 ETF、每日自 TWSE 收盤+融資餘額換算,絕對值略高於含上櫃版;看趨勢與相對高低。灰虛線 <b style="color:#e11d48">130%</b> = 斷頭警戒參考。來源:'+esc(d.src||"TWSE")+'。</div>'+
    '</section>';
  box.querySelectorAll("[data-twmrw]").forEach(b=>b.onclick=()=>{ TWMR_WIN=b.dataset.twmrw||"all"; renderTwMarginRatio(TWMR_DATA); });
  drawTwMarginRatioChart(d);
}
function drawTwMarginRatioChart(d){
  const el=document.getElementById("twMarginRatioChart");
  if(!el||!window.echarts) return;
  const win=TWMR_WINS.find(w=>w[0]===TWMR_WIN)||TWMR_WINS[TWMR_WINS.length-1];
  const nn=win[1]===Infinity?d.dates.length:Math.min(win[1],d.dates.length);
  const dates=d.dates.slice(-nn), ratio=d.ratio.slice(-nn), twii=(d.twii||[]).slice(-nn);
  const hasIdx=twii.some(v=>v!=null&&isFinite(Number(v)));
  const _old=echarts.getInstanceByDom(el); if(_old) _old.dispose();
  const ch=echarts.init(el,null,{renderer:"canvas"});
  const toMs=s=>{const t=String(s);return new Date(t.slice(0,4)+"-"+t.slice(4,6)+"-"+t.slice(6,8)+"T00:00:00").getTime();};
  ch.setOption({
    grid:{left:52,right:hasIdx?58:16,top:16,bottom:26},
    tooltip:{trigger:"axis",axisPointer:{type:"cross"}},
    legend:{data:["融資維持率"].concat(hasIdx?["加權指數"]:[]),top:0,right:0,itemWidth:16,itemHeight:8,textStyle:{fontSize:10}},
    xAxis:{type:"time",axisLabel:{fontSize:9,hideOverlap:true,
      formatter:val=>{const dt=new Date(val);const m=dt.getMonth();return m===0?dt.getFullYear()+"年":(m+1)+"月";}}},
    yAxis:[
      {type:"value",name:"%",scale:true,nameTextStyle:{fontSize:10},axisLabel:{fontSize:10,formatter:x=>x+"%"},splitLine:{lineStyle:{opacity:.3}}},
      {type:"value",scale:true,show:hasIdx,axisLabel:{fontSize:9,formatter:x=>(x/1000).toFixed(0)+"k"},splitLine:{show:false}}
    ],
    series:[
      {name:"融資維持率",type:"line",smooth:true,showSymbol:false,yAxisIndex:0,
        data:dates.map((s,i)=>[toMs(s),ratio[i]]),
        lineStyle:{color:"#0d9488",width:2},itemStyle:{color:"#0d9488"},areaStyle:{color:"#0d9488",opacity:.07},
        markLine:{symbol:"none",silent:true,label:{formatter:"130% 斷頭警戒",color:"#e11d48",fontSize:10,position:"insideEndTop"},
          lineStyle:{color:"#e11d48",type:"dashed",width:1.2,opacity:.85},data:[{yAxis:130}]}}
    ].concat(hasIdx?[{name:"加權指數",type:"line",smooth:true,showSymbol:false,yAxisIndex:1,
        data:dates.map((s,i)=>[toMs(s),twii[i]]),lineStyle:{color:"#94a3b8",type:"dashed",width:1.2},itemStyle:{color:"#94a3b8"}}]:[])
  },true);
  if(!el._ro){el._ro=()=>ch.resize();window.addEventListener("resize",el._ro);}
}
```

- [ ] **Step 4: 掛載 block + 呼叫 loader**

在 `renderSentiment` 的 `$("#sentBox").innerHTML` block 清單中,`'<div id="marginBlock"></div>'+`(web/index.html:2567 附近)之後插入一行:
```javascript
    '<div id="twMarginRatioBlock"></div>'+
```
在 `loadSentiment()` 內(web/index.html:2777 附近,`loadMargin();` 之後)插入:
```javascript
    loadTwMarginRatio();
```

- [ ] **Step 5: 執行測試確認通過 + 整檔語法檢查**

Run: `node web/test_tw_margin_dom.mjs`
Expected: `TW_MARGIN_DOM_OK`

Run(整檔 script 語法):
```bash
cd web && node -e "const fs=require('fs');const h=fs.readFileSync('index.html','utf8');const m=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]).sort((a,b)=>b.length-a.length)[0];fs.writeFileSync(process.env.TEMP+'/_sv2.js',m);require('child_process').execSync('node --check '+process.env.TEMP+'/_sv2.js');console.log('NODE_SYNTAX_OK')"
```
Expected: `NODE_SYNTAX_OK`

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/test_tw_margin_dom.mjs
git commit -m "feat(web): 台股大盤融資維持率 big chart (time buttons + TAIEX overlay + updStamp)"
```

---

### Task 5: 整合驗證 + 部署說明

**Files:** 無(驗證與文件)

- [ ] **Step 1: 本機跑一次 export 產出 sentiment.json 並檢查新 key**

Run(僅情緒指標,不重抓全市場):
```bash
cd engine && python export_sentiment.py 2>&1 | tail -5
python -c "
import json; d=json.load(open('../web/data/sentiment.json',encoding='utf-8'))
t=d.get('tw_margin_ratio'); assert t, '缺 tw_margin_ratio'
print('as_of',t['as_of'],'level',t['level'],'n',len(t['dates']),'twii完整', all(x is not None for x in t['twii']))
assert len(t['dates'])>=200 and t['level']>100
print('EXPORT_OK')"
```
Expected: `EXPORT_OK`,且 `as_of` 為最近交易日、`n≥200`、`twii完整 True`
*(若 `export_sentiment.py` 有 skip 參數只跑本段,依該檔慣例帶上;否則整跑。)*

- [ ] **Step 2: 本機開站目視**

Run: `cd web && python -m http.server 8099`,瀏覽器開 `http://localhost:8099` → 總體市場分頁 → 捲到「台股大盤融資維持率」:確認 (a) 標題/tag/hint、(b)「資料週期 … · 更新時間:星期X」、(c) 現值卡、(d) 時間按鈕可切換且只重繪本圖、(e) 維持率線 + 灰虛線加權指數(右軸)+ 130% 紅虛線。

- [ ] **Step 3: 部署(需使用者確認後)**

```bash
git push -u origin feat-tw-margin-maintenance-ratio
# 合併 main 後(單人 repo 可直推),手動觸發(無 push 自動部署):
gh workflow run export-and-deploy.yml --ref main -f skip_stocks=true
```

## Self-Review 註記
- 涵蓋 spec 各節:口徑(Global Constraints + Task1/3)、每日(Task2)、回補+接縫驗證(Task3)、輸出結構(Task2)、前端圖(Task4)、部署(Task5)。
- FinMind 欄名/單位在 Task3 Step1 探測確認,程式內標 TODO;seam 驗證(Step4)兜底。
- 型別一致:`compute_ratio`/`merge_history` 簽名於 Task1 定義,Task2/3 沿用;前端 `TWMR_*`、`#twMarginRatioBlock/Chart` 命名前後一致。

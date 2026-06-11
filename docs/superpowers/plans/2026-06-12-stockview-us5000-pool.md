# stockview「5000股」全美股金叉池 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 stockview 金叉訊號頁 SP600 右邊新增兩個輕量金叉池——「5000股」(全美股~3000,門檻過濾)與「台股全市場」(上市櫃~1800,不過濾)。皆 1年日線→EMA20/60金叉→只清單不回測,各自收盤後解耦獨立排程部署。

**Architecture:** 全新**通用** `engine/export_lite_pool.py`(us5000 + tw_all 兩池共用)重用 `adr_screen.compute_trend`(1年, 分批)取 cross_state/cross_days，套各池門檻，再用 `export_json.build_cross_signals(rows, downloader=offline_stub)` 產生**無回測** cross_signals。前端 POOLS 加 `us5000`/`tw_all` + label map + lite 走 renderCross(withBacktest=false)。兩個獨立 workflow(美股/台股收盤後 cron)：pull_live 沿用其他池 → 覆蓋本池 → 全快照部署。**現有 export_json.run_pool / 40分 workflow 完全不動。**

**Tech Stack:** Python 3.11, yfinance, pandas；既有引擎 adr_screen / export_json；前端 web/index.html；GitHub Actions + Cloudflare Pages (wrangler)。

**Spec:** `docs/superpowers/specs/2026-06-12-stockview-us5000-pool-design.md`

---

## 環境約定
- repo：`C:/Users/u9914/adr-trend-web`（bash 用 `~/adr-trend-web` 或 `/c/Users/u9914/adr-trend-web`）。
- 引擎用系統/CI Python(裝 yfinance+pandas)；本機驗證可用 `~/openbb_env/Scripts/python.exe`(已有 yfinance/pandas)。
- 測試風格沿用 repo 既有：**純 assert、無 pytest 框架**，`cd engine && python test_xxx.py` 跑、印 `OK`。
- 改檔避免 Write 工具中文路徑 mojibake：用 Bash heredoc 或既有編輯方式；改完以 `python -c "open(...,encoding='utf-8')"` 驗無亂碼。
- 既有測試別弄壞：`cd engine && python test_cross_signals.py` 必須仍 `OK`。

## 檔案結構（職責）
| 檔案 | 動作 | 職責 |
|---|---|---|
| `engine/universe/us5000.txt` | 新增(版控) | 全美股 ~5500 代號靜態快照(借 skill 產生) |
| `engine/adr_screen.py` | 改(1 行 additive) | compute_trend 列加 `close`(供 price 門檻) |
| `engine/universe/tw_all.txt` | 新增(版控) | 台股全上市櫃 ~1800 代號(tw_names.json 濾普通股) |
| `engine/export_lite_pool.py` | 新增 | 通用:批次 compute_trend + 門檻 + build_cross_signals(offline) → data/<pool>.json |
| `engine/test_export_lite_pool.py` | 新增 | 注入 fake compute 測門檻/輸出/lite flag(us5000 有濾、tw_all 不濾) |
| `web/index.html` | 改 | POOLS 加 us5000+tw_all + label map + lite 渲染 |
| `.github/workflows/export-us5000.yml` | 新增 | 美股收盤後 cron：pull_live→export_lite_pool us5000→deploy |
| `.github/workflows/export-tw-all.yml` | 新增 | 台股收盤後 cron：pull_live→export_lite_pool tw_all→deploy |

---

## Task 1: 產生 engine/universe/us5000.txt（借 skill 全美股清單）

**Files:**
- Create: `engine/universe/us5000.txt`

- [ ] **Step 1: 由 skill 既有清單轉出 us5000.txt（含檔頭，格式相容 load_pool）**

skill 已產出 `~/.claude/skills/golden-cross-screener/universe/us_all.txt`（5579 檔，已排 ETF/權證/單位/特別股）。bash：
```
src=~/.claude/skills/golden-cross-screener/universe/us_all.txt
dst=~/adr-trend-web/engine/universe/us5000.txt
{
  echo "# us5000 全美股普通股快照 (借 golden-cross-screener / Nasdaq Trader)"
  echo "# 排除 ETF/test/warrant/unit/right/preferred; 門檻(price/dolvol)在 export 時套"
  grep -vE '^#' "$src" | grep -E '^[A-Z]' 
} > "$dst"
echo "lines: $(grep -cE '^[A-Z]' "$dst")"
```
Expected：印出 ~5500（lines）。

- [ ] **Step 2: 驗證 load_pool 能讀（格式相容，會跳 # 註解）**

`cd ~/adr-trend-web/engine && python -c "import adr_screen as e; s=e.load_pool('us5000'); print(len(s), 'AAPL' in s, 'NVDA' in s, 'QQQ' in s)"`
Expected：`5500 左右 True True False`（含 AAPL/NVDA、不含 ETF QQQ）。若 `load_pool` 不跳 `#` 註解（symbols 含 '#...'）→ 改 Step 1 去掉檔頭兩行只留代號，重跑。

- [ ] **Step 3: Commit**
```bash
cd ~/adr-trend-web && git add engine/universe/us5000.txt && git commit -q -m "data: us5000 全美股 universe 快照(~5500, 借 golden-cross-screener)"
```

---

## Task 2: compute_trend 列加 `close`（additive，供 price 門檻）

**Files:**
- Modify: `engine/adr_screen.py`（compute_trend 的 row dict）
- Test: `engine/test_compute_close.py`

- [ ] **Step 1: 寫失敗測試（monkeypatch _download 回合成 df，驗 row 有 close）**

`engine/test_compute_close.py`:
```python
# -*- coding: utf-8 -*-
"""compute_trend row 應含 close（供 us5000 price 門檻）。cd engine && python test_compute_close.py"""
import pandas as pd, numpy as np
import adr_screen as e

def _fake_df():
    n=70; idx=pd.date_range("2025-01-01", periods=n, freq="D")
    close=pd.Series(np.linspace(100,110,n), index=idx)
    cols=pd.MultiIndex.from_product([["AAA"],["Open","High","Low","Close","Volume"]])
    data={("AAA","Open"):close,("AAA","High"):close*1.01,("AAA","Low"):close*0.99,
          ("AAA","Close"):close,("AAA","Volume"):pd.Series([1_000_000]*n,index=idx)}
    return pd.DataFrame(data, columns=cols)

def test_row_has_close():
    e._download = lambda syms, period="1y": _fake_df()   # monkeypatch 模組級下載
    rows, failed = e.compute_trend(["AAA"])
    assert rows, ("no rows", failed)
    assert "close" in rows[0], rows[0].keys()
    assert abs(rows[0]["close"] - 110.0) < 1e-6, rows[0]["close"]

if __name__=="__main__":
    test_row_has_close(); print("OK")
```

- [ ] **Step 2: 跑測試確認失敗**

`cd ~/adr-trend-web/engine && python test_compute_close.py`
Expected：AssertionError（`'close' not in row`）。

- [ ] **Step 3: 在 compute_trend 的 row dict 加 close（additive）**

`engine/adr_screen.py` 中 compute_trend 的 `rows.append({...})`，把 `"cur":` 那一行前加入 `close`。找：
```python
                         "cross_state": cross_state, "cross_days": cross_days,
                         "cur": "TWD" if is_tw(sym) else "USD"})
```
改成：
```python
                         "cross_state": cross_state, "cross_days": cross_days,
                         "close": float(sub["Close"].iloc[-1]),
                         "cur": "TWD" if is_tw(sym) else "USD"})
```

- [ ] **Step 4: 跑測試確認通過 + 既有測試不破**

`cd ~/adr-trend-web/engine && python test_compute_close.py && python test_cross_signals.py`
Expected：兩個都印 `OK`。

- [ ] **Step 5: Commit**
```bash
cd ~/adr-trend-web && git add engine/adr_screen.py engine/test_compute_close.py && git commit -q -m "feat(engine): compute_trend row 加 close 欄(供 us5000 price 門檻)"
```

---

## Task 3: 產生 engine/universe/tw_all.txt（台股全上市櫃普通股）

**Files:**
- Create: `engine/universe/tw_all.txt`

- [ ] **Step 1: 從 tw_names.json keys 濾出普通股（4 位數、非 0 開頭；排 ETF 00xx / 6 位數權證）**

`tw_names.json` 的 key 已帶 .TW/.TWO 後綴。bash(用引擎 python 解析較穩)：
```
cd ~/adr-trend-web/engine
python - <<'PY'
import json, io, re, os
names = json.load(io.open("universe/tw_names.json", encoding="utf-8"))
out = []
for k in names:                       # k 如 "2330.TW" / "6415.TWO"
    code = k.split(".")[0]
    if re.fullmatch(r"[1-9]\d{3}", code):   # 4 位數、非 0 開頭=普通股(排 00xx ETF、6 位權證)
        out.append(k)
out = sorted(set(out))
with io.open("universe/tw_all.txt", "w", encoding="utf-8", newline="\n") as f:
    f.write("# 台股全上市(.TW)+上櫃(.TWO)普通股快照 (來源 tw_names.json / TWSE ISIN)\n")
    f.write("# 濾掉 ETF(00xx) 與 6 位數權證; 不過濾股價/成交額(掃描時不設門檻)\n")
    for s in out:
        f.write(s + "\n")
print("tw_all:", len(out), "sample:", out[:5])
PY
```
Expected：印出 ~1700–1900 檔，sample 形如 `['1101.TW','1102.TW',...]`。

- [ ] **Step 2: 驗證 load_pool 能讀**

`cd ~/adr-trend-web/engine && python -c "import adr_screen as e; s=e.load_pool('tw_all'); print(len(s), '2330.TW' in s, '0050.TW' in s)"`
Expected：`~1800 True False`（含台積電 2330、不含 ETF 0050）。

- [ ] **Step 3: Commit**
```bash
cd ~/adr-trend-web && git add engine/universe/tw_all.txt && git commit -q -m "data: tw_all 台股全上市櫃普通股 universe 快照(~1800)"
```

---

## Task 4: 通用輕量引擎 engine/export_lite_pool.py

**Files:**
- Create: `engine/export_lite_pool.py`
- Test: `engine/test_export_lite_pool.py`

- [ ] **Step 1: 寫失敗測試（純 assert，注入 fake compute；驗門檻/lite/無回測欄）**

`engine/test_export_lite_pool.py`:
```python
# -*- coding: utf-8 -*-
"""export_lite_pool 單元測試。cd engine && python test_export_lite_pool.py"""
import os, tempfile
import export_lite_pool as L

def _row(sym, state, days, close, dv, cur="USD"):
    return {"sym": sym, "cross_state": state, "cross_days": days, "close": close,
            "dv": dv, "score": 1.0, "sc5": 50.0, "r5": 1.0,
            "e5": 0.3, "e20": 0.2, "a20": 5.0, "cur": cur}

def _fake_compute(syms):
    data = {"HI":  _row("HI",  "golden", 1, 100.0, 5e7),
            "LOWP":_row("LOWP","golden", 0,   2.0, 5e7),    # 低價
            "LOWV":_row("LOWV","golden", 0, 100.0, 1e6),    # 低量
            "DEAD":_row("DEAD","death",  2,  80.0, 5e7)}
    return [data[s] for s in syms if s in data], []

def test_us5000_filters_and_lite():
    tmp = tempfile.mkdtemp()
    pl = L.run_lite_pool("us5000", "5000股", 5.0, 5e6, "USD",
                         symbols=["HI","LOWP","LOWV","DEAD"],
                         compute=_fake_compute, out_dir=tmp)
    assert pl["lite"] is True, pl
    assert pl["pool_label"] == "5000股"
    gold = [r["sym"] for r in pl["cross_signals"]["golden"]]
    assert "HI" in gold, gold
    assert "LOWP" not in gold and "LOWV" not in gold, gold      # 門檻濾掉
    assert "bt_win_rate" not in pl["cross_signals"]["golden"][0] # 無回測欄
    assert os.path.exists(os.path.join(tmp, "us5000.json"))

def test_tw_all_no_filter():
    tmp = tempfile.mkdtemp()
    pl = L.run_lite_pool("tw_all", "台股全市場", 0.0, 0.0, "TWD",
                         symbols=["HI","LOWP","LOWV","DEAD"],
                         compute=_fake_compute, out_dir=tmp)
    gold = set(r["sym"] for r in pl["cross_signals"]["golden"])
    assert gold == {"HI","LOWP","LOWV"}, gold     # 不過濾,三檔金叉全留
    assert pl["pool_label"] == "台股全市場"

if __name__ == "__main__":
    test_us5000_filters_and_lite(); test_tw_all_no_filter(); print("OK")
```

- [ ] **Step 2: 跑測試確認失敗**

`cd ~/adr-trend-web/engine && python test_export_lite_pool.py`
Expected：`ModuleNotFoundError: No module named 'export_lite_pool'`。

- [ ] **Step 3: 實作 export_lite_pool.py**

`engine/export_lite_pool.py`:
```python
# -*- coding: utf-8 -*-
"""輕量金叉池匯出(us5000 / tw_all):1年日線→EMA20/60金叉→門檻→cross_signals(無回測)。
重用 adr_screen.compute_trend(分批) + export_json.build_cross_signals(offline downloader→不跑5年回測)。
不改動 export_json.run_pool / 40分流程。
用法: python export_lite_pool.py <us5000|tw_all>
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import adr_screen as eng
import export_json as ej

DATA_DIR = os.path.join(HERE, "..", "data")

PRESETS = {
    "us5000": {"label": "5000股",     "min_price": 5.0, "min_dolvol": 5e6, "cur": "USD"},
    "tw_all": {"label": "台股全市場", "min_price": 0.0, "min_dolvol": 0.0, "cur": "TWD"},
}

def _offline(syms):
    raise RuntimeError("lite pool: no 5y backtest")

def run_lite_pool(pool, label, min_price=0.0, min_dolvol=0.0, default_cur="USD",
                  symbols=None, compute=None, out_dir=None, batch=300):
    compute = compute or eng.compute_trend
    if symbols is None:
        symbols = eng.load_pool(pool)
        if symbols is None:
            raise SystemExit(f"找不到池清單: {pool}")
    rows, failed = [], []
    for i in range(0, len(symbols), batch):
        r, f = compute(symbols[i:i + batch])
        rows += r
        failed += f
        print(f"[lite:{pool}] {min(i + batch, len(symbols))}/{len(symbols)}", flush=True)
    rows = [r for r in rows
            if r.get("close", 1e18) >= min_price and r.get("dv", 0.0) >= min_dolvol]
    cs = ej.build_cross_signals(rows, downloader=_offline)   # offline → 無 bt_ 欄
    payload = {
        "pool": pool, "pool_label": label, "lite": True,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily 1y, no backtest)",
        "n_list": len(symbols), "n_ok": len(rows),
        "currencies": sorted(set(r["cur"] for r in rows)) or [default_cur],
        "cross_signals": cs,
        "failed": [{"sym": s, "why": w} for s, w in failed],
    }
    out_dir = out_dir or DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, f"{pool}.json")
    with io.open(fp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"[lite:{pool}] -> {fp}  ({payload['n_ok']}/{payload['n_list']} ok, "
          f"金叉{cs['n_golden']}/死叉{cs['n_death']})", flush=True)
    return payload

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in PRESETS:
        print("用法: python export_lite_pool.py <us5000|tw_all>")
        raise SystemExit(1)
    pool = sys.argv[1]
    p = PRESETS[pool]
    run_lite_pool(pool, p["label"], p["min_price"], p["min_dolvol"], p["cur"])

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑測試確認通過 + 既有測試不破**

`cd ~/adr-trend-web/engine && python test_export_lite_pool.py && python test_cross_signals.py`
Expected：兩個都印 `OK`。

- [ ] **Step 5: Commit**
```bash
cd ~/adr-trend-web && git add engine/export_lite_pool.py engine/test_export_lite_pool.py && git commit -q -m "feat(engine): 通用 export_lite_pool(us5000/tw_all, 1年無回測)"
```

---

## Task 5: 前端 web/index.html — 加兩池 + label + lite 渲染

**Files:**
- Modify: `web/index.html`（POOLS 陣列、tab 渲染、池載入 dispatch、renderCross 兩處 withBacktest）

說明：前端無單元測試框架，本 Task 用「精確字串替換 + grep 驗證」驗收；完整 UX 在 Task 7 部署後驗。所有替換用 python 讀寫(UTF-8)避免亂碼。

- [ ] **Step 1: POOLS 陣列加 us5000 + tw_all，並加 label map（約 535 行）**

找：`const POOLS = ["tw150","ndx100","sp500","sp400","sp600"];`
換成兩行：
`const POOLS = ["tw150","ndx100","sp500","sp400","sp600","us5000","tw_all"];`
`const POOL_LABELS = {us5000:"5000股", tw_all:"台股全市場"};`

- [ ] **Step 2: tab 文字用 label map（約 594 行）**

把該行的 `+p.toUpperCase()+` 改為 `+(POOL_LABELS[p]||p.toUpperCase())+`（其餘不動）。

- [ ] **Step 3: lite 池一律走 renderCross（約 2596 行）**

找：`if(TREND_SUB==="cross") renderCross(d); else render(d);`
換成：`if(TREND_SUB==="cross"||d.lite) renderCross(d); else render(d);`
（lite 無 main/rankings，避免 render(d) 壞。）

- [ ] **Step 4: renderCross 兩處回測欄改條件式（`true` → `!d.lite`）**

第一處(🔥剛觸發)：`crossSignalTable("t-cross-fresh", fresh, "近 "+fd+" 日無新交叉觸發。", true)`
→ 末參數 `true` 改 `!d.lite`。
第二處(全部金叉)：`crossSignalTable("t-cross-gold", sortCrossRows(cs.golden), "（本池目前無金叉）", true)`
→ 末參數 `true` 改 `!d.lite`。
（死叉表本就無回測參數，不動。）

- [ ] **Step 5: grep 驗證替換都在**

`cd ~/adr-trend-web && grep -nc 'us5000","tw_all' web/index.html && grep -nc 'POOL_LABELS' web/index.html && grep -nc 'd.lite' web/index.html`
Expected：第一個=1(POOLS)、POOL_LABELS≥2(定義+使用)、d.lite≥3(dispatch + 兩處 !d.lite)。

- [ ] **Step 6: 樣本目視（可選）**

可在 `data/us5000.json` 暫放一份最小 lite 樣本(下列 schema)再本機開站，確認分頁顯示「5000股」、金叉表無回測欄、其他池正常；驗完刪除：
```json
{"pool":"us5000","pool_label":"5000股","lite":true,"generated_at":"2026-06-12T00:00:00Z","source":"yfinance (daily 1y, no backtest)","n_list":3000,"n_ok":1,"currencies":["USD"],"cross_signals":{"fresh_days":3,"n_golden":1,"n_death":0,"golden":[{"sym":"AAPL","name":"AAPL","cross_state":"golden","cross_days":0,"sc5":80,"r5":2.1,"score":50,"e5":0.3,"e20":0.2,"a20":3.0,"cur":"USD"}],"death":[]},"failed":[]}
```

- [ ] **Step 7: Commit**
`cd ~/adr-trend-web && git add web/index.html && git commit -q -m "feat(web): 金叉頁加 5000股/台股全市場 lite 池(label + 無回測渲染)"`

---

## Task 6: 兩個獨立部署 workflow

**Files:**
- Create: `.github/workflows/export-us5000.yml`
- Create: `.github/workflows/export-tw-all.yml`

- [ ] **Step 1: 建 export-us5000.yml（美股收盤後）**

`.github/workflows/export-us5000.yml`:
```yaml
name: export-us5000
# 全美股 ~3000(門檻過濾)輕量金叉池。美股收盤後一天一次,解耦於 40 分主流程。
on:
  schedule:
    - cron: "30 21 * * 1-5"    # 美東收盤後(對齊既有美股那檔)
  workflow_dispatch: {}
permissions:
  contents: read
concurrency:
  group: lite-pool-deploy
  cancel-in-progress: false
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install yfinance pandas
      - name: Pull existing live data
        env:
          PYTHONUTF8: "1"
          PYTHONIOENCODING: "utf-8"
        run: cd engine && python pull_live_data.py || true
      - name: Keep sibling lite pool (tw_all)
        run: curl -fsS "https://stockview1.pages.dev/data/tw_all.json" -o data/tw_all.json || echo "tw_all 尚無(首次)"
      - name: Export us5000 lite pool
        env:
          PYTHONUTF8: "1"
          PYTHONIOENCODING: "utf-8"
          NO_COLOR: "1"
        run: cd engine && python export_lite_pool.py us5000
      - name: Stage web output
        run: |
          mkdir -p public && cp -r web/* public/
          mkdir -p public/data && cp data/*.json public/data/
          cp engine/universe/tw_names.json public/data/tw_names.json || true
          if [ -d data/stock ]; then mkdir -p public/data/stock && cp data/stock/*.json public/data/stock/ || true; fi
      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy public --project-name=${{ vars.CF_PAGES_PROJECT }} --branch=main
```

- [ ] **Step 2: 建 export-tw-all.yml（台股收盤後，僅 cron / curl / pool 名不同）**

`.github/workflows/export-tw-all.yml`:
```yaml
name: export-tw-all
# 台股全上市櫃 ~1800(不過濾)輕量金叉池。台股收盤後一天一次,解耦於 40 分主流程。
on:
  schedule:
    - cron: "30 6 * * 1-5"     # 14:30 台北,台股收盤後
  workflow_dispatch: {}
permissions:
  contents: read
concurrency:
  group: lite-pool-deploy
  cancel-in-progress: false
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install yfinance pandas
      - name: Pull existing live data
        env:
          PYTHONUTF8: "1"
          PYTHONIOENCODING: "utf-8"
        run: cd engine && python pull_live_data.py || true
      - name: Keep sibling lite pool (us5000)
        run: curl -fsS "https://stockview1.pages.dev/data/us5000.json" -o data/us5000.json || echo "us5000 尚無(首次)"
      - name: Export tw_all lite pool
        env:
          PYTHONUTF8: "1"
          PYTHONIOENCODING: "utf-8"
          NO_COLOR: "1"
        run: cd engine && python export_lite_pool.py tw_all
      - name: Stage web output
        run: |
          mkdir -p public && cp -r web/* public/
          mkdir -p public/data && cp data/*.json public/data/
          cp engine/universe/tw_names.json public/data/tw_names.json || true
          if [ -d data/stock ]; then mkdir -p public/data/stock && cp data/stock/*.json public/data/stock/ || true; fi
      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy public --project-name=${{ vars.CF_PAGES_PROJECT }} --branch=main
```

- [ ] **Step 3: 驗證 pull_live_data 會沿用重池**

`cd ~/adr-trend-web && grep -nE "tw150|sp600|index.json|data/|pools" engine/pull_live_data.py | head`
確認會把 5 重池 + index.json 從 live 拉回 data/(lite 兄弟池另由 curl 步驟沿用)。若 pull_live_data 完全不拉重池 → 在 Stage 前比照 sibling 補各重池 curl。

- [ ] **Step 4: Commit**
`cd ~/adr-trend-web && git add .github/workflows/export-us5000.yml .github/workflows/export-tw-all.yml && git commit -q -m "ci: 兩個獨立 lite 池部署 workflow(美股/台股收盤後)"`

---

## Task 7: 上線與驗證

**Files:** 無（操作）

- [ ] **Step 1: 推 main**
`cd ~/adr-trend-web && git push origin main`

- [ ] **Step 2: 首跑 us5000（手動 dispatch）**
`gh workflow run export-us5000.yml --ref main`
等完成：`gh run list --workflow=export-us5000.yml -L1`；失敗看 `gh run view <id> --log-failed`。
Expected：綠;`https://stockview1.pages.dev/data/us5000.json` 含 `"lite":true` 與 `cross_signals.golden`。

- [ ] **Step 3: 首跑 tw_all**
`gh workflow run export-tw-all.yml --ref main`
Expected：`https://stockview1.pages.dev/data/tw_all.json` 含 `pool_label:"台股全市場"`、cur 含 TWD。

- [ ] **Step 4: 站上目視驗收**
開 `https://stockview1.pages.dev/#us5000`：
- SP600 右邊出現「5000股」「台股全市場」兩分頁。
- 「5000股」→ 交叉訊號頁顯示金叉/死叉清單，**無**回測欄(金叉勝率/平均報酬…)。
- 「台股全市場」→ 台股金叉(帶中文名)、TWD。
- 切回 SP600/tw150 → 一切正常(回測欄仍在)。
- 確認 40 分主流程未被觸發。

- [ ] **Step 5: 確認 cron 已排程**
`gh workflow list` 應見 export-us5000 / export-tw-all 兩個 enabled。

---

## 自我檢視（writing-plans self-review）

**Spec 覆蓋：**
- §2/§5 us5000(借 universe、門檻過濾、lite 無回測) → Task 1,2,4
- §9 台股全市場(全上市櫃、不過濾、TW 收盤 cron) → Task 3,4,6
- §5.2 重用 compute_trend + build_cross_signals(offline 無回測) → Task 4
- §5.3 前端 POOLS+label+lite 渲染 → Task 5
- §5.4/§9.3 兩獨立 workflow(pull_live→export→deploy) → Task 6
- 全快照不弄丟其他池(pull_live + sibling curl) → Task 6
- 測試 → Task 2/4 單元 + Task 5 grep + Task 7 站上

**型別/介面一致：** `run_lite_pool(pool,label,min_price,min_dolvol,default_cur,symbols,compute,out_dir,batch)`(Task4 定義) 與 PRESETS/main 一致;compute_trend 列含 `close`(Task2)供 Task4 過濾;payload 鍵 pool/pool_label/lite/cross_signals/n_ok/n_list 前端 Task5 一致使用(d.lite/d.pool_label)。

**Placeholder 掃描：** 無 TBD/TODO;每步含完整程式碼/指令/預期。

**已知前提(執行時確認)：** ① `_annotate_fresh_backtest` 對 offline downloader 例外靜默略過(既有 test_cross_signals 以 raise stub 驗證成立);② `load_pool` 跳 `#` 註解行(tw150.txt 既有檔頭,成立);③ pull_live_data 沿用重池(Task6 Step3 驗)。

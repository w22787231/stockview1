# 每日市場判讀第二階段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 產生完整市場檢查表資料，並在每日判讀加入桌面表格、手機摘要與三張確認趨勢圖。

**Architecture:** 新增 `export_daily_checklist.py`，統一以交易日對齊各來源並輸出 `daily_checklist.json`。前端沿用 `buildDailyRead` 做主題判讀，新增獨立表格／圖表 render 函式；GitHub workflow 匯出、驗證、部署與 web-only 拉取新資料檔。

**Tech Stack:** Python、pandas、numpy、yfinance、FRED、純 HTML/CSS/JavaScript、ECharts、Node assert。

## Global Constraints

- 每個指標輸出 `as_of`、來源、有效性與 1D／5D／20D 變化；日線不足時輸出 `null`，不得填 0。
- 日、週、月頻資料須在畫面標示頻率；不可宣稱為盤中或逐秒即時資料。
- 僅使用免費公開來源；不新增自動交易或買賣建議。
- web-only 部署必須沿用線上 `daily_checklist.json`，不可因只改前端而遺失資料。

---

## File Structure

- Create: `engine/export_daily_checklist.py` — 輸出 BEI、信用、波動、相對強弱與現有收益率資料的統一 JSON。
- Create: `engine/test_daily_checklist.py` — 交易日差、bp 變化、相對報酬與資料不足測試。
- Modify: `.github/workflows/export-and-deploy.yml` — 執行、驗證與 web-only 沿用新 JSON。
- Modify: `engine/pull_live_data.py` — 把新 JSON 納入 TOP 清單。
- Modify: `web/index.html` — 桌面表格、手機摘要與三張 ECharts 確認圖。
- Create: `web/test_daily_checklist.mjs` — 資料同步與前端 render 守門測試。
- Modify: `web/package.json` — 納入新增前端測試。

### Task 1: 統一日線檢查表資料

**Files:**

- Create: `engine/export_daily_checklist.py`
- Create: `engine/test_daily_checklist.py`

**Interfaces:**

- Consumes: FRED `T10YIE`、`BAMLH0A0HYM2`、`BAMLC0A0CM`；Yahoo `^MOVE`、`^VIX`、`^VIX3M`、`^VIX9D`、`SPY`、`RSP`、`IWM`、`KRE`；既有 `yieldcurve.json`、`tips.json`。
- Produces: `data/daily_checklist.json`，具有 `{generated_at, groups, charts}`；每列含 `key,label,unit,as_of,last,changes:{d1,d5,d20},status,source,frequency,available`。

- [ ] **Step 1: Write the failing test**

```python
def test_change_uses_previous_valid_trading_observation():
    assert change([1.0, None, 1.3, 1.5], 1) == 0.2

def test_relative_return_is_asset_return_minus_spy_return():
    assert relative_return([100, 110], [100, 105], 1) == 5.0

def test_missing_20d_history_returns_none():
    assert change([1.0, 1.1], 20) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python engine/test_daily_checklist.py`

Expected: FAIL，因 exporter 與純計算函式尚不存在。

- [ ] **Step 3: Write minimal implementation**

```python
def change(values, periods):
    valid=[float(v) for v in values if v is not None]
    return None if len(valid) <= periods else round(valid[-1] - valid[-1-periods], 2)

def relative_return(asset, benchmark, periods):
    if len(asset) <= periods or len(benchmark) <= periods:
        return None
    return round(((asset[-1]/asset[-1-periods])-1 - ((benchmark[-1]/benchmark[-1-periods])-1))*100, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python engine/test_daily_checklist.py`

Expected: PASS，交易日缺口、20D 不足與相對強弱皆有明確結果。

- [ ] **Step 5: Commit**

Run: `git add engine/export_daily_checklist.py engine/test_daily_checklist.py; git commit -m "feat: export daily checklist data"`

### Task 2: 部署資料同步

**Files:**

- Modify: `.github/workflows/export-and-deploy.yml`
- Modify: `engine/pull_live_data.py`
- Modify: `web/test_daily_checklist.mjs`

**Interfaces:**

- Consumes: `export_daily_checklist.py` 成功輸出的 JSON。
- Produces: Cloudflare 部署目錄中的 `data/daily_checklist.json`，web-only 模式也可取得。

- [ ] **Step 1: Write the failing test**

```js
assert.ok(pullSource.includes('"daily_checklist"'), "web-only 拉取清單缺 daily_checklist");
assert.ok(workflow.includes('export_daily_checklist.py'), "部署工作流程未執行 daily checklist exporter");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node web/test_daily_checklist.mjs`

Expected: FAIL，因同步範圍尚未包含新資料檔。

- [ ] **Step 3: Write minimal implementation**

```yaml
- name: Export daily market checklist
  run: |
    cd engine
    python export_daily_checklist.py || echo "[daily-checklist] 失敗,沿用線上"
```

```python
TOP = [..., "daily_checklist"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node web/test_daily_checklist.mjs; node web/test_data_pull_sync.mjs`

Expected: PASS，新檔在 exporter、workflow 與 web-only 拉取範圍一致。

- [ ] **Step 5: Commit**

Run: `git add .github/workflows/export-and-deploy.yml engine/pull_live_data.py web/test_daily_checklist.mjs; git commit -m "chore: deploy daily checklist data"`

### Task 3: 檢查表與三張確認圖

**Files:**

- Modify: `web/index.html`
- Modify: `web/test_daily_checklist.mjs`
- Modify: `web/package.json`

**Interfaces:**

- Consumes: `loadDailyChecklist()` 回傳的 `daily_checklist.json` 與既有 `buildDailyRead()`。
- Produces: `renderDailyChecklist(data, viewModel)`；桌面顯示八欄表格，窄畫面顯示六項摘要；`drawDailyRateChart`、`drawDailyStressChart`、`drawDailyInternalsChart` 各自渲染一張 ECharts 圖。

- [ ] **Step 1: Write the failing test**

```js
assert.ok(html.includes('變數</th><th>現值・資料日</th><th>今日</th><th>1D</th><th>5D</th><th>20D</th>'), "缺完整檢查表欄位");
assert.ok(html.includes('function drawDailyRateChart'), "缺利率／通膨確認圖");
assert.ok(html.includes('function drawDailyStressChart'), "缺風險壓力確認圖");
assert.ok(html.includes('function drawDailyInternalsChart'), "缺股票內部確認圖");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node web/test_daily_checklist.mjs`

Expected: FAIL，因表格與圖表函式尚未存在。

- [ ] **Step 3: Write minimal implementation**

```js
async function loadDailyChecklist(){
  const res=await fetch('data/daily_checklist.json?t='+Date.now(),{cache:'no-store'});
  if(!res.ok) throw new Error(res.status);
  return res.json();
}
```

```js
function renderDailyChecklist(data, vm){
  return '<table class="daily-checklist-table"><thead><tr><th>變數</th><th>現值・資料日</th><th>今日</th><th>1D</th><th>5D</th><th>20D</th><th>判讀結論</th><th>註記</th></tr></thead><tbody>'+renderChecklistRows(data.groups)+'</tbody></table>';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web test`

Expected: PASS，既有測試、資料同步守門與新表格／圖表守門皆通過。

- [ ] **Step 5: Verify visually and commit**

Run: 以本機資料啟動 `web/`；確認桌面表格的八欄完整顯示、390px 寬度顯示摘要、三張圖的圖例與資料日可讀；模擬缺失一個來源後該列顯示「資料待補」且確信度分母下降。

Run: `git add web/index.html web/test_daily_checklist.mjs web/package.json; git commit -m "feat: add complete daily market checklist"`

## Self-review

- Spec coverage：Task 1 完成資料口徑與缺值；Task 2 完成部署資料生命週期；Task 3 完成表格、手機摘要與三張確認圖。
- Placeholder scan：沒有未完成的占位文字或含糊交辦。
- Type consistency：所有任務使用同一 `daily_checklist.json` 及固定列介面，前端由 `loadDailyChecklist()` 與 `renderDailyChecklist()` 銜接。

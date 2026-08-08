# 每日市場判讀量化表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓每日判讀的每個變數輸出獨立的歷史水平、方向分數、判讀標籤與白話註記，並在頁面以參考圖形式呈現。

**Architecture:** `engine/export_daily_checklist.py` 在既有交易日資料上新增純函式評分與列層級的 `level`、`signal`、`note` 欄位。`web/index.html` 只消費這些已明確標示的欄位，負責顯示而不重複計算市場分數；既有市場主題與三張圖表維持不變。

**Tech Stack:** Python、pandas、JSON、原生 JavaScript、ECharts、Node.js 測試。

## Global Constraints

- 每列分數只供生成自己的結論，不跨列相加，也不顯示總分或交易建議。
- 缺值、資料不足、來源失敗一律輸出 `null`／「資料待補」，不得以零補值。
- 利率與信用利差變化使用 bp；股票內部使用相對 SPY 報酬；波動資料使用相對 20 日均值與比值。
- 使用 Windows PowerShell 5.1；測試輸出必須可用 UTF-8。

---

### Task 1: 匯出列的量化判讀欄位

**Files:**
- Modify: `engine/export_daily_checklist.py:17-129`
- Modify: `engine/test_daily_checklist.py:1-31`

**Interfaces:**
- Consumes: `pandas.Series` 的有效交易日值，以及既有 `row(key, label, series, unit, source, frequency, change_unit)`。
- Produces: `judgment(values, kind) -> dict`，回傳 `{"score": int|None, "level": str|None, "signal": str, "note": str}`；每個 JSON row 新增同名四個欄位。

- [ ] **Step 1: 寫失敗的量化判讀測試**

```python
eq(D.percentile(list(range(1, 26))), 100, "最新值應為歷史高位")
eq(D.judgment([2.0, 2.25, 2.40, 2.55, 2.70, 2.95], "tips")["score"], -2,
   "TIPS 五日大幅上升應為估值壓力")
eq(D.judgment([100, 101, 99, 100, 101], "relative")["signal"], "橫盤",
   "相對強弱小幅變化應為橫盤")
eq(D.judgment([], "vix")["score"], None, "缺資料不得產生分數")
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python.exe engine/test_daily_checklist.py`

Expected: FAIL，指出 `percentile` 或 `judgment` 尚未定義。

- [ ] **Step 3: 實作最小評分函式與列欄位**

```python
def percentile(values):
    valid = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(valid) < 20:
        return None
    return round(sum(v <= valid[-1] for v in valid) / len(valid) * 100)

def judgment(values, kind):
    if len(values) < 6:
        return {"score": None, "level": None, "signal": "資料待補", "note": "資料不足"}
    delta5 = change(values, 5)
    level = percentile(values)
    # kind: tips / bei / yield / oas / vix / move / relative
    # 以明確門檻回傳 -2…+2、加速／避險／橫盤與單句理由。
```

將 `row()` 擴充為接收 `kind`，合併 `judgment(values, kind)` 的回傳值；`relative_row()` 對已對齊的相對報酬序列使用 `kind="relative"`。所有 14 列都要有 `score`、`level`、`signal`、`note`。

- [ ] **Step 4: 執行資料層測試**

Run: `python.exe engine/test_daily_checklist.py; python.exe -m py_compile engine/export_daily_checklist.py`

Expected: PASS，且沒有 Python 語法錯誤。

- [ ] **Step 5: 實際產生並檢查 JSON 形狀**

Run: `python.exe engine/export_daily_checklist.py`

Expected: `data/daily_checklist.json` 的任一可用列包含 `score`、`level`、`signal`、`note`；FRED 未設定時可保留利率列空值。

- [ ] **Step 6: 提交資料層改動**

```powershell
git add engine/export_daily_checklist.py engine/test_daily_checklist.py
git commit -m "feat: score daily checklist rows"
```

### Task 2: 呈現量化判讀表與頁首旁證

**Files:**
- Modify: `web/index.html:141-150, 1781-1895`
- Modify: `web/test_daily_read.mjs:1-80`

**Interfaces:**
- Consumes: `daily_checklist.json` row 的 `level`、`signal`、`note`、`score`，與既有 `buildDailyRead(input)`。
- Produces: 詳細表的新欄位「水平／判讀結論／註記」，以及 `buildDailyRead` 的 `evidence` 陣列（僅供頁首顯示旁證數與今日主角）。

- [ ] **Step 1: 寫失敗的前端測試**

```javascript
assert.ok(html.includes('<th>水平</th>'), "量化表應顯示歷史水平欄位");
assert.ok(html.includes('<th>判讀結論</th>'), "量化表應顯示獨立判讀結論欄位");
assert.ok(html.includes('<th>註記</th>'), "量化表應顯示白話註記欄位");
assert.ok(!html.includes('市場總分'), "頁面不得顯示市場總分");
```

在既有 `rotationInputs` 加入一個 `checklist` fixture，包含 `score:-2`、`level:"高 98%"`、`signal:"↑ 加速"`、`note:"高位再升，壓制估值"` 的列；呼叫 `renderDailyRead` 後斷言四個字串都出現在 HTML。

- [ ] **Step 2: 執行測試確認失敗**

Run: `node test_daily_read.mjs`

Expected: FAIL，指出表格缺少「水平」欄位。

- [ ] **Step 3: 最小化修改前端渲染**

```javascript
function _dailySignalClass(score){
  return score == null ? '' : (score < 0 ? 'down' : (score > 0 ? 'up' : ''));
}
```

在 `_dailyChecklistTable(data)` 的表頭插入「水平」，並以 `row.level || '資料待補'`、`row.signal || '資料待補'`、`row.note || ''` 顯示三欄；`signal` 以 `_dailySignalClass(row.score)` 上色。更新 `colspan`，讓群組列涵蓋新欄位。

`buildDailyRead(input)` 從 `input.checklist.groups[].rows[]` 收集可用且 `score !== null` 的列：絕對分數由大到小取前三列，供既有「今日主角」補充顯示；確信度文案改為「旁證 n/m」，但不計算市場總分。

- [ ] **Step 4: 執行前端測試**

Run: `node test_daily_read.mjs; node test_data_pull_sync.mjs; npm.cmd test`

Expected: PASS，既有 ECharts 煙霧測試與每日判讀測試均通過。

- [ ] **Step 5: 瀏覽器檢查部署前畫面**

Run: 以可提供 `data/` 映射的本機預覽開啟「總體市場 → 每日判讀」。

Expected: 詳細表有「水平／判讀結論／註記」欄；三張圖仍存在；窄畫面可橫向捲動表格。

- [ ] **Step 6: 提交前端改動**

```powershell
git add web/index.html web/test_daily_read.mjs
git commit -m "feat: render quantified daily judgments"
```

### Task 3: 最終驗證與部署交接

**Files:**
- Verify: `engine/test_daily_checklist.py`
- Verify: `web/package.json`
- Verify: `.github/workflows/export-and-deploy.yml`

**Interfaces:**
- Consumes: Tasks 1、2 的提交與既有 Actions exporter。
- Produces: 可推送、可由完整 `export-and-deploy` 產生新版 JSON 的乾淨分支。

- [ ] **Step 1: 跑完整驗證**

Run: `python.exe engine/test_daily_checklist.py; Push-Location web; npm.cmd test; Pop-Location; git diff --check`

Expected: 全部 PASS，且 `git diff --check` 無輸出。

- [ ] **Step 2: 確認工作流程會產生新檔**

Run: `Select-String -LiteralPath .github/workflows/export-and-deploy.yml -Pattern 'export_daily_checklist.py|daily_checklist'`

Expected: 同時找到 exporter 與部署後 JSON 驗證。

- [ ] **Step 3: 交付整合選項**

回報提交、測試結果與部署前提：需在 GitHub Actions 手動執行完整 `export-and-deploy`，不能使用 `web_only` 來產生首次新版資料檔。

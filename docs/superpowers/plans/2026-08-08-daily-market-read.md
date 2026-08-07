# 每日市場判讀分頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在總體市場新增「每日判讀」分頁，將既有快照資料轉為可追溯的市場主題與六項檢查表。

**Architecture:** 在 `web/index.html` 增加純函式 `buildDailyRead`，將四份 JSON 轉成不含 DOM 的 view model；載入層平行取得資料並容忍缺檔；渲染層只使用 view model 生成分頁內容。

**Tech Stack:** 純 HTML/CSS/JavaScript、原生 `fetch`、Node `assert` 測試。

## Global Constraints

- 第一版只使用 `macro.json`、`sentiment.json`、`macro_score.json`、`us_theme_flow.json`，不可虛構新資料源。
- 資料檔缺失時，對應模組標示「資料待補」並排除於確信度分母，不得使整頁失效。
- 必須明示資料頻率不同，僅供盤後日線判讀，不是即時交易訊號。
- 既有總覽、個股二階導、Williams %R 行為與 HTML 不可改變。

---

## File Structure

- Modify: `web/index.html` — 分頁按鈕、判讀函式、資料載入器、HTML/CSS 渲染。
- Create: `web/test_daily_read.mjs` — 合成資料單元測試與分頁 DOM 守門測試。
- Modify: `web/package.json` — 將新測試納入 `npm test`。

### Task 1: 市場判讀純函式

**Files:**

- Create: `web/test_daily_read.mjs`
- Modify: `web/index.html` 的 `MACRO_TAB` 宣告附近

**Interfaces:**

- Consumes: `buildDailyRead({macro, sentiment, score, themeFlow})`，四份資料可為 `null`。
- Produces: `{theme, confidence, summary, actors, falsifiers, modules}`；`modules` 固定六列，每列含 `key,label,state,status,detail,available`。

- [ ] **Step 1: Write the failing test**

```js
assert.equal(api.buildDailyRead(riskInputs).theme, "風險撤退");
assert.equal(api.buildDailyRead(rotationInputs).theme, "板塊輪動");
assert.equal(api.buildDailyRead({}).modules.filter(x => !x.available).length, 6);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node test_daily_read.mjs`

Expected: FAIL，因 `buildDailyRead` 尚未定義。

- [ ] **Step 3: Write minimal implementation**

```js
function buildDailyRead(input){
  const modules=[buildRates(input),buildCurve(input),buildDollarGold(input),buildCreditLiquidity(input),buildSentiment(input),buildInternalsFlow(input)];
  const available=modules.filter(m=>m.available), risk=available.filter(m=>m.state==="risk").length, support=available.filter(m=>m.state==="support").length;
  const theme=risk>=2 ? "風險撤退" : support>=3 ? "風險偏好擴散" : modules[5].state==="rotation" ? "板塊輪動" : "訊號分歧";
  return {theme,confidence:{supported:Math.max(risk,support),available:available.length},modules,summary:buildSummary(theme,modules),actors:buildActors(input),falsifiers:buildFalsifiers(theme,input)};
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node test_daily_read.mjs`

Expected: PASS，三種分類、缺資料與固定六列皆通過。

- [ ] **Step 5: Commit**

Run: `git add web/index.html web/test_daily_read.mjs; git commit -m "feat: derive daily market read view model"`

### Task 2: 分頁與容錯載入

**Files:**

- Modify: `web/index.html` 的 `renderMacro` 與 `renderMacroTabBody`
- Modify: `web/test_daily_read.mjs`

**Interfaces:**

- Consumes: `loadDailyRead()` 在 `MACRO_TAB === "dailyread"` 時呼叫。
- Produces: `#dailyReadBlock`，不影響其他 `MACRO_TAB` 分支。

- [ ] **Step 1: Write the failing test**

```js
assert.ok(html.includes('data-mtab="dailyread"'), "缺每日判讀分頁按鈕");
assert.ok(html.includes('id="dailyReadBlock"'), "缺每日判讀容器");
assert.ok(html.includes('Promise.allSettled'), "每日判讀應容忍個別資料檔失敗");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node test_daily_read.mjs`

Expected: FAIL，因分頁、容器與容錯載入尚未存在。

- [ ] **Step 3: Write minimal implementation**

```js
if(MACRO_TAB==="dailyread"){
  body.innerHTML='<div id="dailyReadBlock"><div class="loading-screen">載入每日判讀 …</div></div>';
  loadDailyRead(); return;
}
const results=await Promise.allSettled(names.map(name=>fetch("data/"+name+".json?t="+Date.now(),{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json();})));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node test_daily_read.mjs; node test_data_pull_sync.mjs`

Expected: PASS；四個資料檔均已存在於既有 pull 同步範圍。

- [ ] **Step 5: Commit**

Run: `git add web/index.html web/test_daily_read.mjs; git commit -m "feat: add daily market read tab"`

### Task 3: 檢查表視覺呈現與端到端驗證

**Files:**

- Modify: `web/index.html` 的既有 macro-tabs CSS 區域與每日判讀 render 函式
- Modify: `web/test_daily_read.mjs`
- Modify: `web/package.json`

**Interfaces:**

- Consumes: `renderDailyRead(viewModel)`。
- Produces: 市場主題、確信度、白話結論、今日主角、推翻訊號、六項列與固定口徑提醒。

- [ ] **Step 1: Write the failing test**

```js
api.renderDailyRead(api.buildDailyRead(rotationInputs));
assert.ok(boxHtml.includes("市場主題"), "缺市場主題列");
assert.ok(boxHtml.includes("推翻訊號"), "缺推翻訊號");
assert.equal((boxHtml.match(/data-daily-module=/g)||[]).length,6,"應固定渲染六項檢查表");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node test_daily_read.mjs`

Expected: FAIL，因每日判讀 HTML 尚未渲染。

- [ ] **Step 3: Write minimal implementation**

```js
function renderDailyRead(vm){
  const box=$("#dailyReadBlock"); if(!box)return;
  box.innerHTML='<section class="daily-read">'+dailyReadHeader(vm)+dailyReadActors(vm)+'<div class="daily-read-grid">'+vm.modules.map(dailyReadModuleRow).join("")+'</div><div class="legend">此頁使用盤後快照；週／月資料不代表盤中變化，僅作市場結構判讀。</div></section>';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`

Expected: PASS，既有測試與新每日判讀測試均通過。

- [ ] **Step 5: Verify visually and commit**

Run: 從 `web/` 啟動 `python -m http.server 8899`，在瀏覽器開啟總體市場並切換「每日判讀」。確認桌面與窄視窗六列完整可見、文字不截斷、資料缺漏只影響對應列、切回其他三分頁仍可用。

Run: `git add web/index.html web/test_daily_read.mjs web/package.json; git commit -m "feat: render daily market read checklist"`

## Self-review

- Spec coverage：Task 1 實作分類、信心與推翻條件；Task 2 實作資料容錯與分頁；Task 3 實作六項檢查表、揭露與全套驗證。
- Placeholder scan：沒有未完成的占位文字或含糊交辦。
- Type consistency：各任務均使用同一 `buildDailyRead(input)`、`renderDailyRead(viewModel)` 與固定六列 `modules` 介面。

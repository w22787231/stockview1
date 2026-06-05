# 交叉訊號分頁（全池金叉/死叉觸發整理）— 設計文件

日期：2026-06-06
狀態：已與使用者對齊，待 spec 審閱

## 目標

在網頁新增一個主分頁「交叉訊號」，整理**全池每一檔股票**的 MA10×MA50 黃金交叉 / 死亡交叉狀態，
讓使用者一眼看到：哪些股票「最近剛觸發」交叉，以及目前全部處於金叉 / 死叉的股票清單。

源自使用者需求：「可以把網頁的所有股票黃金交叉訊號觸發時告訴我嗎？或是新增一個主分頁整理黃金交叉觸發 / 死亡交叉觸發。」

## 已對齊的需求決策

| 項目 | 決策 |
|---|---|
| 觸發定義 | 兩者都要：分「🔥最近剛觸發」區塊 + 「全部目前狀態」區塊 |
| 涵蓋範圍 | 跟趨勢動能榜一樣**分池**（tw150 / ndx100 / sp500 / sp400 / sp600），各池獨立載入 |
| 「剛觸發」窗口 | **3 天內**（`cross_days <= 3`）；寫死為常數，要改改一處 |
| 每檔欄位 | 交叉天數 + 動能欄 + 可點進個股：`代號·名稱 / 狀態 / 幾天前 / 5日漲% / 5日評分 / Score` |
| 長表處理 | 全部列出，但「全部金叉 / 全部死叉」**預設收起可展開**；「🔥剛觸發」預設展開 |

## 背景：現有架構（不需改的部分）

- 計算引擎 `engine/adr_screen.py` 的 `compute_trend(symbols)` **已對全池每一檔**計算
  `cross_state`（`golden` 短>長 / `death` 短<長）與 `cross_days`（距最近一次交叉幾天，
  `0`＝最新一根 K 棒觸發、`None`＝回看 120 日內無交叉）。交叉用 MA10×MA50，6 個月日線。
- 此交叉資料**目前在匯出時被丟棄**：`export_json.py` 只把全池 rows 截 Top N 存進 `main`，
  其餘（含全池交叉狀態）未進 JSON。
- 各池清單規模：tw150≈151、ndx100≈95、sp500≈505、sp400≈402、sp600≈605。
  「90」是 ndx100 單池成功抓到的檔數，非全部。
- 前端 `web/index.html` 已有主分頁（`總體市場 / 趨勢動能榜 / 即時快訊`，`data-view` 切換）、
  池子分頁列、`load()` 取 `data/<pool>.json`、點代號 `data-stk` 跳個股、`SORT_STATE` 點表頭排序、
  `crossCell`/`sgn`/`cls`/`esc` 等元件。

## 方案選擇

採 **方案 B：後端補匯出全池交叉欄位 + 前端新分頁**。

- 方案 A（純前端重用 `cross_filter`）：不可行，`cross_filter` 僅 5日評分≥80、無 `cross_days`、`main` 僅 Top 30，沒有全池交叉資料。
- 方案 C（跨池合併大表）：已被「分池」決策排除。
- 方案 B 採用理由：所需交叉資料引擎早已算好（零新計算、不增加 yfinance 抓取），只是把被丟棄的欄位補進匯出；前端完全沿用既有 tab / 表格 / 排序 / 點擊進個股基礎建設。

## 設計

### 1. 後端：`export_json.py` 新增 `build_cross_signals(rows)`

吃 `compute_trend` 回傳的**全池 rows**（未截斷），輸出區塊塞進每池 JSON，與 `cross_filter` 並列：

```python
"cross_signals": {
  "fresh_days": 3,
  "golden": [ {row}, ... ],   # cross_state == 'golden' 的全部股票
  "death":  [ {row}, ... ],   # cross_state == 'death'  的全部股票
  "n_golden": <int>, "n_death": <int>
}
```

每個 `{row}` 欄位（前端動能欄所需）：
`sym, name, cross_state, cross_days, sc5, r5, score, e5, e20, a20, cur`
（`name` 用既有 `_name(sym)`：台股回中文、美股 None。）

排序口徑（golden 與 death 各自）：
- 主鍵：`cross_days` 由小到大（越新觸發越前；`None` 視為 +∞ 排最後）。
- 次鍵：`score` 由大到小。

`cross_state` 非 `golden`/`death`（資料不足、`None`）的列直接略過，不進任一組。
「🔥剛觸發」不另存陣列：前端從 `golden`+`death` 即時篩 `cross_days != null && cross_days <= fresh_days`，
避免資料重複、`fresh_days` 改一處即可。

在主輸出 dict（約 `export_json.py:333`）加：`"cross_signals": build_cross_signals(rows)`。

### 2. 前端：新主分頁「交叉訊號」

- nav 主分頁列（`index.html:283`）在「趨勢動能榜」後加 `<button data-view="cross">交叉訊號</button>`，
  順序：`總體市場 | 趨勢動能榜 | 交叉訊號 | 即時快訊`。
- `switchView()`（`index.html:1252`）加 `cross` 分支：沿用趨勢頁同一套池分頁列與同一份 JSON
  （`data/<pool>.json` 已含 `cross_signals`）。切到 cross 時工具列(池分頁)顯示（同 trend）。
- 加模組級變數記住「目前子分頁是 trend 還是 cross」；`load()` 取完同一份資料後，依此呼叫
  `render(d)`（趨勢）或 `renderCross(d)`（交叉）。trend↔cross 互切若資料已在手可直接重渲染、不必重抓。

`renderCross(d)` 版面（由上到下）：
1. 區段標頭：`交叉訊號  [MA10×MA50 · 本池 <LABEL>]  本池 <n_ok> 檔，每日快照`
2. ⚠️ 歷史/快照提醒 banner（沿用既有樣式）。
3. `🔥 最近剛觸發（≤3 天）  [金叉 X ・ 死叉 Y]` — 預設展開，單一表格（golden+death 篩 fresh 後依天數排序）。
4. `▼ 全部金叉（N 檔）` — `<details>` 預設收起，展開為金叉表格。
5. `▼ 全部死叉（N 檔）` — `<details>` 預設收起，展開為死叉表格。
6. legend：金叉=MA10 上穿 MA50（偏多）、死叉=下穿（偏空）；幾天前＝距最近交叉的交易日數。

表格欄位（共用元件 `crossSignalTable(rows)`）：
`# / 代號·名稱(可點 data-stk) / 狀態(▲金叉綠 ▼死叉紅，沿用 crossCell) / 幾天前 / 5日漲% / 5日評分 / Score`

復用既有元件：`crossCell`/`crossSortVal`、`sgn`/`cls`、`esc`、`data-stk` 點擊進個股、
`tbl-wrap`/`sec-head`/`details` 樣式 → 幾乎不需新 CSS。折疊用原生 `<details>/<summary>`（無需 JS）。

### 3. 互動與排序

- 三表沿用 `SORT_STATE` + 點表頭排序。
- 預設排序：交叉天數小→大（越新越上）、同天數 Score 大→小。
- 「幾天前」排序值：`cross_days==null` 排最後。

## 邊界情況

| 情況 | 處理 |
|---|---|
| 某池無金叉 | golden 區「（本池目前無金叉）」 |
| 🔥剛觸發篩完為空 | 顯示「近 3 日無新交叉觸發」，不顯示空表 |
| `cross_days == 0` | 「今日觸發 ★」，置頂 |
| `cross_days == null` | 「幾天前」顯示「—」，排序墊底 |
| `cross_state == null`（<52 bar 資料不足） | 後端直接略過，不進 golden/death |
| 舊 JSON 尚無 `cross_signals`（部署時間差） | 前端 `if(!d.cross_signals)` → 顯示「此池資料尚未含交叉訊號，請按更新資料」，不報錯 |

## 測試

1. **後端**：本地重跑 `export_json.py ndx100`，斷言：有 `cross_signals`；`n_golden+n_death <= n_ok`；
   golden 全 `cross_state=='golden'`、death 全 `=='death'`；排序正確（`cross_days` 遞增、None 墊底）；
   fresh 數 == `cross_days<=3` 的數。
2. **前端**：Node 抽出 `crossSignalTable`/`renderCross` 邏輯餵真實 `cross_signals`，斷言三區塊 HTML 無誤、
   檔數標籤正確、空池 / 空剛觸發走 fallback 文案。
3. **手動**：本地 `python -m http.server` 開頁，點「交叉訊號」、切池、展開折疊、點代號跳個股皆正常。

## 改動檔案

| 檔案 | 改動 |
|---|---|
| `engine/export_json.py` | +`build_cross_signals(rows)`；主輸出 dict 加 `"cross_signals"` |
| `web/index.html` | +主分頁按鈕；`switchView` 加 `cross` 分支；+`renderCross`/`crossSignalTable`；`load()` 依子分頁選 render |
| `engine/adr_screen.py` | 不改（交叉計算已存在） |

## 不做（YAGNI）

跨池合併大表、歷史交叉時間軸、Email/推播通知、自訂天數 UI（先寫死 3 天常數）。

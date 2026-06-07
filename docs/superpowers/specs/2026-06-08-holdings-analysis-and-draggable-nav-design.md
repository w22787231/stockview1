# 設計：持股分析主分頁 + 主分頁拖曳重排

日期：2026-06-08
專案：adr-trend-web（stockview1.pages.dev）
範圍：單檔前端 `web/index.html` + Worker `web/_worker.js` 小改

## 背景

現有主分頁共 7 個（[web/index.html:409-417](../../../web/index.html)）：總體市場、趨勢動能榜、交叉訊號、產業鏈、ETF持股異動、**持股檢查**、即時快訊。其中「持股檢查」（`data-view="holdings"`）已 commit（`7bc91cf`）並 push 到 main，但尚未部署上線。

本設計做兩件事：
1. 把「持股檢查」升級成「**持股分析**」：改逐檔加股票的輸入框架、加多日漲幅動能欄位。
2. 讓所有主分頁可**拖曳重排**，順序記在瀏覽器。

兩者皆為純前端（加一處 Worker 小改），不動 Python/資料管線。

---

## 功能一：持股分析主分頁

### 1. 導覽列改名
[web/index.html:415](../../../web/index.html) 的 `持股檢查` 標籤文字改為 `持股分析`。`data-view` 維持 `holdings`，因此 `switchView`、`loadHoldings` 的路由與函式名都不需更動（僅內部 UI 重寫）。

### 2. 輸入框架（逐檔加股票）
取代原本的多行 textarea：

- 單列輸入：`代號輸入框` + `[+ 新增]` 按鈕；輸入框按 Enter 等同按新增。
- 新增流程：正規化代號 → 去重加入清單 → 立即抓該檔報價 → append 一列到表格。
- 正規化規則（沿用現有 `_holdCand`）：純數字 → 候選 `.TW` 與 `.TWO`；已含 `.TW`/`.TWO` → 原樣；其餘（美股等）→ 原樣大寫。
- 每列尾端 `[刪除]` 鈕；表格上方 `[清空]`、`[🔄 重新整理]`。
- **只存代號、不收股數/成本、不算損益**（使用者明確選擇）。

### 3. 持久化與舊資料遷移
- 新 localStorage key `holdings_codes`，內容為代號 JSON 陣列，例 `["NVDA","2330.TW","6488"]`。
- 載入時若 `holdings_codes` 不存在但舊 key `holdings`（多行文字）存在，解析每行第一個 token 當代號、去重寫入 `holdings_codes`，完成一次性遷移（不刪舊 key，保險）。

### 4. Worker 小改 — `web/_worker.js`
`fetchQuote`（約 [web/_worker.js:97-124](../../../web/_worker.js)）在 `withKline` 模式下，除現有 `closes` 外，多回傳對齊的 `volumes` 陣列：

- 取 `res.indicators.quote[0].close` 與 `…volume` 兩個陣列。
- **以「close 非 null」為準成對保留**（同一索引 close 為 null 就整列丟棄），確保 `closes` 與 `volumes` 索引對齊。回傳 `q.closes`、`q.volumes`。
- 非 kline 模式不變。

### 5. 抓取
- 代號清單依 `_holdCand` 展開候選後，**每 5 檔一批**呼叫 `/api/quotes?kline=1&syms=…`（kline 模式 Worker 上限 5 檔）。
- 多批以 `Promise.all` 併發；逐檔比對候選命中哪個後綴（沿用現有命中邏輯）。

### 6. 每檔表格欄位
`代號｜名稱｜現價｜日漲跌%｜1日｜5日｜20日｜量比｜資金流向｜距52週高｜距52週低｜健康檢查`

### 7. 計算（前端，嚴格對齊 `engine/adr_screen.py`）
以 kline 回傳的 `closes`、`volumes` 計算（變數對齊 `_ret_n`、`compute_trend` 的 `volr`）：

- `r_n = (closes[-1] / closes[-(n+1)] − 1) × 100`，分別取 n=1,5,20 → 1/5/20 日漲幅。
  - 對齊 `_ret_n(sub,n)`：用 `tail(n+1)`，即 `closes[-(n+1)]` 為基準。
- `dv_i = closes[i] × volumes[i]`（成交金額）。
- `dv = mean(最近 20 筆 dv)`；`dv1 = 最後一筆 dv`；**`量比 volr = dv1 / dv`**。
  - 對齊 `compute_trend`：分母用近 20 日均成交金額、分子用最後一日成交金額。
- **資金流向**（對齊 `export_json.py` build_signals 的 inflow 慣例 `volr≥1.5 且 r5>0`）：
  - `volr ≥ 1.5 且 r5 > 0` → 🟢流入（量價同向）
  - `volr ≥ 1.5 且 r5 ≤ 0` → 🔴爆量下跌（出貨?）
  - 其餘 → —
- 健康檢查標籤沿用現有 `renderHoldings`：創新高區（距52週高≥-1%）／遠離高點≥25%／逼近52週低（距低≤8%）／今日重挫（日跌≥3%）。

### 8. 邊界 / 錯誤處理
- `closes` 不足 21 筆 → r20（或對應 r_n）顯「–」，不報錯；量比同理（dv 樣本不足 20 仍以現有筆數均值計，<2 筆顯「–」）。
- 某批 `/api/quotes` 失敗 → 僅該批的列顯「查詢失敗」，其餘批照常顯示。
- 代號查無報價 → 該列顯「查無即時報價（代號可能不存在）」。
- 本機無 Worker（dev）→ 沿用現況提示「需部署後 /api/quotes 才可用」。

---

## 功能二：主分頁拖曳重排

### 1. 動態渲染
把 [web/index.html:409-417](../../../web/index.html) 靜態的 7 顆 `.mtab` 改成由陣列產生：

```
NAV = [
  {view:"macro", label:"總體市場"},
  {view:"trend", label:"趨勢動能榜"},
  {view:"cross", label:"交叉訊號"},
  {view:"chain", label:"產業鏈"},
  {view:"etf",   label:"ETF持股異動"},
  {view:"holdings", label:"持股分析"},
  {view:"news",  label:"即時快訊"},
]
```

`#mainnav` 的內容改由 JS 依「生效順序」render；每顆按鈕仍是 `.mtab[data-view]`，現有 `switchView` 綁定方式不變（render 後重新綁 click）。

### 2. 順序持久化
- localStorage key `navOrder`，存 `view` 字串陣列。
- 生效順序 = 取 `navOrder` 過濾掉 `NAV` 已無的 view → 再把 `NAV` 中尚未出現的 view 依原序補到尾端。
  - 好處：未來新增/移除分頁時，舊順序仍有效，新分頁自動出現在最後、不會憑空消失。

### 3. 拖曳互動（pointer events，滑鼠 + 觸控共用）
- 直接拖動分頁即可換位，放開即把新順序寫回 `navOrder`。不另設「編輯模式」。
- **點擊 vs 拖曳分流**：`pointerdown` 記起點 → `pointermove` 位移超過門檻（約 6px）才進入拖曳；未超過門檻於 `pointerup` 視為點擊 → 切頁。避免想切頁卻誤觸重排。
- 重排演算法：拖曳中依指標位置即時計算插入索引、重排 DOM（或以 transform 讓位）。放開後依目前 DOM 順序寫回 `navOrder`、清除拖曳樣式。
- 視覺：拖曳中的分頁浮起 / 半透明（提高 z-index、加陰影），其他分頁讓位。
- 手機：`#mainnav` 本為 `overflow-x:auto` 橫向可捲動；拖曳中的元素設 `touch-action:none` 並於進入拖曳時 `setPointerCapture`，避免「捲動 vs 拖曳」衝突。未達拖曳門檻時不攔截，原生橫向捲動照常。

---

## 受影響檔案
- `web/index.html` — nav 動態化 + 拖曳；holdings 視圖重寫（輸入框架、欄位、計算）。
- `web/_worker.js` — `fetchQuote` kline 模式多回傳 `volumes`。

## 不做（YAGNI）
- 不收股數/成本、不算損益、不做組合層統計。
- 不做 ADR/效率欄位（未要求；且需 High/Low，Worker 未回傳）。
- 不對到 1700 預生池（做法 C），一律走 `/api/quotes` 即時，邏輯單一。
- 拖曳不做跨列動畫的精緻 FLIP，夠用即可。

## 測試重點
- 計算正確性：以一組已知 closes/volumes 驗證 r1/r5/r20、volr、flow 與 `adr_screen.py` 對同一序列的結果一致。
- 遷移：舊 `holdings` 文字 → `holdings_codes` 陣列。
- 拖曳：滑鼠拖曳換位後重整仍保留；點擊（未達門檻）正常切頁；手機橫向捲動不被誤判為拖曳。
- navOrder 容錯：手動塞入含未知 view / 缺漏 view 的 navOrder，render 仍正確（過濾 + 補尾）。
- 邊界：closes<21、批次失敗、代號查無，皆不整頁壞掉。

## 上線
純前端 + Worker 改動。依專案慣例 push main **不會自動部署**（`export-and-deploy.yml` 無 push 觸發）。合併後須手動 `gh workflow run export-and-deploy.yml --ref main` 才上線；或開 PR 先看 Cloudflare preview。

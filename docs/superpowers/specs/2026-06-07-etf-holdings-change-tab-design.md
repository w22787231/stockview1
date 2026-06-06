# ETF 持股異動分頁（主動式 ETF 每日池股變化）— 設計文件

日期：2026-06-07
狀態：已與使用者對齊，待 spec 審閱

## 目標

在 stockview1.pages.dev 新增一個主分頁「ETF 持股異動」，每日追蹤 5 檔台股主動式 ETF
的持股變化（新增 / 出清 / 加碼 / 減碼），以「日期 → ETF 分組」呈現最近 30 個交易日的
變動流水帳。

源自使用者需求：把本機 `etf_tool` 產生的 `active_etf_history`（每日 ETF 池股變化）整合進網站。

## 已對齊的需求決策

| 項目 | 決策 |
|---|---|
| 資料橋接 | **讓網站自己重抓**：移植 `fetch_holdings.py` 成 `engine/fetch_etf.py`，GitHub Actions 每天自抓自累積，與本機 `D:\ETF` 脫鉤 |
| 歷史長度 | **最近 30 個交易日**（超過自動滾掉最舊）|
| 顯示重點 | **以「每日變化」為主**（不做當前持股完整快照分頁、不做個股視角聚合）|
| 排序 | **日期(新→舊) → ETF(固定順序) → 組內權重(高→低)**；不可把不同 ETF 的股票混在一張表按股票排 |

## 背景：兩個既有系統

- **本機 ETF 工具**（`~/etf_tool`，輸出 `D:\ETF`）：排程每日跑，`fetch_holdings.py`
  從 ETF 發行商官網抓 5 檔持股，`active_etf_daily.py` 比對前一日產 Excel + `active_etf_history.xlsx`。
  本設計**不改動**此工具，只移植其 `fetch_holdings.py` 抓取邏輯。
- **網站**（`adr-trend-web` → Cloudflare Pages）：5 個主分頁
  （macro / trend / cross / chain / news），資料由 GitHub Actions 跑 `engine/export_*.py` 產生並
  commit 進 repo 的 `data/`。`chain` 分頁是「讀靜態 `tw_chain.json` + `loadChain()` 渲染」的範例，
  本設計沿用此模式。
- **關鍵限制**：GitHub Actions 在雲端執行，看不到本機 `D:\ETF`，故網站必須自行抓取 ETF 官網。

## 5 檔 ETF（來源 `fetch_holdings.py` 的 ETFS，即固定排序順序）

| 順序 | 代號 | 名稱 | 來源 |
|---|---|---|---|
| 1 | 00981A | 統一台股增長 | 統一 ezmoney (tongyi) |
| 2 | 00988A | 統一全球創新 | 統一 ezmoney (tongyi) |
| 3 | 00403A | 統一台股升級50 | 統一 ezmoney (tongyi) |
| 4 | 00982A | 群益台灣精選強棒 | 群益 capitalfund (capital) |
| 5 | 00990A | 元大全球AI新經濟 | 元大 yuantaetfs (yuanta) |

## 方案選擇

採 **方案 A：移植 fetch + 新增 export_etf.py，網站自抓自累積**。
- 方案 B（本機 push JSON）：依賴本機每天開機+push，違背「自動」，已排除。
- 方案 C（抽共用引擎）：改動最大（動到 etf_tool 結構），已排除。
- A 採用理由：完全自動、與本機脫鉤、沿用網站既有 chain 分頁架構。

## 設計

### 1. 後端：抓取 + 產資料

#### 1a. `engine/fetch_etf.py`（移植自 `etf_tool/fetch_holdings.py`）
原樣移植，**邏輯不改**：
- `ETFS` dict（5 檔定義，含 src / fundCode / path）——也是前端分組的固定順序來源。
- `fetch_tongyi` / `fetch_capital` / `fetch_yuanta`：各抓一發行商官網持股頁。
- `fetch_all()`：回傳 `{etf: [{etf,etf_name,code,name,weight,qty}, ...]}`；**已內建 per-ETF
  try/except**（單檔失敗 → 該檔回空 list，不影響其他檔）。

#### 1b. `engine/export_etf.py`（新增）
流程：
1. `data = fetch_etf.fetch_all()`（今日 5 檔持股）。
2. 讀現有 `../data/etf.json`（若有）取 `snapshot`（上次最新持股）做比對基準。
3. 對每檔 ETF 算變化（同 etf_tool 口徑）：
   - 今有昨無 → `新增`；今無昨有 → `出清`；張數增 → `加碼`；張數減 → `減碼`；持平不記。
   - 每筆：`{etf, etf_name, code, name, action, dqty, qty, dweight, weight}`。
4. 把**只含真正變動**的今日 changes 包成一筆 `{date: TODAY, changes:[...]}` 加到 `history` 最前。
   - 若今日全無變動（週末/假日持股不變）→ **不新增** history 條目。
   - 同日重複跑 → 以日期去重（覆蓋當日那筆，不重複堆疊）。
5. `history` **只保留最近 30 筆**（最舊滾掉）。
6. 更新 `snapshot` 為今日持股；寫回 `../data/etf.json`。

**容錯（防寫壞資料）**：
- 單檔抓失敗（`fetch_all` 回該檔空 list）→ 該檔**保留 `etf.json` 既有 snapshot**，不當成「全出清」。
- 全部抓失敗（5 檔皆空）→ **不覆寫 `etf.json`**，log 報錯後正常結束（讓 workflow `|| true` 繼續）。
- 首次跑（無 `etf.json`）→ 只存 snapshot，history 留空。
- `downloader` / fetch 函式可注入，供離線測試。

#### `data/etf.json` 結構
```json
{
  "generated_at": "2026-06-07T10:30:00Z",
  "etfs": { "00981A": {"name":"統一台股增長"}, "...": {} },
  "order": ["00981A","00988A","00403A","00982A","00990A"],
  "snapshot": { "00981A": [{"code","name","weight","qty"}, ...], "...": [] },
  "history": [
    { "date":"2026-06-06",
      "changes":[
        {"etf":"00981A","etf_name":"統一台股增長","code":"2330","name":"台積電",
         "action":"加碼","dqty":120,"qty":11960,"dweight":0.3,"weight":10.11}
      ] }
  ]
}
```
- `order`：固定 ETF 顯示順序（= `ETFS` 鍵順序），前端分組依此排。
- `snapshot`：供下次比對 + 前端「目前持股」如需（本期不展示，但保留）。

### 2. 前端：`etf` 主分頁

- nav（`web/index.html` 約 :343，chain 之後 / news 之前）加
  `<button class="mtab" data-view="etf">ETF持股異動</button>`。
- `switchView` 加 `else if(v==="etf") loadEtf();`；此頁工具列(池分頁)隱藏，搜尋框可保留。
- `loadEtf()`（仿 `loadChain`，fetch `data/etf.json`）渲染：
  - 區段標頭：`ETF 持股異動  [5 檔主動式ETF · 每日追蹤]  資料日 <最新history日期>`。
  - 提醒 banner：資料源各 ETF 官網、週末/假日持股不變動屬正常。
  - **ETF 篩選列**（全部 / 各 ETF）+ **動作篩選**（全部 / 🆕新增 / ➕加碼 / ➖減碼 / ❌出清）——純前端即時過濾。
  - **內容（核心排序）**：依 `history`（日期新→舊）逐日一區塊；每日內**依 `order` 把 changes
    分組成各 ETF**（ETF 名稱當分組標頭 + 該組變動計數），組內依 `weight` 由高到低。
    - 每組一張表，欄位：`代碼 / 股票 / 動作 / 張數變化 / 目前張數 / 權重變化 / 權重%`（ETF 名在標頭，故無 ETF 欄）。
    - 動作上色（同 etf_tool）：🆕新增黃 / ➕加碼綠 / ➖減碼紅 / ❌出清灰。
    - 台股代碼可點 → 沿用 `data-stk` 跳個股詳情。
  - 空狀態：某日全無變動則不顯示該日；整份無 history → 「尚無變動紀錄（週末/假日或剛部署）」；
    `if(!d)`（舊 JSON 無 etf）→ 「ETF 資料尚未產生，請待下次更新」。

復用：`sgn`/`cls`/`esc`/`data-stk`/`sec-head`/`tag`/`legend`/`tbl-wrap` → 幾乎不需新 CSS。

### 3. workflow 接線

`.github/workflows/export-and-deploy.yml`：在 `export_chain.py` 步驟之後加：
```yaml
- name: Export active ETF holdings change
  run: |
    cd engine
    python export_etf.py || true
```
`|| true`：ETF 官網擋爬/改版時不中斷整體部署（沿用既有 sentiment 步驟的容錯慣例）。

## 測試

1. **後端離線** `engine/test_etf.py`（注入假 fetcher，不連網）：
   - 4 種變化 tag 計算正確（新增/出清/加碼/減碼），持平不記。
   - history 追加 + 保留最近 30 日、超過滾掉最舊；同日重跑去重。
   - 今日全無變動 → 不新增 history 條目。
   - 單檔抓失敗 → 保留該檔舊 snapshot、不誤判全出清；全失敗 → 不覆寫 etf.json。
2. **前端 headless** `web/test_etf_dom.mjs`（餵真實 etf.json 結構跑 loadEtf 純邏輯）：
   - 日期分組數 = history 長度；每日內 ETF 分組依 order；組內權重遞減。
   - 動作篩選正確；空 history / 無 etf 走 fallback 文案。
3. **真實資料端對端**（手動，需網路）：本地 `python export_etf.py` 跑一次，確認抓到 5 檔、
   `etf.json` 結構合理（snapshot 有資料、history 視當日有無變動）。

## 改動檔案

| 檔案 | 改動 |
|---|---|
| `engine/fetch_etf.py` | 新增（移植自 etf_tool/fetch_holdings.py，邏輯不改）|
| `engine/export_etf.py` | 新增（抓→比對→算變化→寫 etf.json，留 30 日，容錯）|
| `engine/test_etf.py` | 新增（離線單元測試）|
| `web/index.html` | +etf 主分頁按鈕；switchView 加 etf 分支；+loadEtf() 渲染 |
| `web/test_etf_dom.mjs` | 新增（前端 headless 測試）|
| `.github/workflows/export-and-deploy.yml` | +一步 export_etf.py \|\| true |
| `etf_tool/*` | **不改** |

## 不做（YAGNI）

個股視角聚合、ETF 持股完整快照分頁、自訂歷史天數 UI（寫死 30 天）、即時抓取按鈕、改動本機 etf_tool。

# CPO 鏈加入全球龍頭（跨市場個股）— 設計

日期：2026-06-06
範圍：在「產業鏈」分頁的 CPO/矽光子鏈，加入美股、歐股國際龍頭，與既有台股並列；前端依代號後綴自動標記來源市場。

## 1. 目標與非目標

**目標**
- CPO/矽光子鏈納入跨市場個股（台/美/歐），呈現完整全球供應鏈。
- 個股卡片依代號後綴自動顯示來源市場標記（台/美/瑞…），無需手動標。
- 跨市場個股的 1/5/20 日漲跌、資金流向徽章沿用既有 `export_chain.py` 自動計算（已驗證 yfinance 可抓）。

**非目標**
- 不動 AI 伺服器、半導體兩條鏈（本次只擴 CPO 鏈）。
- 不為美/歐股加中文名（搜尋維持用代號；中文名搜尋不受影響）。
- 不改 `export_chain.py` 抓取邏輯、不改 workflow、不改部署。
- 不處理匯率換算（各股 last 顯示原幣別數值；本就不顯示 last，漲跌%為相對值跨市場可比）。

## 2. 新增的國際龍頭（已逐一驗證 yfinance 可抓，2026-06-06）

分入 CPO/矽光子鏈，含新增兩個環節：

| 環節 | 個股（代號 / 名稱 / 市場） |
|---|---|
| 光源 / 雷射 (ELS)（既有，補入） | SIVE.ST（Sivers Semiconductors / 瑞典）|
| **光收發 / CPO 模組（新環節，中游）** | COHR（Coherent / 美）、LITE（Lumentum / 美）、CIEN（Ciena / 美）|
| **運算晶片 / CPO 推手（新環節，上游）** | NVDA（NVIDIA / 美）、AVGO（Broadcom / 美）、MRVL（Marvell / 美）|
| 電光熱測試 / 探針介面（既有，補入） | KEYS（Keysight / 美 測試量測）|
| 光通訊高彈性 / 收發模組（既有，補入） | FN（Fabrinet / 美 代工）|

每檔含：`sym`、`name`、`tags`（概念標籤）、`note`（一句話定位）。國際龍頭的 note 依公開資訊撰寫，於 spec 與資料中不宣稱來自 CPO 報告。

## 3. 市場自動判斷（前端）

新增純函式 `marketOf(sym)`，吃**完整 sym（含後綴）**，依後綴回傳市場標記字（後綴比對優先，故 `2330.TW` 先命中 `.TW`，不會因「數字開頭」誤判）：

| 後綴 | 市場 | 標記 |
|---|---|---|
| `.TW` | 台灣上市 | 市 |
| `.TWO` | 台灣上櫃 | 櫃 |
| `.ST` | 瑞典 | 瑞 |
| `.MC` | 西班牙 | 西 |
| `.DE` | 德國 | 德 |
| `.PA` | 法國 | 法 |
| `.AS` | 荷蘭 | 荷 |
| `.L` | 英國 | 英 |
| `.HK` | 香港 | 港 |
| `.T` | 日本 | 日 |
| 無後綴（純英文字母） | 美國 | 美 |
| 其他無法判斷 | — | （空，不顯示標記）|

`memberCard`（`web/index.html` 內）目前第 ~1045 行的台股二分判斷
（`/\.TWO$/ ? "櫃" : (/\.TW$/ ? "市" : "")`）改用 `marketOf(sym)`。

`code`（去後綴顯示）也要泛化：目前 `sym.replace(/\.(TW|TWO)$/,"")` 只去台股後綴，
改為去任一已知後綴 `sym.replace(/\.(TW|TWO|ST|MC|DE|PA|AS|L|HK|T)$/,"")`，
讓 SIVE.ST 顯示為 SIVE。美股無後綴不受影響。

## 4. 市場標記樣式（前端 CSS）

既有 `.mstock-mkt` 是單一灰框小標。為區分市場，加市場別配色（淡背景）：
- 台股（市/櫃）：維持現狀（灰框）。
- 美股（美）：藍系淡底。
- 歐股（瑞/西/德/法/荷/英）：橙系淡底。
- 亞股（港/日）：紫系淡底。

以 `marketOf` 回傳值對應 class（如 `.mstock-mkt.us` / `.mstock-mkt.eu` / `.mstock-mkt.asia` / `.mstock-mkt.tw`），單純底色區隔，不喧賓奪主。

## 5. 資料管線（不變）

- 分類定義仍在 `engine/universe/tw_chain.json`，本次只「新增」CPO 鏈的環節與成員。
- `export_chain.py` 抓取/計算/輸出完全不改——對任何 yfinance 代號通用。
- 重跑 `python export_chain.py` 後，新國際龍頭的 r1/r5/r20/volr/flow 會一併產出。
- 抓不到的個股（如未來某代號下市）沿用既有處理：行情欄位 null、顯示「–」、不破版、計入 `failed`。

## 6. 前端相容性

- `memberCard` 的漲跌列、資金徽章、可點 data-stk 全部沿用，跨市場個股一致呈現。
- 點國際龍頭代號 → `openStock` 沿用現有降級（無個股詳情 → 提示頁）。美股 NVDA 已有詳情（_index.json 含 NVDA）。

## 7. 驗證

- **資料層**：跑 `export_chain.py`，確認 CPO 鏈新成員出現、各有行情欄與 flow、市場別齊（台/美/瑞皆有）、JSON 合法、既有台股成員未被破壞。
- **前端層**：headless 測 `marketOf`（各後綴→正確標記）、`memberCard`（美股 NVDA 顯示「美」、歐股 SIVE.ST 顯示「瑞」且 code=SIVE、台股不回歸）。既有 `test_chain_dom.mjs` / `test_search_dom.mjs` / `test_cross_dom.mjs` 不回歸。

## 8. 受影響檔案
- 修改：`engine/universe/tw_chain.json`（CPO 鏈新增環節與國際龍頭成員）
- 修改：`web/index.html`（新增 `marketOf`、`memberCard` 改用之、`code` 後綴泛化、市場標記 CSS）
- 新增：`web/test_chain_intl.mjs`（marketOf 與跨市場 memberCard 測試）
- 資料：`data/tw_chain.json`、`web/data/tw_chain.json`（跑 export 後含國際龍頭行情）

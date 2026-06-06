# 產業鏈跨市場擴充 — 設計（多市場基礎 + CPO 全球龍頭 + AR/XR 新鏈）

日期：2026-06-06
範圍：(A) 讓產業鏈分頁支援多市場個股（台/美/中/港/日/歐），前端依代號後綴自動標記市場；(B) CPO/矽光子鏈補入全球龍頭；(C) 由 Obsidian 研究報告新增「AR/XR 智慧眼鏡」整條產業鏈。

## 1. 目標與非目標

**目標**
- 產業鏈個股可橫跨多市場（台/美/中滬深/港/日/歐），卡片依代號後綴自動顯示市場標記。
- CPO/矽光子鏈納入國際龍頭（美 COHR/LITE/CIEN/NVDA/AVGO/MRVL/FN/KEYS、歐 SIVE.ST）。
- 新增「AR/XR 智慧眼鏡」鏈，內容來自 `D:\obsidian claude\估應鏈研究\AR-XR智慧眼鏡 瓶頸拆鏈分析 2026-06-04.md`，依報告 L0–L7 層級分環節，個股取自報告「個股身分驗證表」。
- 個股 note 濃縮報告精華：角色定位 + 定價狀態/CP 評分（如「L1.0 石墨坩堝 · CP4/4 · 🟢未定價」）。
- 跨市場個股的 1/5/20 日漲跌、資金流向沿用 `export_chain.py` 自動計算（35 檔已驗證 yfinance 可抓）。

**非目標**
- 不改 `export_chain.py` 抓取/計算邏輯（對任何 yfinance 代號通用）、不改 workflow、不改部署。
- 不為非台股加中文名搜尋（搜尋維持代號；中文搜尋功能不受影響）。
- 不加新 UI 區塊或互動（定價狀態寫進 note 文字，不新增欄位/色條）。
- 不處理匯率（不顯示 last；漲跌% 為相對值，跨市場可比）。
- 私有/已下市公司（Lumus、SCHOTT、EVG、JBD、SeeYA、eMagin 等）：在環節 desc 文字提及，但不列為可點個股（無代號）。

## 2. 多市場基礎（前端）

### 2.1 市場判斷 `marketOf(sym)`
吃**完整 sym（含後綴）**，依後綴回傳 `{mkt, cls}`（標記字 + CSS 類）。後綴比對優先，故 `2330.TW` 先命中 `.TW`：

| 後綴 | 市場 | 標記 | cls |
|---|---|---|---|
| `.TW` | 台灣上市 | 市 | tw |
| `.TWO` | 台灣上櫃 | 櫃 | tw |
| `.SS` | 上海 | 滬 | cn |
| `.SZ` | 深圳 | 深 | cn |
| `.HK` | 香港 | 港 | hk |
| `.T` | 東京 | 日 | jp |
| `.DE` | 德國 | 德 | eu |
| `.ST` | 瑞典 | 瑞 | eu |
| `.MC` | 西班牙 | 西 | eu |
| `.PA` | 法國 | 法 | eu |
| `.AS` | 荷蘭 | 荷 | eu |
| `.L` | 倫敦 | 英 | eu |
| 無後綴（純英數，無 `.`） | 美國 | 美 | us |
| 其他 | — | （空） | — |

### 2.2 code 去後綴泛化
`memberCard` 目前 `sym.replace(/\.(TW|TWO)$/,"")` 只去台股後綴。改為去任一已知後綴：
`sym.replace(/\.(TW|TWO|SS|SZ|HK|T|DE|ST|MC|PA|AS|L)$/,"")`，
讓 `688234.SS`→顯示 `688234`、`SIVE.ST`→`SIVE`、`5301.T`→`5301`。美股無後綴不受影響。

### 2.3 `memberCard` 改用 marketOf
第 ~1043-1045 行的 `code` 與 `mkt` 兩行改用上述。`mkt` 標記套對應 cls。

### 2.4 市場標記配色（CSS）
`.mstock-mkt` 加市場別淡底色（區隔但不喧賓奪主）：
- `.tw` 灰（維持現狀）、`.us` 藍系、`.eu` 橙系、`.cn` 紅系、`.hk` 青系、`.jp` 紫系。

## 3. 資料：代號格式約定
資料檔（`engine/universe/tw_chain.json`）一律存 **yfinance 可抓的代號格式**：
- A 股用 `.SS`（上海）/ `.SZ`（深圳）—— 報告若寫 `.SH` 一律轉 `.SS`。
- 港股 `.HK`、日股 `.T`、德股 `.DE`、瑞典 `.ST` 等照 yfinance。
- 撞號注意：港股 `2382.HK`（舜宇光學）≠ 台股 `2382.TW`（廣達），兩者各自獨立成員，不可混。

## 4. CPO/矽光子鏈新增國際龍頭

| 環節 | 新增成員（代號 / 名稱 / 市場） |
|---|---|
| 光源 / 雷射 (ELS)（補入） | SIVE.ST（Sivers / 瑞）|
| **運算晶片 / CPO 推手（新環節，上游）** | NVDA（輝達 / 美）、AVGO（博通 / 美）、MRVL（Marvell / 美）|
| **光收發 / CPO 模組（新環節，中游）** | COHR（Coherent / 美）、LITE（Lumentum / 美）、CIEN（Ciena / 美）|
| 電光熱測試 / 探針介面（補入） | KEYS（Keysight / 美）|
| 光通訊高彈性 / 收發模組（補入） | FN（Fabrinet / 美）|

note 依公開資訊撰寫，不宣稱來自 CPO 報告。

## 5. 新鏈「AR/XR 智慧眼鏡」（id: ar-xr）

依報告 L0–L7 分環節（由上游材料到下游終端）。個股全取自報告兩份驗證表中「有公開代號」者；私有/下市者於 desc 提及不列成員。

| pos | 環節 name | 成員（代號·市場） |
|---|---|---|
| 上游 | L1.0 石墨耗材 / 長晶熱場 | 東海碳素 5301.T、東洋炭素 5310.T、SGL Carbon SGL.DE、晶盛機電 300316.SZ |
| 上游 | L2 光學級 SiC 基板 | 天岳先進 688234.SS、天岳先進(H) 2631.HK、Coherent COHR、Wolfspeed WOLF |
| 上游 | L3 製程 / 設備 (NIL/蝕刻) | Applied Materials AMAT、晶盛機電 300316.SZ（EVG 私有，desc 標註）|
| 中游 | L4 微顯示 (LCoS/microLED/OLED) | 韋爾股份 603501.SS、奇景 HIMX、Sony 6758.T、京東方 000725.SZ |
| 中游 | L4 高折射率玻璃 (繞射波導材料) | AGC 5201.T、Hoya 7741.T、Ohara 5218.T |
| 中游 | L5 光波導 / 微光學 | 廣達 2382.TW、玉晶光 3406.TW、上詮 3363.TWO、亞光 3019.TW、業成 6456.TW（Lumus/SCHOTT 私有，desc 標註）|
| 下游 | L6 系統組裝 / 聲學 / EMS | 歌爾 002241.SZ、立訊 002475.SZ、瑞聲 2018.HK、Knowles KN、Foster 6794.T、EssilorLuxottica EL.PA |
| 周邊 | 相機 / 鏡頭 (CIS) | 大立光 3008.TW、舜宇光學 2382.HK、onsemi ON |
| 周邊 | 被動元件 / 載板 | 村田 6981.T、太陽誘電 6976.T、國巨 2327.TW |
| 周邊 | 主晶片 SoC | Qualcomm QCOM |

鏈層 desc 點出核心命題（多巨頭出貨、層級套利）。每檔 note = 角色 + 層級 + CP評分/定價狀態（取自報告 Step 3/4/5 與 Part 2/3 矩陣），並標註報告的重大修正（Lumus 玻璃波導突破使 SiC「唯一路徑」溢價下修）。

## 6. 資料管線（不變）
- 只「新增/修改」`engine/universe/tw_chain.json` 內容。
- 跑 `python export_chain.py` 後，所有新成員（含中港日歐股）的 r1/r5/r20/volr/flow 一併產出。
- 抓不到者沿用既有處理（null、顯示「–」、計入 failed），不破版。

## 7. 驗證
- **資料層**：跑 `export_chain.py`，確認三/四條鏈成員齊、各市場別都有成員、新成員有行情與 flow、JSON 合法、既有台股成員未破壞、failed 數合理（報告 35 檔已驗證可抓）。
- **前端層**：headless 測 `marketOf`（各後綴 → 正確 mkt/cls，含 `.SS`/`.HK`/`.T`/`.DE`）、`memberCard`（美股顯「美」、滬股 688234.SS 顯「滬」且 code=688234、台股不回歸）。既有 `test_chain_dom.mjs`/`test_search_dom.mjs`/`test_cross_dom.mjs` 不回歸。

## 8. 受影響檔案
- 修改：`engine/universe/tw_chain.json`（CPO 鏈補國際龍頭 + 新增 ar-xr 鏈）
- 修改：`web/index.html`（`marketOf`、`memberCard` 改用之、code 後綴泛化、市場標記 CSS）
- 新增：`web/test_chain_intl.mjs`（marketOf 與跨市場 memberCard 測試）
- 資料：`data/tw_chain.json`、`web/data/tw_chain.json`（跑 export 後含跨市場行情）

## 9. 後續可複用（本次建立的流程）
此 spec 同時建立「Obsidian 研究報告 → 產業鏈」的轉換範式：報告需有「個股身分驗證表（中文名+代號+上市地）」與層級結構，即可由我解析成 `tw_chain.json` 的一條鏈。日後新增報告沿用同法（你丟報告 → 我解析 → 推上線）。

# stockview「5000股」全美股金叉池 設計文件 (spec)

- 日期: 2026-06-12
- 狀態: 已定案，待實作
- 專案: stockview1 (adr-trend-web)，Cloudflare Pages
- 目標站: https://stockview1.pages.dev/ 金叉訊號頁，SP600 右邊新增「5000股」分頁

## 1. 目的
在金叉訊號頁的池分頁列(tw150 / ndx100 / sp500 / sp400 / sp600)最右邊，新增一個涵蓋
**全美股 ~5000 檔**的「5000股」池，顯示當日 EMA20/60 金叉/死叉清單。
資料來源借用本機 golden-cross-screener skill 的「Nasdaq Trader 全美股 universe」，
金叉偵測沿用 stockview 既有引擎口徑（EMA20/60）。

## 2. 已定案決策
- **SKILL 寫入方式**：只借「全美股 universe」(Nasdaq Trader 抓取+排除 ETF/權證/單位/特別股)；金叉偵測/顯示用 stockview 既有口徑。**不**搬 skill 的 techScore/Buy。
- **Universe 範圍**：靜態清單 ~5500 檔；export 時套門檻 price≥$5 且 dolvol20≥$5M，實際輸出 ~3000 檔。
- **評分/CI**：**輕量** — 只金叉清單，**跳過 5 年回測**(1 年日線即可)。
- **接線**：**解耦** — US 池獨立 workflow，**完全不動**現有 ~40 分重流程(零回歸)。
- **更新頻率**：**美股收盤後一天一次**(cron，台灣清晨) + 可手動 dispatch。

## 3. 不做 (YAGNI)
- 不做 5 年回測品質分(其他池有；本池改用 cross_days + 成交額排序)。
- 不進 Web Push(`push_golden_cross.py` 維持只掃既有指數池)。
- 不做 main 表/趨勢榜/爆量/backtest_rank 等重區塊，只做 cross_signals。
- universe 不做 CI 即時抓取，採版控靜態快照(比照既有 sp500.txt)。

## 4. 架構與資料流
```
Nasdaq Trader 全清單 ──(借 skill gc_universe 抓取+過濾)──> engine/universe/us5000.txt (版控靜態, ~5500)
        │
   [獨立 workflow export-us5000.yml：美股收盤後 cron, 台灣清晨]
        │  1) pull_live_data.py：其他池/資料從 live 拉回 public/data/(全快照部署不弄丟其他池)
        │  2) export_us5000.py：產 data/us5000.json，覆蓋到 public/data/
        ▼
   wrangler pages deploy public ──> 全站快照(新鮮 us5000 + 沿用的其他池)
        ▼
   前端「5000股」分頁讀 /data/us5000.json
```

## 5. 元件設計

### 5.1 Universe：engine/universe/us5000.txt
- 內容：Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt`，排除 ETF=Y / Test=Y / 代號含 `$`/`.` / Security Name 含 warrant/unit/right/preferred/depositary 等。
- 產生：借 golden-cross-screener skill 的 `gc_universe.parse_nasdaq_files`(skill 已產出 `~/.claude/skills/golden-cross-screener/universe/us_all.txt`，5579 檔，可直接轉成本檔)。
- 格式：比照既有 universe/*.txt，一行一代號，檔頭 `#` 註明抓取日期與來源。版控(非 gitignore)。
- 更新：過久時重跑 skill 產新快照覆蓋(手動，由我協助)。

### 5.2 引擎：engine/export_us5000.py (全新，獨立，不動 export_json.py)
職責：產生 `data/us5000.json`。流程(stage)：
1. 讀 `engine/universe/us5000.txt`。
2. 分批(100–200/批)下載 **1 年**日線(yfinance，group_by ticker，retry)。
3. 每檔：算 EMA20/EMA60；門檻過濾 `收盤≥5` 且 `近20日 mean(Close×Volume)≥5e6`；不足 60 根→跳過。
4. 偵測金叉/死叉狀態 + `cross_days`(距最近一次交叉的交易日數)，口徑與 stockview 既有 EMA20/60 一致。
5. 組 `cross_signals = {"golden":[...], "death":[...]}`，每列欄位**對齊既有 cross_signals schema**(sym/name/close/cross_days/… )但**無 bt_ 回測欄**。
6. 輸出 `data/us5000.json`：
   ```json
   {"pool":"us5000","pool_label":"5000股","lite":true,
    "generated_at":"...Z","source":"yfinance (daily, 1y, no backtest)",
    "n_list":<universe數>,"n_ok":<通過門檻數>,
    "cross_signals":{"golden":[...],"death":[...]},
    "currencies":["USD"],"failed":[...]}
   ```
- 排序：golden/death 依 `cross_days` 升冪(新鮮優先)、同日再依成交額降冪。
- 失敗/不足誠實標進 `failed`，不編數字。
- 可注入 `downloader`(測試用)。EMA/交叉 helper 盡量重用 `export_json.py` 的對應函式以保口徑一致(import 既有 helper，不複製公式)。

### 5.3 前端：web/index.html
- 第 535 行 `const POOLS = [...]` 末端加 `"us5000"`(SP600 右邊)。
- 加 label map：`const POOL_LABELS = {us5000:"5000股"}`；tab 文字優先取 label map，否則 `p.toUpperCase()`(第 592–594 行渲染處)。
- 金叉表渲染：偵測 `d.lite === true` 或列無 `bt_` 欄 → `crossSignalTable(..., withBacktest=false)`(不顯示回測欄)；本池只渲染 `cross_signals`，趨勢/爆量等區塊跳過(沿用既有「此池資料尚未含…」fallback 或 lite 判斷直接不渲染)。
- index.json 不含 us5000(由重流程產生)→ 前端對缺 index 項已優雅處理(無 cur 徽章)。

### 5.4 部署：.github/workflows/export-us5000.yml (全新)
- 觸發：`schedule` cron 美股收盤後(UTC `30 21 * * 1-5`，對齊既有美股那檔；台灣清晨) + `workflow_dispatch`。
- 步驟：checkout → setup Python 3.11 → `pip install yfinance pandas` →
  `python engine/pull_live_data.py`(沿用其他池/資料) →
  `python engine/export_us5000.py`(覆蓋 data/us5000.json) →
  Stage(`cp -r web/* public/`；`cp data/*.json public/data/`) →
  `wrangler pages deploy public --project-name=${{ vars.CF_PAGES_PROJECT }} --branch=main`。
- 用既有 secrets：`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` / var `CF_PAGES_PROJECT`。
- 與 `export-and-deploy.yml` 用同一 concurrency group 或各自獨立(避免同時部署衝突，採各自 group + cancel-in-progress:false)。
- **現有 export-and-deploy.yml 完全不改。**

## 6. 錯誤處理與成本
- 下載分批 + 批間 sleep + 失敗重試；單檔例外不中斷。
- 成本：1 年日線、無回測，~5500 檔下載 + EMA 計算，預估數分鐘(本機 skill 實測 5500 檔 2.7 分)。CI 容許。
- 解耦後：US 池更新**不重掃**台股+指數的 ~1700 檔重流程，反之亦然。

## 7. 測試
- `engine/test_export_us5000.py`：注入假 downloader，驗
  ① 門檻過濾(低價/低量被排除)；② 金叉/死叉分類與 cross_days；③ 輸出含 `lite:true`/`pool_label`/`n_ok`；④ 缺資料進 failed。
- 前端：用一份 lite us5000.json 樣本，確認分頁出現「5000股」、金叉表無回測欄、其他池不受影響。
- 不破壞既有 `test_cross_signals.py` 等。

## 8. 上線
- 改完直推 main(單人 repo)。
- 首次：手動 `gh workflow run export-us5000.yml --ref main` 產生第一份 data/us5000.json 並部署，驗證「5000股」分頁出現。
- 之後由 cron 美股收盤後自動更新。

---

## 9. 追加範圍 (2026-06-12)：台股全市場池(對稱 lite 池)
使用者追加「台股的掃描」。新增第二個輕量金叉池，與 us5000 **對稱**，引擎**一般化**共用。

### 9.1 決策
- **範圍**：全上市(.TW)+上櫃(.TWO) ~1800 檔。
- **Universe 來源**：`engine/universe/tw_names.json` 的 keys(已帶 .TW/.TWO 後綴；TWSE ISIN 產生)，濾掉 ETF(代號 00xx)/權證(6 位數),留 4 位數普通股 → 靜態快照 `engine/universe/tw_all.txt`。
- **門檻**：**不過濾**(price/dolvol 皆 0)，全上市櫃都掃。
- **幣別**：compute_trend 自動設 `cur="TWD"`(is_tw 判斷 .TW/.TWO)。
- **更新**：**台股收盤後**獨立 workflow(cron `30 6 * * 1-5` = 14:30 台北)。與 us5000(美股收盤後)各自獨立。
- **池 key / label**：`tw_all` / 「台股全市場」。位置 us5000 之後(SP600 右邊兩個新池)。

### 9.2 引擎一般化
原 `export_us5000.py` 改為通用 `engine/export_lite_pool.py`：
`run_lite_pool(pool, label, min_price, min_dolvol, ...)`，CLI `python export_lite_pool.py <us5000|tw_all>`。
PRESETS：`us5000`={label:"5000股", min_price:5, min_dolvol:5e6}；`tw_all`={label:"台股全市場", min_price:0, min_dolvol:0}。
兩池都：批次 compute_trend(1年) → 套門檻 → build_cross_signals(offline,無回測) → data/<pool>.json(lite:true)。

### 9.3 前端 / 部署
- 前端 POOLS 加 `us5000` 與 `tw_all`；label map {us5000:"5000股", tw_all:"台股全市場"}。lite 渲染同 §5.3。
- 兩個獨立 workflow：`export-us5000.yml`(美股收盤後)、`export-tw-all.yml`(台股收盤後)。各自 pull_live→export_lite_pool→deploy。現有 40 分流程不動。

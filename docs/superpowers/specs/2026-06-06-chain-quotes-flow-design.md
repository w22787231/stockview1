# 產業鏈分頁：個股漲跌與資金流向 — 設計

日期：2026-06-06
範圍：在既有「產業鏈」主分頁的每檔個股卡片上，顯示 1/5/20 日漲跌與「資金流向」徽章；資料由新腳本 `export_chain.py` 每日雲端自動更新。

## 1. 目標與非目標

**目標**
- 產業鏈分頁每張個股卡片新增一列：1 日 / 5 日 / 20 日漲跌%（紅綠），與一個「資金流向」徽章。
- 「資金流向」採量比 + 5 日漲幅雙條件，口徑與網站既有「爆量榜」(`surgeGuide`/`volrCls`，inflow 為 volr>=1.5 且 r5>0) 完全一致。
- 行情資料每日台股收盤後由 GitHub Actions 自動更新，比照 `tw_themes.json` 的更新模式。

**非目標**
- 不在環節層 / 鏈層顯示平均漲跌（維持結構清爽）。
- 不顯示三大法人買賣超（yfinance 抓不到，需付費資料源，明確排除）。
- 不改動其他分頁（總體市場、趨勢動能榜、交叉訊號、即時快訊）。
- 不顯示現價 `last`（卡片以結構分類為主，行情為輔；保留欄位於 JSON 但 UI 不顯示）。

## 2. 資料管線

### 2.1 新腳本 `engine/export_chain.py`

比照 `engine/export_themes.py` 的「定義檔與行情產出分離」模式（定義放 `engine/universe/`、產出放 repo 根 `data/`）。

> 設計細化（取代「原地回填同一檔」）：分類定義移到 `engine/universe/tw_chain.json`（純結構，無行情），`export_chain.py` 讀它 → 抓行情 → 輸出 `data/tw_chain.json`（部署 workflow 既有的 `cp data/*.json public/data/` 會帶上），並同步一份到 `web/data/tw_chain.json` 供本機預覽。此法與既有架構一致，且避免讀寫同檔。

- **輸入**：`engine/universe/tw_chain.json`（人工維護的三鏈分類結構，由現有 `web/data/tw_chain.json` 抽出）。
- **輸出**：`data/tw_chain.json`（線上來源）+ `web/data/tw_chain.json`（本機預覽）。
- **抓取**：收集所有 `chains[].stages[].members[].sym`，去重後一次 `yf.download(symbols, period="2mo", interval="1d", group_by="ticker", progress=False, auto_adjust=False)`。
- **逐檔計算**（沿用既有公式）：
  - `r1 / r5 / r20`：`ret_n(closes, n)` = `(closes[-1] / closes[-1-n] - 1) * 100`，資料不足回 `null`。
  - `dv`：`(last20["Close"] * last20["Volume"]).mean()`（20 日均成交金額）。
  - `dv1`：今日 `Close × Volume`。
  - `volr`：`dv1 / dv`（量比），`dv<=0` 時為 `null`。
  - `flow`：見 2.2。
  - `last`：`closes[-1]`（寫入 JSON，UI 暫不顯示）。
- **原地回填**：保留每個 member 既有的 `sym/name/tags/note`，只更新/新增行情欄位 `last/r1/r5/r20/volr/flow`。更新頂層 `generated_at` 為當次 UTC 時間戳。
- **輸出**：覆寫 `web/data/tw_chain.json`。

### 2.2 資金流向 `flow` 判定（與爆量榜同口徑）

以量比 `volr` 與 5 日漲幅 `r5` 雙條件判定，門檻沿用既有 `volrCls()` 的 1.5 / 0.7（爆量榜 inflow 亦為 volr>=1.5 且 r5>0）：

判定順序由上而下，命中即停：

| 條件 | flow | 前端顯示 |
|---|---|---|
| volr 或 r5 為 null | `null` | （不顯示徽章） |
| volr ≥ 1.5 且 r5 > 0 | `inflow` | 🟢 資金流入 |
| volr ≥ 1.5 且 r5 < 0 | `outflow` | 🔴 爆量出貨 |
| volr < 0.7 | `quiet` | ⚪ 縮量觀望 |
| 其餘（含 volr≥1.5 但 r5=0 的平盤爆量、0.7≤volr<1.5） | `neutral` | ◯ 量平 |

判定函式 `flow_of(volr, r5)` 寫在 `export_chain.py`，回傳上述字串或 `None`。

### 2.3 錯誤處理 / 邊界
- 單檔抓取失敗或資料 < 21 根：該檔行情欄位寫 `null`（保留 name/tags/note），不影響其他檔；收集到 `failed` 清單並印出。
- yfinance 整體回傳空 / 例外：不寫檔，保留上一版 `tw_chain.json`（分類結構不丟），以非零 exit code 結束讓 CI 顯示失敗。
- 空 members 的環節（如「對準暨貼合設備」）：跳過，不報錯。

## 3. 前端呈現（`web/index.html`）

改動集中在 `memberCard()` 一個函式 + 一段 CSS。

### 3.1 卡片版面（由上而下）
1. 代號 + 名稱 + 市/櫃標記（原有）
2. 個股標籤膠囊（原有）
3. **新增**：漲跌列 `1日 X%  5日 Y%  20日 Z%`，沿用 `cls()` 上色（漲綠跌紅）、`sgn(v,1)+"%"` 格式；值為 null 顯示「–」。
4. **新增**：資金徽章（4 態，見下）；`flow` 為 null 時整個徽章不渲染。
5. 一句話定位 note（原有）

### 3.2 資金徽章樣式
| flow | 文字 | 配色（沿用 CSS 變數） |
|---|---|---|
| `inflow` | 🟢 資金流入 | 綠底淡 `#e6f6ec` / `var(--green)` |
| `outflow` | 🔴 爆量出貨 | 紅底淡 `#fdeaed` / `var(--red)` |
| `quiet` | ⚪ 縮量觀望 | 灰 `var(--panel2)` / `var(--ink3)` |
| `neutral` | ◯ 量平 | 淡 `var(--panel2)` / `var(--ink2)` |

新增 CSS class：`.mstock-quote`（漲跌列）、`.mstock-flow`（徽章，含 4 個狀態修飾類）。

### 3.3 向下相容
- 舊版 JSON（無 r*/flow 欄位）：漲跌列顯示「–」，徽章不顯示，卡片不破版。`memberCard` 對缺欄位以 `m.r1 ?? null` 等寬鬆讀取。

## 4. GitHub Actions

在 `.github/workflows/export-and-deploy.yml` 中，緊接現有「Export Taiwan themes」步驟後新增一步：

```yaml
- name: Export Taiwan industry chains (quotes + fund flow)
  run: |
    cd engine
    python export_chain.py
```

沿用既有排程（`30 6 * * 1-5` 台股收盤後、手動 `workflow_dispatch`、網頁按鈕 `repository_dispatch`），無需改 cron 或部署步驟。`export_chain.py` 不引入新的 Python 依賴（與 `export_themes.py` 相同，僅需 yfinance）。

## 5. 驗證

- **腳本層**：本機跑 `python export_chain.py`，確認 `tw_chain.json` 被回填、JSON 合法、分類結構（name/tags/note）未被破壞、`flow` 四態都出現過、失敗檔以 null 呈現。
- **前端層**：沿用既有 headless 手法（抽函式 + stub DOM）驗 `memberCard` 對「有行情」「缺行情」「各 flow 態」都渲染正確且不報錯；確認既有 `test_cross_dom.mjs` 仍綠。
- **相容性**：用一份移除 flow 欄位的 JSON 驗證前端不破版。

## 6. 受影響檔案
- 新增：`engine/export_chain.py`
- 修改：`web/index.html`（`memberCard` + CSS）
- 修改：`.github/workflows/export-and-deploy.yml`（加一步）
- 資料：`web/data/tw_chain.json`（執行 export 後行情欄位被回填）

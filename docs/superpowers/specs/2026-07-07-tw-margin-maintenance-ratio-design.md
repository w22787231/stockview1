# 大盤融資維持率 大圖 — 設計文件

日期:2026-07-07
分頁:stockview1「總體市場」

## 目標
在總體市場分頁新增一張「大盤融資維持率」大圖,含:
- 時間按鈕(1M / 3M / 6M / 1Y / 全部)
- 更新時間戳記(重用 `updStamp`,日頻 → 星期X)
- 加權指數(^TWII)疊圖(右軸)
- 130% 斷頭警戒參考線 + 現值卡(最新維持率 + 日變化)

## 口徑(seed 與每日必須一致,否則接縫跳動)
```
維持率% = Σ 上市非ETF個股(融資餘額張 × 1000 × 收盤價) ÷ 上市融資金額總額 × 100
```
- 上市(TWSE)口徑;分子排除 ETF(代號 `00` 開頭)。
- **口徑已確認(2026-07-07)**:採上市,與每日 TWSE 法一致,且對得上 wantgoo/M平方引用的 **194.55%(2026-07-06)**——該來源本身即上市口徑。

### 官方驗證錨點(2026-07-06,供接縫驗證/回填基準)
| 市場 | 融資餘額 | 來源 |
|---|---|---|
| 上市(TWSE) | 6,313.45 億 | MI_MARGN 融資金額今日餘額 631,344,856 仟元 |
| 上櫃(TPEX) | 2,145.64 億 | TPEX balance summary 融資金額 214,564,154 仟元 |
| 全市場 | ≈ 8,459 億 | — |

分母(上市融資金額)= **6,313.45 億**;回填最後一天的維持率應 ≈ 194.55%(容許四捨五入),否則檢查口徑。

## 資料流

### A. 每日更新(上線後,GitHub Actions,免 token)
重用**已存在但未接線**的 `fetch_tw_margin_ratio()`(engine/export_sentiment.py:311):
- TWSE `STOCK_DAY_ALL`(逐檔收盤)
- TWSE `MI_MARGN?selectType=ALL`(融資金額總額 = 分母;逐檔融資張 = 分子權數)
- 讀前一版 published sentiment.json 自我累積歷史。

本設計把它**接進 `build()`**,並改成輸出到獨立 key(見輸出結構),不再塞進 `levels`。

### B. 歷史回補(一次性,本機,FinMind 匿名)
新腳本 `engine/backfill_tw_margin_ratio.py`:
- 視窗:**近 1 年**(約 250 交易日)。
- FinMind datasets:
  - `TaiwanStockMarginPurchaseShortSale`(逐檔融資今日餘額;確認單位 張 vs 股,程式內對齊 STOCK_DAY_ALL 的「張×1000股」口徑)
  - `TaiwanStockPrice`(逐檔收盤)
  - `TaiwanStockTotalMarginPurchaseShortSale`(上市融資金額總額 = 分母)
- **呼叫策略**:優先「一個 dataset 一次抓整段(所有個股 × 1 年)」的 bulk range 呼叫(數個呼叫即可);若匿名額度/payload 被截斷 → 退回逐日迴圈 + `time.sleep` + **可續跑快取**(中間結果落地,被限流後可接續)。
- 上市過濾:用 FinMind 上市清單(排除上櫃/ETF `00*`),與每日 TWSE 口徑對齊。
- `^TWII` 日線(yfinance)一次抓齊,對齊所有日期 → 疊圖欄位 `twii`。
- 產出 **committed 種子檔** `engine/tw_margin_ratio_seed.json`(比照 `insider_seed.json`):
  ```json
  {"method":"...","generated_at":"...","dates":["YYYYMMDD"],"ratio":[...],"twii":[...]}
  ```

### C. 接縫驗證(必做)
回補的**最後一天**維持率,要與 TWSE 每日法(A)算出的同日值相符(容許四捨五入 ~±1pt)。
- 對不上 → 檢查:上市/上櫃過濾、ETF 排除、融資餘額單位(張 vs 股)、分母是否同為上市融資金額。
- 驗證通過才 commit 種子檔。

## 輸出結構(sentiment.json 新增 top-level key)
```json
"tw_margin_ratio": {
  "as_of": "20260706",
  "level": 194.55, "diff": -0.8,
  "dates": ["YYYYMMDD", ...],
  "ratio": [194.55, ...],
  "twii":  [23456.7, ...],
  "note": "上市·不含ETF·斷頭壓力",
  "read": "<130% 斷頭警戒(常見底部);上市口徑,絕對值略高於含上櫃版",
  "src": "TWSE STOCK_DAY_ALL + MI_MARGN(每日自算)· 歷史回補 FinMind",
  "url": "https://www.macromicro.me/charts/53117/taiwan-taiex-maintenance-margin"
}
```
- `build()`:合併 種子 + 前版累積 + 今日 → 去重(以 YYYYMMDD)→ 依日期排序 → 上限 ~750 日(≈3年)。
- `twii`:每日補上今日 ^TWII 收盤;首次以 ^TWII 日線 history 對齊所有既有日期(疊圖恆完整)。

## 前端(web/index.html,總體市場)
- renderMacro 版面新增 `<div id="twMarginRatioBlock"></div>`(擺在台股相關區,如 m1m2 附近)。
- 三函式(沿用 準備金/SOFR 模式):
  - `loadTwMarginRatio()`:讀 sentiment.json 的 `tw_margin_ratio`(已在 loadSentiment 流程內,或獨立 fetch)。
  - `renderTwMarginRatio(d)`:sec-head(標題 + tag「上市·自算·日頻」)+ `updStamp(d.as_of)` + 時間按鈕 + 現值卡 + 圖容器 + legend(口徑說明)。
  - `drawTwMarginRatioChart(d)`:echarts,維持率線(左軸)+ ^TWII(右軸灰虛線,同 reserves/SOFR 樣式)+ 130% markLine(虛線)。時間按鈕只重繪本圖。
- 時間按鈕依 `dates` 長度過濾(資料不足的窗自動隱藏或顯示「全部」)。

## 動到的檔
- `engine/export_sentiment.py` — 接線 `fetch_tw_margin_ratio`、改輸出獨立 key、合併種子、^TWII 疊圖。
- `engine/backfill_tw_margin_ratio.py` — 新增(一次性,本機)。
- `engine/tw_margin_ratio_seed.json` — 新增(committed 種子)。
- `web/index.html` — 新圖 block + render/draw + 插進 renderMacro。

## 相依 / 風險
- FinMind 匿名有額度限制 → bulk 呼叫 + 逐日退路 + 可續跑快取。
- 單位/口徑對齊(張 vs 股、上市 vs 含上櫃、ETF 排除)→ 接縫驗證把關。
- FinMind 只在本機回補時用;CI 每日不需 token。

## 部署
純資料 + 前端。合併 main 後手動 `gh workflow run export-and-deploy.yml --ref main -f skip_stocks=true`(不自動觸發)。

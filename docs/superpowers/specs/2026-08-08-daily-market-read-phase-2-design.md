# 每日市場判讀第二階段：完整檢查表設計

## 目標

把「總體市場 → 每日判讀」擴充為接近參考圖的每日檢查表：同時顯示現值、今日、1D、5D、20D、判讀結論與資料註記，並讓市場主題、確信度與推翻條件使用這些統一口徑。

## 資料分層

### 現有資料，直接重用

- `yieldcurve.json`：2Y、10Y、30Y 名目殖利率與時間序列。
- `tips.json`：10Y TIPS 實質利率與日差。
- `macro.json`：DXY、黃金日變動。
- `macro_score.json`、`sentiment.json`、`us_theme_flow.json`：信用、情緒、廣度與題材輪動。

### 新增 `daily_checklist.json`

新的 Python exporter 只產出檢查表所需的日線資料；來源與口徑如下。

| 指標 | 來源 | 輸出 |
| --- | --- | --- |
| 10Y BEI | FRED `T10YIE` | 現值、今日/1D/5D/20D bps 變化 |
| MOVE | Yahoo Finance `^MOVE` | 現值、今日/1D/5D/20D 點數變化 |
| VIX / VIX3M | Yahoo Finance `^VIX`、`^VIX3M` | 各自現值與比值，並提供方向 |
| RSP / SPY | Yahoo Finance | 相對強弱日、5D、20D 報酬差 |
| IWM / SPY | Yahoo Finance | 相對強弱日、5D、20D 報酬差 |
| KRE / SPY | Yahoo Finance | 相對強弱日、5D、20D 報酬差 |

所有輸出均有 `as_of`、`generated_at`、`source` 與 `availability`。交易日不足或單一來源失敗時，該列的值為 `null`，前端標示「資料待補」。

## 畫面

新分頁的頂部仍保留市場主題、確信度、白話解讀、推翻訊號與今日主角。其下改為表格：

`變數｜現值・資料日｜今日｜1D｜5D｜20D｜判讀結論｜註記`

表格列依參考圖分組：利率／通膨、美元／避險、信用／波動、股票內部。現有六項卡片保留為手機版的摘要展開內容，桌面版以表格為主。

## 判讀規則

- 殖利率與 BEI：以 bp 變化顯示；TIPS 上升為估值壓力，BEI 上升表示通膨預期升溫，兩者拆開判讀。
- 波動：VIX/VIX3M 大於 1 視為短端壓力升高；MOVE 5D 上升視為債市壓力。
- 股市內部：RSP、IWM、KRE 相對 SPY 的 5D 與 20D 同步為負，構成撤退旁證；僅局部分化時支持「板塊輪動」。
- 確信度只計入資料日不過期、且有效的列；缺失與低頻資料不得被標示為即時確認。

## 可靠性與測試

- exporter 單元測試：交易日缺少、20D 不足、相對報酬、VIX/VIX3M 比值、BEI bp 轉換。
- 前端測試：新增資料檔被 `pull_live_data.py` 覆蓋；桌面表格與手機摘要均有固定欄位；缺資料不計入確信度。
- GitHub Actions 在既有 `export-and-deploy` 中執行 exporter、驗證 JSON 後部署；web-only 部署則沿用線上最新 `daily_checklist.json`。

## 非目標

- 不使用盤中或付費資料，不承諾逐秒即時。
- 不新增自動交易訊號或買賣建議。

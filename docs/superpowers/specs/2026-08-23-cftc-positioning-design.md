# CFTC 機構持倉水位設計

## 目標

在「總體市場 → 每日判讀 → 結構圖表」新增可自動更新的 CFTC 持倉水位圖，讓使用者能比較機構與槓桿基金在主要金融期貨的方向與擁擠程度。

## 資料範圍與來源

- 唯一原始來源為 CFTC 的年度歷史壓縮檔，不需要 API 金鑰。
- 金融期貨使用 `fut_fin_txt_<year>.zip` 的 TFF futures-only 報告：E-mini S&P 500、Nasdaq Mini、UST 10Y Note、USD Index、VIX Futures。
- 黃金使用 `fut_disagg_txt_<year>.zip` 的 Disaggregated futures-only 報告，標的為 COMEX Gold。
- 每次匯出下載目前年份與往前五個完整年份；因此 5Y 按鈕至少有足夠的週資料。
- CFTC 資料的持倉日是週二、通常於週五發布。頁面須同時呈現持倉日與資料來源，不能把它當成即時資料。

## 定義與正確性

- 淨持倉水位（Net OI %）=`100 × (多單合約 − 空單合約) ÷ 未平倉量`。
- 金融市場的兩條線：`Asset Manager / Institutional` 與 `Leveraged Funds`。
- 「槓桿基金」只可標示為「對沖基金可觀測代理」，不可稱為所有對沖基金的完整持倉。
- 黃金只有 `Managed Money` 一條水位線；不可用金融期貨類別冒充黃金的資產管理機構資料。
- 最新 4 週變化為最新水位減四週前水位，單位為百分點。
- 歷史百分位採可得的最近三年週資料，並以 `值 ≤ 最新值` 的比例計算。
- 缺欄位、零未平倉量、重複日期、找不到精準合約名稱時，該市場輸出空資料與原因，不得以其他合約替代。

## 使用者介面

- 新卡片標題為「機構／槓桿基金持倉水位（CFTC）」。
- 卡片內提供六個市場切換鈕：S&P 500、Nasdaq 100、10Y 美債、美元指數、VIX、黃金。
- 主圖顯示選定市場的週度 Net OI %；金融市場顯示兩線，黃金顯示 Managed Money 一線。
- 保留既有 1M、3M、6M、1Y、3Y、5Y、ALL 時間按鈕；時間範圍僅濾圖，不改變計算。
- 圖下顯示最新水位、4W 變化、3Y 百分位與資料截至日。無資料時顯示來源失敗訊息。
- 圖例與腳註說明資料頻率、持倉日／發布日落差與槓桿基金口徑。

## 系統整合與限制

- 在 `engine/export_daily_checklist.py` 產生 `charts.cftc_positioning`，不新增前端即時跨網域請求。
- 資料匯出須在網路失敗時產出可用的空結構，避免整個每日判讀 JSON 失效。
- `.github/workflows/export-and-deploy.yml` 的正常資料匯出必須執行此更新；`web_only` 不重算資料。
- 不新增第三方套件；使用 Python 標準庫、pandas、numpy 與既有 ECharts。


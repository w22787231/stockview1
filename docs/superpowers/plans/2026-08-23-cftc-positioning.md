# CFTC Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每日判讀提供可自動更新、可切換市場與期間的 CFTC 機構／槓桿基金持倉水位圖。

**Architecture:** 將 CFTC 年度 ZIP 檔在 Python 匯出階段轉換為小型 JSON 圖表資料，前端只載入既有的每日判讀 JSON 並用 ECharts 呈現。金融期貨與黃金採各自正確的 CFTC 報告分類，不混用類別。

**Tech Stack:** Python 3.11、標準庫 zipfile/urllib、pandas、numpy、ECharts 5、Node DOM tests。

**Spec:** `docs/superpowers/specs/2026-08-23-cftc-positioning-design.md`

## Global Constraints

- 只使用 CFTC 官方年度壓縮檔，且不需要 API 金鑰。
- Net OI % 固定為 `100 × (多單 − 空單) ÷ 未平倉量`。
- 金融期貨最多六年資料，前端所有既有時間按鈕都要可用。
- 槓桿基金只能標示為對沖基金可觀測代理。
- 網路或資料格式失敗時輸出空結構，不可使每日判讀失效。

---

### Task 1: CFTC 資料標準化與測試

**Files:**
- Modify: `engine/export_daily_checklist.py`
- Modify: `engine/test_daily_checklist.py`

**Interfaces:**
- Produces: `cftc_net_oi(long, short, open_interest) -> float | None`
- Produces: `cftc_percentile(values, years=3) -> int | None`
- Produces: `build_cftc_positioning(now=None) -> dict`

- [ ] 寫入以手算數字驗證 Net OI %、零未平倉量與三年百分位的失敗測試。
- [ ] 執行 `python engine/test_daily_checklist.py`，確認新函式尚未定義而失敗。
- [ ] 以最小程式實作 ZIP 下載、精準合約比對、淨持倉與空資料契約。
- [ ] 重跑 Python 測試並提交資料匯出變更。

### Task 2: 每日判讀資料契約與圖表

**Files:**
- Modify: `engine/export_daily_checklist.py`
- Modify: `web/index.html`
- Modify: `web/test_daily_read.mjs`

**Interfaces:**
- Consumes: `charts.cftc_positioning.markets[market_key]` with `series`, `metrics`, `as_of`, and `note`.
- Produces: `renderDailyCftcPositioningChart(id, block, market, win)`.

- [ ] 寫入每日判讀 CFTC 容器、圖名與市場切換按鈕的失敗 DOM 測試。
- [ ] 執行 `node web/test_daily_read.mjs` 確認失敗。
- [ ] 實作六市場選擇、全部時間按鈕、金融雙線／黃金單線、統計數字與說明。
- [ ] 重跑 Python、Node 測試並提交前端變更。

### Task 3: 部署資料保護與視覺驗證

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml`
- Modify: `engine/test_daily_checklist.py`

- [ ] 寫入 `charts.cftc_positioning` 必須存在的資料契約測試。
- [ ] 在正常匯出流程驗證產物包含 CFTC 結構；`web_only` 維持不重算資料。
- [ ] 執行 `python engine/export_daily_checklist.py`、Python 與 Node 測試。
- [ ] 在瀏覽器驗證預設市場、一次市場切換、一次 5Y 時間切換及窄螢幕顯示。
- [ ] 提交部署保護變更。


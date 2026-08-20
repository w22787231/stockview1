# TGA 與銀行準備金自動預估 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在總體市場提供可自動更新的 TGA 與銀行準備金 1 個月、3 個月模型預估圖與摘要數字。

**Architecture:** 新增獨立 Python 匯出器，讀取 FRED 的 TGA、準備金、Fed 資產與 RRP，產生版控外的 `data/liquidity_forecast.json`。預估器輸出實際、基準、寬鬆、緊縮序列與摘要；單頁前端只負責讀取、切換期間及畫圖。

**Tech Stack:** Python、pandas、FRED CSV/API、靜態 JSON、ECharts、Node DOM tests。

**Spec:** `docs/superpowers/specs/2026-08-20-tga-reserves-forecast-design.md`

## Global Constraints

- 僅將模型結果標示為「預估／情境」，不可稱為官方預測。
- TGA 使用日頻、準備金使用週頻；圖表必須明顯區分實際實線與預估虛線。
- 來源缺失、落後超過兩個頻率週期或樣本不足時，不輸出預估資料。
- TGA 預估取最近三完整年度同日曆窗口變動的中位數、25%、75% 分位數。
- 準備金使用 `ΔWRESBAL = ΔWALCL − ΔTGA − ΔRRP + 校正殘差` 的 13 週中位數推導，RRP 下限為零。

---

### Task 1: 建立預估資料匯出器與單元測試

**Files:**
- Create: `engine/export_liquidity_forecast.py`
- Create: `engine/test_liquidity_forecast.py`

**Interfaces:**
- Consumes: `fetch_pi.fetch_fred(series, start)`；輸入 `WTREGEN`、`WRESBAL`、`WALCL`、`RRPONTSYD` 的 pandas Series。
- Produces: `build_forecast(series_map, as_of=None) -> dict`，回傳 `tga`、`reserves` 的 actual/base/loose/tight 序列與 `summary`。

- [ ] **Step 1: 寫出失敗的 TGA 路徑測試**

```python
def test_tga_forecast_has_21_and_63_business_days():
    result = F.build_forecast(sample_series())
    assert len(result["tga"]["base"]["1m"]["dates"]) == 21
    assert len(result["tga"]["base"]["3m"]["dates"]) == 63
    assert result["tga"]["loose"]["1m"]["values"][-1] <= result["tga"]["tight"]["1m"]["values"][-1]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python engine/test_liquidity_forecast.py`

Expected: FAIL，因 `export_liquidity_forecast.py` 尚不存在。

- [ ] **Step 3: 實作 TGA 情境路徑**

```python
def tga_paths(tga: pd.Series, days: int) -> dict:
    future = pd.bdate_range(tga.index[-1] + pd.offsets.BDay(), periods=days)
    samples = [historical_change_for_calendar_day(tga, d, years=3) for d in future]
    return {
        "base": accumulate(tga.iloc[-1], [median(x) for x in samples]),
        "loose": accumulate(tga.iloc[-1], [quantile(x, .25) for x in samples]),
        "tight": accumulate(tga.iloc[-1], [quantile(x, .75) for x in samples]),
    }
```

- [ ] **Step 4: 加入準備金推導與資料保護**

```python
def reserve_paths(wresbal, walcl, rrp, tga_path, weeks):
    walcl_step = median_weekly_change(walcl, 13)
    rrp_step = median_weekly_change(rrp, 13)
    residual = median_weekly_residual(wresbal, walcl, rrp, 13)
    return project_reserves(wresbal.iloc[-1], walcl_step, rrp_step, residual, tga_path, weeks)

def build_forecast(series_map, as_of=None):
    if not all_fresh_and_sufficient(series_map):
        return {"generated_at": utc_now(), "status": "insufficient_data", "tga": {}, "reserves": {}}
```

- [ ] **Step 5: 擴充測試並執行**

```python
def test_reserves_floor_rrp_and_missing_data():
    result = F.build_forecast(sample_series(rrp_declines_to_zero=True))
    assert min(result["assumptions"]["rrp_path"]) >= 0
    assert F.build_forecast({"WTREGEN": pd.Series(dtype=float)})["status"] == "insufficient_data"
```

Run: `python engine/test_liquidity_forecast.py`

Expected: PASS。

- [ ] **Step 6: 寫入 JSON 並提交**

```python
if __name__ == "__main__":
    payload = build_from_fred()
    write_json("../data/liquidity_forecast.json", payload)
```

Run: `python engine/export_liquidity_forecast.py`

Commit:

```bash
git add engine/export_liquidity_forecast.py engine/test_liquidity_forecast.py
git commit -m "feat: add liquidity forecast exporter"
```

### Task 2: 將預估資料加入部署更新流程

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml:498-540`
- Modify: `engine/pull_live_data.py`（若 web-only 流程需保留既有預估 JSON）

**Interfaces:**
- Consumes: `engine/export_liquidity_forecast.py` 成功寫出的 `data/liquidity_forecast.json`。
- Produces: 部署 `web/data/liquidity_forecast.json`，並在匯出失敗時沿用線上有效版本。

- [ ] **Step 1: 寫出部署資料存在性測試**

```javascript
assert.ok(PULL_LIVE_TARGETS.includes("liquidity_forecast.json"));
assert.ok(html.includes("data/liquidity_forecast.json"));
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `npm.cmd --prefix web test`

Expected: FAIL，因工作流與前端尚未引用新資料檔。

- [ ] **Step 3: 在主部署工作流產出及保留資料**

```yaml
- name: Export TGA and reserve forecast
  env:
    FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
  run: |
    cd engine
    python export_liquidity_forecast.py || \
      curl -fsS "https://stockview1.pages.dev/data/liquidity_forecast.json" -o ../data/liquidity_forecast.json
```

- [ ] **Step 4: 讓 web-only 拉取包含資料檔**

```python
TOP_FILES.add("liquidity_forecast.json")
```

- [ ] **Step 5: 執行資料同步與全部測試**

Run: `python engine/test_liquidity_forecast.py; npm.cmd --prefix web test`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add .github/workflows/export-and-deploy.yml engine/pull_live_data.py web/test_data_pull_sync.mjs
git commit -m "ci: publish liquidity forecast data"
```

### Task 3: 新增總體市場預估摘要與圖表

**Files:**
- Modify: `web/index.html:1490-1502, 1600-1680, 3207-3213`
- Modify: `web/test_daily_read.mjs` 或 create `web/test_liquidity_forecast_dom.mjs`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `data/liquidity_forecast.json`，其中 `tga` 與 `reserves` 各包含 `actual`、`base`、`loose`、`tight`、`summary`。
- Produces: `renderLiquidityForecast(data)`；按鈕狀態 `LIQUIDITY_FORECAST_WIN`，可取值 `"1m"` 或 `"3m"`。

- [ ] **Step 1: 寫出失敗的 DOM／圖表選項測試**

```javascript
const data = fixtureForecast();
api.renderLiquidityForecast(data);
assert.ok(BOX_HTML.includes("TGA 與銀行準備金預估"));
assert.strictEqual(CAP.series.filter(s => s.lineStyle?.type === "dashed").length, 6);
assert.ok(BOX_HTML.includes('data-liquidity-forecast-win="1m"'));
assert.ok(BOX_HTML.includes('data-liquidity-forecast-win="3m"'));
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `node web/test_liquidity_forecast_dom.mjs`

Expected: FAIL，因 `renderLiquidityForecast` 尚不存在。

- [ ] **Step 3: 載入資料並實作摘要區**

```javascript
let LIQUIDITY_FORECAST = null;
let LIQUIDITY_FORECAST_WIN = "1m";

async function loadLiquidityForecast(){
  LIQUIDITY_FORECAST = await fetch("data/liquidity_forecast.json").then(r => r.ok ? r.json() : null).catch(() => null);
}
```

摘要必須顯示最新實際值、資料日期、基準 1M／3M 終點與變動；當 `status !== "ok"` 時只顯示資料待補與原因。

- [ ] **Step 4: 實作雙圖與情境帶**

```javascript
function forecastSeries(name, block, color){
  return [
    actualLine(name + " 實際", block.actual, color),
    forecastLine(name + " 基準", block.base[LIQUIDITY_FORECAST_WIN], color),
    forecastLine(name + " 寬鬆", block.loose[LIQUIDITY_FORECAST_WIN], "#16a34a"),
    forecastLine(name + " 緊縮", block.tight[LIQUIDITY_FORECAST_WIN], "#dc2626"),
  ];
}
```

實際線必須為實線；三條預估線必須為虛線；圖下固定呈現模型公式與來源。

- [ ] **Step 5: 連接總體市場載入與測試**

```javascript
await Promise.all([loadMacro(), loadLiquidityForecast()]);
renderLiquidityForecast(LIQUIDITY_FORECAST);
```

Run: `npm.cmd --prefix web test`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add web/index.html web/test_liquidity_forecast_dom.mjs web/package.json
git commit -m "feat: show TGA and reserve forecasts"
```

### Task 4: 端到端資料驗證與發布檢查

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml:573-585`
- Test: `engine/test_liquidity_forecast.py`, `web/test_liquidity_forecast_dom.mjs`

**Interfaces:**
- Consumes: 已部署的 `https://stockview1.pages.dev/data/liquidity_forecast.json`。
- Produces: 部署工作流在資料不存在、JSON 無效或沒有預估欄位時失敗。

- [ ] **Step 1: 加入部署驗證命令**

```bash
curl -fsS "$URL/data/liquidity_forecast.json" -o liquidity_forecast.json
python -c "import json; d=json.load(open('liquidity_forecast.json')); assert d['status']=='ok'; assert d['tga']['base']['1m']['values']; assert d['reserves']['base']['3m']['values']"
```

- [ ] **Step 2: 執行本機完整驗證**

Run: `python engine/test_liquidity_forecast.py; python engine/test_daily_checklist.py; npm.cmd --prefix web test; git diff --check`

Expected: 全部 PASS，無空白差異。

- [ ] **Step 3: 提交最終驗證設定**

```bash
git add .github/workflows/export-and-deploy.yml
git commit -m "test: verify deployed liquidity forecast"
```

## Self-Review

- 規格中的資料來源、1M／3M、三情境、資料不足保護、圖表揭露及部署驗證分別由 Task 1–4 覆蓋。
- 所有後續引用的 JSON 欄位與函式在 Task 1 或 Task 3 明確定義。
- 未包含未定義的待辦事項、占位符或未驗證的官方預測主張。

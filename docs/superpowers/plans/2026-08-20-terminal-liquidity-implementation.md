# 期末美元流動性三線模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每日判讀提供 TGA、銀行準備金與完整淨流動性的月末／季末預估點，以及六項獨立抽放水因子卡。

**Architecture:** `engine/export_liquidity_forecast.py` 以 FRED H.4.1 帳戶建立週頻實際水位，解析財政部最新融資估計中的官方 TGA 季末目標，再計算未來月末／季末的單點水位。前端讀取同一 JSON，在單一 ECharts 圖中畫三條實際／期末預估線，並從 `factors` 陣列渲染六張獨立因子卡。

**Tech Stack:** Python 3、pandas、FRED 官方 CSV、Treasury.gov 公告 HTML、原生 HTML/JavaScript、ECharts 5.5.0、Node 測試。

**Spec:** `docs/superpowers/specs/2026-08-20-terminal-liquidity-design.md`

## Global Constraints

- 所有金額在 JSON 內以百萬美元保存；前端顯示 B 或 T。
- 未來資料只能為月末／季末節點，禁止產生每日或每週累加預測線。
- TGA 官方期末目標必須優先於模型；缺少官方來源時必須標示 `model`。
- 三條線不得互相加總；完整淨流動性必須使用固定帳戶定義。
- 任一主要序列缺失時不得以零補值，必須保留資料日並降低信心或回傳不足資料。

---

### Task 1: 建立期末預估 JSON 契約與單元測試

**Files:**
- Modify: `engine/test_liquidity_forecast.py`
- Modify: `engine/export_liquidity_forecast.py`

**Interfaces:**
- Consumes: `dict[str, pandas.Series]`（FRED 原始序列）與 `list[dict]`（官方 TGA 目標）。
- Produces: `build_terminal_forecast(series_map, tga_targets, generated_at) -> dict`；結果包含 `tga`、`reserves`、`full_liquidity`、`factors`、`targets`。

- [ ] **Step 1: 寫入失敗測試，固定輸出契約與官方優先規則**

```python
result = F.build_terminal_forecast(sample_series(), [
    {"date": "2026-12-31", "value": 850000, "source_type": "official"}
], "2026-08-20T00:00:00Z")
assert result["status"] == "ok"
assert result["tga"]["forecast"][-1]["value"] == 850000
assert result["tga"]["forecast"][-1]["source_type"] == "official"
assert len(result["factors"]) == 6
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python engine\test_liquidity_forecast.py`

Expected: FAIL，因為 `build_terminal_forecast` 尚不存在。

- [ ] **Step 3: 實作資料結構與最小端點產生器**

```python
def terminal_dates(as_of, months=6):
    end = pd.Timestamp(as_of) + pd.offsets.MonthEnd(1)
    return [date.strftime("%Y-%m-%d") for date in pd.date_range(end, periods=months, freq="ME")]

def build_terminal_forecast(series_map, tga_targets, generated_at=None):
    actual = {key: _block(series) for key, series in series_map.items()}
    dates = terminal_dates(series_map["WTREGEN"].index[-1])
    forecast = build_forecast_points(actual, dates, tga_targets)
    return {"status": "ok", "generated_at": generated_at,
            "tga": forecast["tga"], "reserves": forecast["reserves"],
            "full_liquidity": forecast["full_liquidity"], "factors": forecast["factors"]}
```

- [ ] **Step 4: 執行資料單元測試**

Run: `python engine\test_liquidity_forecast.py`

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add engine/export_liquidity_forecast.py engine/test_liquidity_forecast.py
git commit -m "feat: define terminal liquidity forecast contract"
```

### Task 2: 取得官方 TGA 期末目標與六項來源資料

**Files:**
- Modify: `engine/export_liquidity_forecast.py`
- Modify: `engine/test_liquidity_forecast.py`

**Interfaces:**
- Consumes: Treasury.gov Quarterly Refunding／Marketable Borrowing Estimates HTML、FRED `WTREGEN`、`WRESBAL`、`WALCL`、`RRPONTSYD`、`CURRCIR` 與可用的 FIMA／其他 Fed 負債序列。
- Produces: `fetch_treasury_tga_targets(http_get) -> list[dict]` 與 `fetch_factor_series() -> dict[str, pandas.Series]`。

- [ ] **Step 1: 寫入官方文字解析與缺值降級測試**

```python
html = "During the October–December 2026 quarter, Treasury assumes an end-of-December cash balance of $850 billion."
targets = F.parse_treasury_tga_targets(html)
assert targets == [{"date": "2026-12-31", "value": 850000, "source_type": "official", "confidence": "high"}]
assert F.factor_status(pd.Series(dtype=float)) == "missing"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python engine\test_liquidity_forecast.py`

Expected: FAIL，因為解析器與因子狀態函式尚不存在。

- [ ] **Step 3: 實作來源抓取、來源中繼資料與明確降級**

```python
FACTOR_SPECS = {
    "tga": {"series": "WTREGEN", "sign": -1},
    "walcl": {"series": "WALCL", "sign": 1},
    "rrp": {"series": "RRPONTSYD", "sign": -1, "scale": 1000},
    "currency": {"series": "CURRCIR", "sign": -1},
}
def parse_treasury_tga_targets(html):
    matches = re.findall(r"([A-Z][a-z]+)–([A-Z][a-z]+) (\\d{4}) quarter.*?end-of-([A-Z][a-z]+) cash balance of \\$([0-9,.]+) (billion|trillion)", html, re.S)
    return [to_target(year, month, amount, unit) for _, _, year, month, amount, unit in matches]
```

- [ ] **Step 4: 執行測試確認解析、來源標示與缺值降級通過**

Run: `python engine\test_liquidity_forecast.py`

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add engine/export_liquidity_forecast.py engine/test_liquidity_forecast.py
git commit -m "feat: fetch official TGA targets and liquidity factors"
```

### Task 3: 實作獨立的期末水位計算

**Files:**
- Modify: `engine/export_liquidity_forecast.py`
- Modify: `engine/test_liquidity_forecast.py`

**Interfaces:**
- Consumes: Task 1 的端點、Task 2 的實際序列與 TGA 官方／模型目標。
- Produces: `forecast_components()`、`forecast_reserves()`、`forecast_full_liquidity()`；每個節點使用 `value`、`change`、`source_type`、`confidence`。

- [ ] **Step 1: 寫入會計方向與非重複計算測試**

```python
components = {"walcl": 10000, "tga": 5000, "rrp": -2000, "currency": 3000, "fima_other": 1000}
assert F.reserve_change(components) == 3000
assert F.full_liquidity_change(components) == 3000
assert F.reserve_change({**components, "tga": 10000}) == -2000
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python engine\test_liquidity_forecast.py`

Expected: FAIL，因為期末組件計算函式尚不存在。

- [ ] **Step 3: 實作各因子的期末變化與三條獨立水位**

```python
def reserve_change(delta):
    return delta["walcl"] - delta["tga"] - delta["rrp"] - delta["currency"] - delta["fima_other"]

def full_liquidity_value(levels):
    return levels["walcl"] - levels["tga"] - levels["rrp"] - levels["currency"] - levels["fima_other"]
```

- [ ] **Step 4: 執行測試確認 TGA 官方覆蓋、準備金與完整淨流動性均只計入一次**

Run: `python engine\test_liquidity_forecast.py`

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add engine/export_liquidity_forecast.py engine/test_liquidity_forecast.py
git commit -m "feat: calculate terminal liquidity levels"
```

### Task 4: 在每日判讀渲染三線圖與六項因子卡

**Files:**
- Modify: `web/index.html:1567,2112-2143`
- Create: `web/test_terminal_liquidity_dom.mjs`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `data/liquidity_forecast.json` 的 Task 3 契約。
- Produces: `renderLiquidityForecast(data)` 的三張期末卡、三條 ECharts 線、六張 `[data-liquidity-factor]` 因子卡，以及 1M／3M／6M 範圍按鈕。

- [ ] **Step 1: 寫入前端 DOM 測試**

```javascript
assert.match(html, /期末美元流動性預估/);
assert.match(html, /TGA 期末預估/);
assert.match(html, /銀行準備金期末預估/);
assert.match(html, /完整淨流動性期末預估/);
assert.match(html, /data-liquidity-factor/);
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `node web\test_terminal_liquidity_dom.mjs`

Expected: FAIL，因為三線圖與因子卡尚未存在。

- [ ] **Step 3: 更新前端渲染與圖表函式**

```javascript
const terminalLine = (name, block, color, axis) => ({
  name, type: "line", yAxisIndex: axis, showSymbol: true,
  data: block.actual.concat(block.forecast).map(point => [toMs(point.date), point.value])
});
const series = [
  terminalLine("TGA 期末預估", data.tga, "#d97706", 0),
  terminalLine("銀行準備金期末預估", data.reserves, "#0d9488", 1),
  terminalLine("完整淨流動性期末預估", data.full_liquidity, "#1f6feb", 1),
];
```

- [ ] **Step 4: 將新前端測試加入既有測試命令並執行全部測試**

Run: `npm.cmd --prefix web test`

Expected: PASS，含新的 DOM 測試與既有 ECharts 煙霧測試。

- [ ] **Step 5: Commit**

```powershell
git add web/index.html web/test_terminal_liquidity_dom.mjs web/package.json
git commit -m "feat: render terminal liquidity chart and factor cards"
```

### Task 5: 整合工作流、端對端資料驗證與手動檢查

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml:518-528,595`
- Modify: `engine/pull_live_data.py:51-54`
- Modify: `engine/test_liquidity_forecast.py`

**Interfaces:**
- Consumes: Task 3 JSON 產生器與 Task 4 前端資料需求。
- Produces: 每次完整資料更新都重新生成 `data/liquidity_forecast.json`；web-only 更新沿用上次有效 JSON。

- [ ] **Step 1: 寫入工作流資料存在性與 JSON 欄位測試**

```python
payload = F.build_terminal_forecast(sample_series(), sample_targets())
assert payload["status"] == "ok"
assert all(key in payload for key in ("tga", "reserves", "full_liquidity", "factors"))
assert all("confidence" in point for point in payload["tga"]["forecast"])
```

- [ ] **Step 2: 執行測試確認失敗或新增斷言尚未滿足**

Run: `python engine\test_liquidity_forecast.py`

Expected: FAIL，直到完整預測 JSON 與資料保留規則就緒。

- [ ] **Step 3: 更新資料更新工作流與 web-only 保留清單**

```yaml
- name: Export terminal liquidity forecasts
  if: ${{ github.event.inputs.web_only != 'true' }}
  run: |
    cd engine
    python export_liquidity_forecast.py
```

- [ ] **Step 4: 執行完整驗證**

Run: `python engine\test_liquidity_forecast.py; npm.cmd --prefix web test; git diff --check`

Expected: 全部 PASS，無空白錯誤。

- [ ] **Step 5: Commit**

```powershell
git add .github/workflows/export-and-deploy.yml engine/pull_live_data.py engine/test_liquidity_forecast.py
git commit -m "chore: publish terminal liquidity data"
```

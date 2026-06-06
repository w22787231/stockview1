# 產業鏈分頁：個股漲跌與資金流向 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有「產業鏈」主分頁的每張個股卡片上顯示 1/5/20 日漲跌與「資金流向」徽章，資料由新腳本 `export_chain.py` 每日雲端自動更新。

**Architecture:** 比照 `export_themes.py` 的「定義檔放 `engine/universe/`、行情產出放 repo 根 `data/`」分離模式。新增 `engine/universe/tw_chain.json`（純分類結構，無行情）作為定義來源；`export_chain.py` 讀它 → 一次抓 yfinance → 算 `r1/r5/r20/volr/flow` → 輸出 `data/tw_chain.json`（部署時 workflow 自動複製進 `public/data/`），並同步一份到 `web/data/tw_chain.json` 供本機預覽。前端僅改 `memberCard()` 加一列漲跌與徽章。

**Tech Stack:** Python 3 + yfinance（無新依賴）、原生 JS/CSS、GitHub Actions、Node(headless 驗證，沿用既有手法)。

---

## 路徑與資料流（重要背景）

- engine 腳本一律寫到 **repo 根 `data/`**（透過 `os.path.join(HERE, "..", "data")`）。
- 部署 workflow 把 `web/*` → `public/`，再把 `data/*.json` → `public/data/`（覆蓋）。前端線上 fetch 的 `data/xxx.json` 來自 repo 根 `data/`。
- `web/data/` 是本機開發副本（`python -m http.server` 在 `web/` 起站時 fetch 的對象）。
- 既有 `tw_chain.json`（上一個任務手建的分類結構）目前只在 `web/data/`。本計畫 Task 1 會把它的純結構版本移到 `engine/universe/tw_chain.json` 當定義檔。

## 檔案結構

- **Create** `engine/universe/tw_chain.json` — 純分類結構定義（chains→stages→members，每個 member 僅 sym/name/tags/note），無行情欄位。Task 1。
- **Create** `engine/export_chain.py` — 讀定義 → 抓 yfinance → 算 r1/r5/r20/volr/flow → 輸出 `data/tw_chain.json` + 同步 `web/data/tw_chain.json`。Task 2–4。
- **Create** `engine/test_export_chain.py` — 單元測試 `flow_of()` 與行情合併邏輯。Task 2–3。
- **Modify** `web/index.html` — `memberCard()` 加漲跌列與徽章 + CSS。Task 5–6。
- **Create** `web/test_chain_dom.mjs` — headless 驗 `memberCard` 各情境。Task 6。
- **Modify** `.github/workflows/export-and-deploy.yml` — 加一步跑 `export_chain.py`。Task 7。

---

## Task 1: 抽出分類定義檔到 engine/universe/

把 `web/data/tw_chain.json` 的純結構（移除任何行情欄位，目前本就只有 sym/name/tags/note）複製成定義檔，放到 engine 慣例位置。

**Files:**
- Create: `engine/universe/tw_chain.json`

- [ ] **Step 1: 複製現有結構為定義檔**

```bash
cd /c/Users/u9914/adr-trend-web
cp web/data/tw_chain.json engine/universe/tw_chain.json
```

- [ ] **Step 2: 驗證定義檔合法且結構完整**

Run:
```bash
node -e "const d=require('./engine/universe/tw_chain.json'); let m=0; d.chains.forEach(c=>c.stages.forEach(s=>m+=s.members.length)); console.log('chains='+d.chains.length,'members='+m); const bad=[]; d.chains.forEach(c=>c.stages.forEach(s=>s.members.forEach(x=>{if(!x.sym||!x.name)bad.push(x)}))); console.log('缺sym/name:',bad.length)"
```
Expected: `chains=3 members=43`、`缺sym/name: 0`

- [ ] **Step 3: Commit**

```bash
git add engine/universe/tw_chain.json
git commit -m "feat: 抽出產業鏈分類定義到 engine/universe/tw_chain.json"
```

---

## Task 2: export_chain.py 骨架與 flow_of() — TDD

先寫 `flow_of()`（資金流向判定，純函式好測）與測試。

**Files:**
- Create: `engine/export_chain.py`
- Test: `engine/test_export_chain.py`

- [ ] **Step 1: 寫失敗測試**

Create `engine/test_export_chain.py`：

```python
# -*- coding: utf-8 -*-
"""export_chain 單元測試：flow_of 判定 + merge 行情合併。"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from export_chain import flow_of, merge_quotes


def test_flow_inflow():
    # 量比放大且上漲 → 資金流入
    assert flow_of(2.0, 5.0) == "inflow"
    assert flow_of(1.5, 0.1) == "inflow"


def test_flow_outflow():
    # 量比放大但下跌 → 爆量出貨
    assert flow_of(2.0, -3.0) == "outflow"


def test_flow_quiet():
    # 縮量 → 觀望（不論漲跌）
    assert flow_of(0.5, 4.0) == "quiet"
    assert flow_of(0.69, -4.0) == "quiet"


def test_flow_neutral():
    # 量平、或爆量但平盤 → 量平
    assert flow_of(1.0, 2.0) == "neutral"
    assert flow_of(1.5, 0.0) == "neutral"   # 平盤爆量歸量平，非出貨
    assert flow_of(0.7, 1.0) == "neutral"   # 0.7 為 quiet 的開區間端點 → 不算 quiet


def test_flow_null():
    # 缺量比或漲跌 → None（前端不顯示徽章）
    assert flow_of(None, 1.0) is None
    assert flow_of(2.0, None) is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && python -m pytest test_export_chain.py -v`
Expected: FAIL（`ModuleNotFoundError` 或 `ImportError: cannot import name 'flow_of'`）

- [ ] **Step 3: 寫 export_chain.py 含 flow_of 與 merge_quotes 簽名**

Create `engine/export_chain.py`：

```python
# -*- coding: utf-8 -*-
"""台股產業鏈漲跌與資金流向匯出。
讀 universe/tw_chain.json（純分類結構），抓每檔 1/5/20 日漲跌、量比，
判定資金流向，輸出 ../data/tw_chain.json（並同步 ../web/data/ 供本機預覽）。

資金流向 flow（與爆量榜 volrCls 同口徑，門檻 1.5/0.7；
  與爆量榜 export_json inflow 同口徑：volr>=1.5 且 r5>0）：
  volr>=1.5 且 r5>0  -> inflow  (🟢 資金流入)
  volr>=1.5 且 r5<0  -> outflow (🔴 爆量出貨)
  volr<0.7           -> quiet   (⚪ 縮量觀望)
  其餘               -> neutral (◯ 量平)
  volr 或 r5 為 None -> None

用法: python export_chain.py
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")

CHAIN_DEF = os.path.join(HERE, "universe", "tw_chain.json")
DATA_DIR = os.path.join(HERE, "..", "data")
WEB_DATA_DIR = os.path.join(HERE, "..", "web", "data")


def _safe(x):
    try:
        f = float(x)
        return None if (f != f) else f
    except Exception:
        return None


def _round(x, n=2):
    v = _safe(x)
    return round(v, n) if v is not None else None


def ret_n(closes, n):
    """近 n 日報酬% = (最後 / 第 n+1 個前) - 1。"""
    if len(closes) < n + 1:
        return None
    a, b = closes[-1], closes[-1 - n]
    if b in (0, None):
        return None
    return (a / b - 1.0) * 100.0


def flow_of(volr, r5):
    """資金流向判定。volr=量比, r5=5日漲幅%（與爆量榜 export_json.py 同口徑）。
    回傳 inflow/outflow/quiet/neutral 或 None。"""
    if volr is None or r5 is None:
        return None
    if volr >= 1.5 and r5 > 0:
        return "inflow"
    if volr >= 1.5 and r5 < 0:
        return "outflow"
    if volr < 0.7:
        return "quiet"
    return "neutral"


def merge_quotes(member, q):
    """把行情 dict q 併入 member（保留 sym/name/tags/note），回傳新 dict。
    q 為 None（抓取失敗）時所有行情欄位填 None。"""
    out = {"sym": member.get("sym"), "name": member.get("name", "")}
    if member.get("tags"):
        out["tags"] = member["tags"]
    if member.get("note"):
        out["note"] = member["note"]
    if q:
        out["last"] = _round(q.get("last"), 2)
        out["r1"] = _round(q.get("r1"), 2)
        out["r5"] = _round(q.get("r5"), 2)
        out["r20"] = _round(q.get("r20"), 2)
        out["volr"] = _round(q.get("volr"), 2)
        out["flow"] = flow_of(q.get("volr"), q.get("r5"))
    else:
        out["last"] = out["r1"] = out["r5"] = out["r20"] = out["volr"] = out["flow"] = None
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && python -m pytest test_export_chain.py -v`
Expected: 5 passed（`test_flow_*` 全綠；`merge_quotes` 已可 import）

- [ ] **Step 5: Commit**

```bash
git add engine/export_chain.py engine/test_export_chain.py
git commit -m "feat: export_chain flow_of 資金流向判定 + merge_quotes"
```

---

## Task 3: merge_quotes 行情合併測試 — TDD

補測 `merge_quotes`：確認保留分類欄位、缺資料填 null、flow 正確帶入。

**Files:**
- Test: `engine/test_export_chain.py`（追加）

- [ ] **Step 1: 追加失敗測試**

在 `engine/test_export_chain.py` 的 `if __name__` 之前插入：

```python
def test_merge_keeps_classification():
    m = {"sym": "3363.TWO", "name": "上詮", "tags": ["FAU"], "note": "台積電夥伴"}
    q = {"last": 840.0, "r1": -4.98, "r5": 3.07, "r20": 3.07, "volr": 2.1}
    out = merge_quotes(m, q)
    assert out["sym"] == "3363.TWO"
    assert out["name"] == "上詮"
    assert out["tags"] == ["FAU"]
    assert out["note"] == "台積電夥伴"
    assert out["r1"] == -4.98 and out["r5"] == 3.07 and out["r20"] == 3.07
    assert out["volr"] == 2.1
    assert out["flow"] == "inflow"   # volr>=1.5 且 r5>0


def test_merge_missing_quote_fills_null():
    m = {"sym": "9999.TW", "name": "測試", "tags": ["X"]}
    out = merge_quotes(m, None)
    assert out["sym"] == "9999.TW" and out["name"] == "測試" and out["tags"] == ["X"]
    assert out["r1"] is None and out["r5"] is None and out["r20"] is None
    assert out["volr"] is None and out["flow"] is None


def test_merge_no_tags_no_note():
    m = {"sym": "2330.TW", "name": "台積電"}
    out = merge_quotes(m, {"last": 1, "r1": 0.5, "r5": 1, "r20": 1, "volr": 1.0})
    assert "tags" not in out and "note" not in out   # 不無中生有
    assert out["flow"] == "neutral"
```

- [ ] **Step 2: 跑測試確認通過**

Run: `cd engine && python -m pytest test_export_chain.py -v`
Expected: 8 passed（merge_quotes 邏輯在 Task 2 已寫好，這裡補測應直接綠）

- [ ] **Step 3: Commit**

```bash
git add engine/test_export_chain.py
git commit -m "test: merge_quotes 保留分類欄位與缺資料填 null"
```

---

## Task 4: fetch() 抓取 + build() 主流程

加抓取（含 volr）與 build 主流程，產出 `data/tw_chain.json` 並同步到 `web/data/`。fetch 涉及網路，不寫單元測試，用實跑驗證。

**Files:**
- Modify: `engine/export_chain.py`（追加 fetch / build / __main__）

- [ ] **Step 1: 追加 fetch、build、__main__**

在 `engine/export_chain.py` 末尾（`merge_quotes` 之後）追加：

```python
def fetch(symbols):
    """一次抓多檔，回傳 {sym: {last,r1,r5,r20,volr} or None}。volr=今日$Vol/20日均$Vol。"""
    import yfinance as yf
    df = yf.download(symbols, period="2mo", interval="1d",
                     group_by="ticker", progress=False, auto_adjust=False)
    out = {}
    for s in symbols:
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            closes = list(sub["Close"])
            dollar = list(sub["Close"] * sub["Volume"])   # 每日成交金額
            if len(closes) < 2:
                out[s] = None
                continue
            last20 = dollar[-20:]
            dv = (sum(last20) / len(last20)) if last20 else None     # 20日均成交金額
            dv1 = dollar[-1] if dollar else None                     # 今日成交金額
            volr = (dv1 / dv) if (dv and dv > 0 and dv1 is not None) else None
            out[s] = {
                "last": _safe(closes[-1]),
                "r1": ret_n(closes, 1), "r5": ret_n(closes, 5), "r20": ret_n(closes, 20),
                "volr": _safe(volr),
            }
        except Exception:
            out[s] = None
    return out


def build():
    spec = json.load(io.open(CHAIN_DEF, encoding="utf-8"))
    # 收集所有 sym
    all_syms = []
    for c in spec["chains"]:
        for st in c["stages"]:
            for m in st.get("members", []):
                if m.get("sym"):
                    all_syms.append(m["sym"])
    all_syms = sorted(set(all_syms))
    if not all_syms:
        print("[chain] 定義檔無任何 sym，中止。")
        raise SystemExit(1)

    px = fetch(all_syms)
    if not any(px.values()):
        print("[chain] yfinance 全數抓取失敗，保留舊檔不覆寫。")
        raise SystemExit(1)

    failed = []
    chains_out = []
    for c in spec["chains"]:
        stages_out = []
        for st in c["stages"]:
            members_out = []
            for m in st.get("members", []):
                s = m.get("sym")
                q = px.get(s) if s else None
                if s and not q:
                    failed.append(s)
                members_out.append(merge_quotes(m, q))
            stages_out.append({
                "pos": st.get("pos", ""), "name": st.get("name", ""),
                "desc": st.get("desc", ""), "concepts": st.get("concepts", []),
                "members": members_out,
            })
        chains_out.append({
            "id": c.get("id", ""), "name": c.get("name", ""),
            "desc": c.get("desc", ""), "concepts": c.get("concepts", []),
            "stages": stages_out,
        })

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": spec.get("source", "yfinance (daily)"),
        "note": spec.get("note", ""),
        "chains": chains_out,
        "failed": sorted(set(failed)),
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for d in (DATA_DIR, WEB_DATA_DIR):
        os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(d, "tw_chain.json"), "w", encoding="utf-8") as f:
            f.write(blob)
    nstage = sum(len(c["stages"]) for c in chains_out)
    print(f"[chain] -> data/tw_chain.json + web/data/  ({len(chains_out)} 鏈, {nstage} 環節, {len(all_syms)} 檔, 失敗 {len(set(failed))})")
    if failed:
        print("[chain] 失敗:", ", ".join(sorted(set(failed))))


if __name__ == "__main__":
    build()
```

- [ ] **Step 2: 全測試仍綠**

Run: `cd engine && python -m pytest test_export_chain.py -v`
Expected: 8 passed（fetch/build 未破壞既有）

- [ ] **Step 3: 實跑（需網路，抓 yfinance）**

Run: `cd engine && python export_chain.py`
Expected: 輸出形如 `[chain] -> data/tw_chain.json + web/data/  (3 鏈, 17 環節, 43 檔, 失敗 N)`。失敗數可 >0（個別台股代號偶爾抓不到），只要不是全失敗即可。

- [ ] **Step 4: 驗證產出 JSON 結構與 flow 欄位**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && node -e "
const d=require('./data/tw_chain.json');
let withQuote=0, withFlow=0, total=0; const flows={};
d.chains.forEach(c=>c.stages.forEach(s=>s.members.forEach(m=>{
  total++; if(m.r1!==undefined) withQuote++;
  if(m.flow){withFlow++; flows[m.flow]=(flows[m.flow]||0)+1;}
  if(!m.sym||!m.name) throw new Error('分類欄位遺失: '+JSON.stringify(m));
})));
console.log('total='+total,'有行情欄='+withQuote,'有flow='+withFlow);
console.log('flow分布:',JSON.stringify(flows));
console.log('generated_at='+d.generated_at);
"
```
Expected: `total=43`，`有行情欄=43`，flow 分布印出（具體數字依當日行情，至少出現 1 種以上），`generated_at` 為當下時間戳。分類欄位無遺失（無 throw）。

- [ ] **Step 5: Commit**

```bash
git add engine/export_chain.py data/tw_chain.json web/data/tw_chain.json
git commit -m "feat: export_chain fetch(含volr) + build 產出行情與資金流向"
```

---

## Task 5: 前端 CSS — 漲跌列與資金徽章

**Files:**
- Modify: `web/index.html`（在 `.mstock-note` 樣式後追加）

- [ ] **Step 1: 加 CSS**

在 `web/index.html` 找到這行（產業鏈樣式區塊內）：
```css
  .mstock-note{font-size:11.5px;color:var(--ink2);line-height:1.55}
```
在其**後面**插入：
```css
  .mstock-quote{display:flex;gap:14px;font-family:var(--mono);font-size:11.5px;margin-bottom:6px}
  .mstock-quote .q{display:flex;flex-direction:column;line-height:1.3}
  .mstock-quote .q .ql{font-size:9px;color:var(--ink3);font-family:-apple-system,sans-serif}
  .mstock-flow{display:inline-flex;align-items:center;font-size:10.5px;font-weight:700;
    padding:2px 9px;border-radius:6px;margin-bottom:6px;letter-spacing:.2px}
  .mstock-flow.inflow{background:#e6f6ec;color:var(--green)}
  .mstock-flow.outflow{background:#fdeaed;color:var(--red)}
  .mstock-flow.quiet{background:var(--panel2);color:var(--ink3)}
  .mstock-flow.neutral{background:var(--panel2);color:var(--ink2)}
```

- [ ] **Step 2: 確認頁面仍可解析（無語法破壞）**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_cross_dom.mjs 2>&1 | tail -3`
Expected: `headless renderCross tests passed`（CSS 改動不影響 JS）

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat: 產業鏈個股卡片漲跌列與資金徽章 CSS"
```

---

## Task 6: 前端 memberCard — 渲染漲跌與徽章 — TDD

**Files:**
- Modify: `web/index.html`（`memberCard` 函式）
- Test: `web/test_chain_dom.mjs`

- [ ] **Step 1: 寫 headless 測試（會失敗）**

Create `web/test_chain_dom.mjs`：

```javascript
// headless 驗 memberCard：抽函式 + stub helper，驗各情境輸出。
import { readFileSync } from "node:fs";
import assert from "node:assert";
import vm from "node:vm";

const ROOT = "C:/Users/u9914/adr-trend-web/web";
const html = readFileSync(ROOT + "/index.html", "utf8");
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const appJs = scripts[scripts.length - 1];

// 抽出需要的純函式：esc / sgn / cls / memberCard
function extract(name) {
  const s = appJs.indexOf("function " + name);
  if (s < 0) throw new Error("缺函式 " + name);
  const o = appJs.indexOf("{", s);
  let d = 0;
  for (let i = o; i < appJs.length; i++) {
    if (appJs[i] === "{") d++;
    else if (appJs[i] === "}") { d--; if (d === 0) return appJs.slice(s, i + 1); }
  }
  throw new Error("不平衡 " + name);
}

const sandbox = {};
vm.createContext(sandbox);
// esc/sgn/cls 是 const 箭頭函式，直接抓原始定義行
const helpers = `
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const fmtNum = (n,d=0)=> n==null?"–":Number(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn = (n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls = n => n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
`;
vm.runInContext(helpers + "\n" + extract("memberCard") + "\nglobalThis.memberCard = memberCard;", sandbox);

// 情境 1：完整行情 + inflow
const h1 = sandbox.memberCard({sym:"3363.TWO", name:"上詮", tags:["FAU"], note:"夥伴",
  r1:2.0, r5:3.07, r20:3.07, volr:2.1, flow:"inflow"});
assert.ok(h1.includes("mstock-quote"), "缺漲跌列");
assert.ok(h1.includes("mstock-flow inflow"), "缺 inflow 徽章");
assert.ok(h1.includes("資金流入"), "缺流入文字");
assert.ok(h1.includes("data-stk=\"3363.TWO\""), "缺可點 data-stk");
assert.ok(h1.includes("夥伴"), "缺 note");

// 情境 2：缺行情（舊版 JSON 相容）→ 漲跌顯示 –、無徽章、不破版
const h2 = sandbox.memberCard({sym:"9999.TW", name:"測試", tags:["X"]});
assert.ok(h2.includes("mstock-quote"), "缺行情時仍應有漲跌列骨架");
assert.ok(h2.includes("–"), "缺行情應顯示 –");
assert.ok(!h2.includes("mstock-flow inflow") && !h2.includes("mstock-flow outflow"), "缺 flow 不應有徽章");

// 情境 3：outflow / quiet / neutral 文字正確
assert.ok(sandbox.memberCard({sym:"1.TW",name:"a",flow:"outflow",r1:-1,r5:0,r20:0,volr:2}).includes("爆量出貨"));
assert.ok(sandbox.memberCard({sym:"2.TW",name:"b",flow:"quiet",r1:1,r5:0,r20:0,volr:0.3}).includes("縮量觀望"));
assert.ok(sandbox.memberCard({sym:"3.TW",name:"c",flow:"neutral",r1:1,r5:0,r20:0,volr:1}).includes("量平"));

console.log("✅ memberCard 漲跌列與資金徽章測試全過");
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_dom.mjs`
Expected: FAIL（`AssertionError: 缺漲跌列` —— 現有 memberCard 尚未輸出 mstock-quote）

- [ ] **Step 3: 改 memberCard**

在 `web/index.html` 找到現有 `memberCard`：
```javascript
function memberCard(m){
  const code = m.sym.replace(/\.(TW|TWO)$/,"");
  const mkt = /\.TWO$/.test(m.sym) ? "櫃" : (/\.TW$/.test(m.sym) ? "市" : "");
  const tags = (m.tags||[]).map(t=>'<span class="mstock-tag">'+esc(t)+'</span>').join("");
  return '<div class="mstock">'+
    '<div class="mstock-top">'+
      '<span class="mstock-sym clickable" data-stk="'+esc(m.sym)+'">'+esc(code)+'</span>'+
      '<span class="mstock-name">'+esc(m.name)+'</span>'+
      (mkt?'<span class="mstock-mkt">'+mkt+'</span>':'')+
    '</div>'+
    (tags?'<div class="mstock-tags">'+tags+'</div>':'')+
    (m.note?'<div class="mstock-note">'+esc(m.note)+'</div>':'')+
  '</div>';
}
```
整段替換為：
```javascript
// 資金流向徽章文字（與 export_chain flow_of 同口徑）
const FLOW_LABEL = {inflow:"🟢 資金流入", outflow:"🔴 爆量出貨", quiet:"⚪ 縮量觀望", neutral:"◯ 量平"};
function quoteCol(lbl,v){
  return '<span class="q"><span class="ql">'+lbl+'</span>'+
    '<span class="'+cls(v)+'">'+(v==null?"–":sgn(v,1)+"%")+'</span></span>';
}
function memberCard(m){
  const code = m.sym.replace(/\.(TW|TWO)$/,"");
  const mkt = /\.TWO$/.test(m.sym) ? "櫃" : (/\.TW$/.test(m.sym) ? "市" : "");
  const tags = (m.tags||[]).map(t=>'<span class="mstock-tag">'+esc(t)+'</span>').join("");
  const quote = '<div class="mstock-quote">'+
    quoteCol("1日", m.r1!=null?m.r1:null)+
    quoteCol("5日", m.r5!=null?m.r5:null)+
    quoteCol("20日", m.r20!=null?m.r20:null)+
  '</div>';
  const flow = (m.flow && FLOW_LABEL[m.flow])
    ? '<div class="mstock-flow '+esc(m.flow)+'">'+FLOW_LABEL[m.flow]+'</div>' : '';
  return '<div class="mstock">'+
    '<div class="mstock-top">'+
      '<span class="mstock-sym clickable" data-stk="'+esc(m.sym)+'">'+esc(code)+'</span>'+
      '<span class="mstock-name">'+esc(m.name)+'</span>'+
      (mkt?'<span class="mstock-mkt">'+mkt+'</span>':'')+
    '</div>'+
    (tags?'<div class="mstock-tags">'+tags+'</div>':'')+
    quote+
    flow+
    (m.note?'<div class="mstock-note">'+esc(m.note)+'</div>':'')+
  '</div>';
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_dom.mjs`
Expected: `✅ memberCard 漲跌列與資金徽章測試全過`

- [ ] **Step 5: 既有測試仍綠**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_cross_dom.mjs 2>&1 | tail -2`
Expected: `headless renderCross tests passed`

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/test_chain_dom.mjs
git commit -m "feat: memberCard 渲染 1/5/20 日漲跌與資金流向徽章"
```

---

## Task 7: GitHub Actions 加一步

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml`

- [ ] **Step 1: 找到 themes 步驟並在其後加 chain 步驟**

在 `.github/workflows/export-and-deploy.yml` 找到：
```yaml
- name: Export Taiwan themes (sector/theme baskets)
  run: |
    cd engine
    python export_themes.py
```
在這段**之後**插入：
```yaml
- name: Export Taiwan industry chains (quotes + fund flow)
  run: |
    cd engine
    python export_chain.py
```

- [ ] **Step 2: 驗證 YAML 合法**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && python -c "import yaml; yaml.safe_load(open('.github/workflows/export-and-deploy.yml',encoding='utf-8')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: 確認部署步驟會帶上新檔（無需改）**

Run: `grep -n "cp data/\*.json" .github/workflows/export-and-deploy.yml`
Expected: 命中 `cp data/*.json public/data/` —— 既有萬用複製已涵蓋新產生的 `data/tw_chain.json`，不需額外改部署步驟。

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/export-and-deploy.yml
git commit -m "ci: 每日匯出產業鏈行情與資金流向 (export_chain.py)"
```

---

## Task 8: 端到端本機驗證

確認本機起站後產業鏈分頁完整呈現（資料已由 Task 4 產生）。

**Files:** 無（純驗證）

- [ ] **Step 1: 起本機站台**

Run（背景）: `cd /c/Users/u9914/adr-trend-web/web && python -m http.server 8765`

- [ ] **Step 2: 驗證 JSON 可由站台取得且含 flow**

Run:
```bash
curl -s http://localhost:8765/data/tw_chain.json | node -e "
let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{
const d=JSON.parse(s); let f=0; d.chains.forEach(c=>c.stages.forEach(st=>st.members.forEach(m=>{if(m.flow)f++})));
console.log('flow 徽章檔數='+f,'generated_at='+d.generated_at);
})"
```
Expected: `flow 徽章檔數` > 0、`generated_at` 為今日。

- [ ] **Step 3: 收掉站台**

Run: 結束背景 http.server 行程。

- [ ] **Step 4: 最終全測試**

Run: `cd /c/Users/u9914/adr-trend-web && python -m pytest engine/test_export_chain.py -q && node web/test_chain_dom.mjs && node web/test_cross_dom.mjs 2>&1 | tail -2`
Expected: pytest 8 passed、chain dom ✅、cross dom passed。

---

## 完成後
- 推分支 `feat/chain-quotes-flow` 並開 PR（合併後 Actions 下次排程或手動觸發即會更新線上資料）。
- 線上生效：合併到 main 後，下個台股收盤排程（或手動 workflow_dispatch / 網頁「🔄 更新資料」）會跑 `export_chain.py`，產業鏈分頁即顯示當日漲跌與資金流向。

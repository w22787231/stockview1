# 交叉訊號分頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一個主分頁「交叉訊號」，整理每個股票池全池的 MA10×MA50 金叉/死叉股票，分「🔥近3日剛觸發 / 全部金叉 / 全部死叉」三區塊。

**Architecture:** 後端 `export_json.py` 把引擎 `compute_trend` 早就算好、卻被丟棄的全池 `cross_state`/`cross_days` 補進每池 JSON 的新 `cross_signals` 區塊；前端 `index.html` 加第 4 個主分頁，沿用既有 `buildTable` 表格引擎、全域委派的排序與點擊進個股機制，render 三個區塊。零新計算、零額外抓取。

**Tech Stack:** Python 3.11（無第三方測試框架，用 `assert` 腳本）、純 HTML/CSS/JS（無建置）、Node 做前端邏輯單測。

參考 spec：`docs/superpowers/specs/2026-06-06-cross-signals-tab-design.md`

---

## File Structure

| 檔案 | 角色 | 改動 |
|---|---|---|
| `engine/export_json.py` | JSON 匯出 | 新增 `build_cross_signals(rows)`；`run_pool` payload 加 `"cross_signals"` |
| `web/index.html` | 前端 | 加主分頁按鈕；`switchView` 加 `cross` 分支；新增 `crossSignalTable`/`renderCross`；`load()` 依目前子分頁決定 render 哪個 |
| `engine/test_cross_signals.py` | 後端測試（新檔，臨時） | 驗證 `build_cross_signals` 行為 |
| `web/test_cross_render.mjs` | 前端測試（新檔，臨時） | 驗證篩選/排序純函式 |
| `engine/adr_screen.py` | 計算引擎 | **不改** |

說明：`build_cross_signals` 是純函式（吃 rows、回 dict），易測。前端把「篩 fresh」「排序」抽成純函式 `freshCrosses(cs)` / `sortCrossRows(rows)` 以便 Node 單測，render 函式呼叫它們。

---

## Task 1: 後端 `build_cross_signals(rows)` — 純函式 + 測試

**Files:**
- Modify: `engine/export_json.py`（在 `build_cross_filter` 之後、`run_pool` 之前新增函式；約 `export_json.py:312` 後）
- Test: `engine/test_cross_signals.py`（新檔）

- [ ] **Step 1: 寫失敗測試**

建立 `engine/test_cross_signals.py`：

```python
# -*- coding: utf-8 -*-
"""build_cross_signals 單元測試（無第三方框架，純 assert）。
執行：cd engine && python test_cross_signals.py"""
import export_json as ej


def _row(sym, state, days, score=1.0, sc5=50.0, r5=1.0):
    return {"sym": sym, "cross_state": state, "cross_days": days,
            "score": score, "sc5": sc5, "r5": r5,
            "e5": 0.3, "e20": 0.2, "a20": 5.0, "cur": "USD"}


def test_splits_golden_and_death():
    rows = [_row("A", "golden", 5), _row("B", "death", 2),
            _row("C", "golden", 1)]
    cs = ej.build_cross_signals(rows)
    assert cs["n_golden"] == 2, cs["n_golden"]
    assert cs["n_death"] == 1, cs["n_death"]
    assert all(r["cross_state"] == "golden" for r in cs["golden"])
    assert all(r["cross_state"] == "death" for r in cs["death"])


def test_skips_none_state():
    rows = [_row("A", "golden", 3), _row("X", None, None)]
    cs = ej.build_cross_signals(rows)
    syms = [r["sym"] for r in cs["golden"]] + [r["sym"] for r in cs["death"]]
    assert "X" not in syms, syms
    assert cs["n_golden"] + cs["n_death"] == 1


def test_sort_recent_first_none_last():
    # cross_days 小→前；None→墊底；同天數 score 大→前
    rows = [_row("OLD", "golden", 40, score=9),
            _row("NEW", "golden", 1, score=1),
            _row("NEVER", "golden", None, score=5),
            _row("MID_HI", "golden", 10, score=8),
            _row("MID_LO", "golden", 10, score=2)]
    cs = ej.build_cross_signals(rows)
    order = [r["sym"] for r in cs["golden"]]
    assert order == ["NEW", "MID_HI", "MID_LO", "OLD", "NEVER"], order


def test_fresh_days_constant():
    cs = ej.build_cross_signals([_row("A", "golden", 1)])
    assert cs["fresh_days"] == 3, cs["fresh_days"]


def test_row_has_expected_keys():
    cs = ej.build_cross_signals([_row("A", "golden", 1)])
    r = cs["golden"][0]
    for k in ("sym", "name", "cross_state", "cross_days",
              "sc5", "r5", "score", "e5", "e20", "a20", "cur"):
        assert k in r, k


def test_empty_rows():
    cs = ej.build_cross_signals([])
    assert cs["n_golden"] == 0 and cs["n_death"] == 0
    assert cs["golden"] == [] and cs["death"] == []


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"\n{len(fns)} passed")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && python test_cross_signals.py`
Expected: FAIL — `AttributeError: module 'export_json' has no attribute 'build_cross_signals'`

- [ ] **Step 3: 寫最小實作**

在 `engine/export_json.py` 的 `build_cross_filter` 函式結束之後（`return out` 那行之後、`def run_pool` 之前）插入：

```python
FRESH_CROSS_DAYS = 3  # 「剛觸發」窗口：cross_days <= 此值視為近期新交叉


def _cross_sort_key(r):
    """排序鍵：cross_days 小→前(None 墊底)、同天數 score 大→前。"""
    d = r.get("cross_days")
    days = d if d is not None else float("inf")
    return (days, -(r.get("score") or 0.0))


def build_cross_signals(rows):
    """全池 MA10×MA50 交叉清單。把 compute_trend 的全池 rows 依交叉狀態分組。
    golden/death 各自依「越新觸發越前、同天數 Score 大→前」排序；
    cross_state 非 golden/death(資料不足)者略過。「剛觸發」由前端依 fresh_days 篩。"""
    def pack(r):
        return {"sym": r["sym"], "name": _name(r["sym"]),
                "cross_state": r.get("cross_state"),
                "cross_days": r.get("cross_days"),
                "sc5": _round(r.get("sc5"), 0), "r5": _round(r.get("r5"), 1),
                "score": _round(r.get("score"), 0),
                "e5": _round(r.get("e5"), 2), "e20": _round(r.get("e20"), 2),
                "a20": _round(r.get("a20"), 1), "cur": r.get("cur")}

    golden, death = [], []
    for r in rows:
        st = r.get("cross_state")
        if st == "golden":
            golden.append(pack(r))
        elif st == "death":
            death.append(pack(r))
    golden.sort(key=_cross_sort_key)
    death.sort(key=_cross_sort_key)
    return {"fresh_days": FRESH_CROSS_DAYS,
            "golden": golden, "death": death,
            "n_golden": len(golden), "n_death": len(death)}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && python test_cross_signals.py`
Expected: PASS — `6 passed`

- [ ] **Step 5: Commit**

```bash
git add engine/export_json.py engine/test_cross_signals.py
git commit -m "feat(engine): build_cross_signals 全池金叉/死叉分組匯出"
```

---

## Task 2: 把 `cross_signals` 接進 payload + 真實資料驗證

**Files:**
- Modify: `engine/export_json.py`（`run_pool` 的 payload dict，約 `export_json.py:334`）

- [ ] **Step 1: 寫失敗測試**（沿用 Task 1 測試檔，新增整合測試）

在 `engine/test_cross_signals.py` 的 `test_empty_rows` 之後新增：

```python
def test_payload_contains_cross_signals():
    """run_pool 不實際抓網路：直接驗證 payload 組裝把 cross_signals 帶進去。
    用 monkeypatch 換掉會連網的相依，只測 dict 是否含鍵。"""
    import json as _json
    # 直接驗證原始碼層級：payload 模板要有 cross_signals 這個鍵
    src = open("export_json.py", encoding="utf-8").read()
    assert '"cross_signals": build_cross_signals(rows)' in src, \
        "run_pool payload 尚未加入 cross_signals"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && python test_cross_signals.py`
Expected: FAIL — `AssertionError: run_pool payload 尚未加入 cross_signals`

- [ ] **Step 3: 寫最小實作**

在 `engine/export_json.py` 的 `run_pool` 內 payload dict，於這一行：

```python
        "cross_filter": build_cross_filter(rows, main_rows, topn),
```

之後新增一行：

```python
        "cross_signals": build_cross_signals(rows),
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && python test_cross_signals.py`
Expected: PASS — `7 passed`

- [ ] **Step 5: 真實資料端對端驗證**（手動，需網路；若無網路可跳過並註記）

Run: `cd engine && PYTHONUTF8=1 python export_json.py ndx100 30`
Expected: 終端印出 `[export] ndx100 ...`，產生 `../data/ndx100.json`。

接著驗證輸出：

Run:
```bash
cd engine && python -c "
import json
d=json.load(open('../data/ndx100.json',encoding='utf-8'))
cs=d['cross_signals']
print('keys:', sorted(cs.keys()))
print('n_golden:', cs['n_golden'], 'n_death:', cs['n_death'], 'n_ok:', d['n_ok'])
assert cs['n_golden']+cs['n_death'] <= d['n_ok']
assert all(r['cross_state']=='golden' for r in cs['golden'])
assert all(r['cross_state']=='death' for r in cs['death'])
gd=[r['cross_days'] for r in cs['golden'] if r['cross_days'] is not None]
assert gd==sorted(gd), '金叉未依天數遞增'
fresh=[r for r in cs['golden']+cs['death'] if r['cross_days'] is not None and r['cross_days']<=cs['fresh_days']]
print('fresh(<=3天):', len(fresh), [r['sym'] for r in fresh])
print('OK')
"
```
Expected: 印出 `OK`，無 AssertionError。

- [ ] **Step 6: Commit**

```bash
git add engine/export_json.py engine/test_cross_signals.py
git commit -m "feat(engine): run_pool payload 加入 cross_signals 區塊"
```

---

## Task 3: 前端純函式 `freshCrosses` / `sortCrossRows` + Node 測試

**Files:**
- Modify: `web/index.html`（在 `crossSortVal` 之後，約 `index.html:345` 附近，加兩個純函式）
- Test: `web/test_cross_render.mjs`（新檔）

說明：把「篩 fresh」與「排序」做成不依賴 DOM 的純函式，方便 Node 單測；render 函式之後呼叫它們。`sortCrossRows` 與後端 `_cross_sort_key` 同口徑（天數小→前、None 墊底、同天數 score 大→前），讓前端即使吃到未排序資料也穩定。

- [ ] **Step 1: 寫失敗測試**

建立 `web/test_cross_render.mjs`：

```javascript
// 前端交叉訊號純函式測試。執行：cd web && node test_cross_render.mjs
// 從 index.html 抽出兩個純函式來測（以「數大括號」找出函式完整本體，避免被巢狀 } 截斷）。
import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");

function extract(name) {
  const start = html.indexOf("function " + name);
  if (start < 0) throw new Error("找不到函式 " + name);
  const open = html.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") { depth--; if (depth === 0) return html.slice(start, i + 1); }
  }
  throw new Error("函式 " + name + " 大括號不平衡");
}

// 把純函式載進來
const src = extract("sortCrossRows") + "\n" + extract("freshCrosses");
const mod = new Function(src + "\nreturn { sortCrossRows, freshCrosses };")();
const { sortCrossRows, freshCrosses } = mod;

function row(sym, state, days, score) {
  return { sym, cross_state: state, cross_days: days, score };
}

// sortCrossRows: 天數小→前、None→墊底、同天數 score 大→前
{
  const rows = [row("OLD","golden",40,9), row("NEW","golden",1,1),
                row("NEVER","golden",null,5), row("HI","golden",10,8),
                row("LO","golden",10,2)];
  const out = sortCrossRows(rows).map(r => r.sym);
  assert.deepStrictEqual(out, ["NEW","HI","LO","OLD","NEVER"], JSON.stringify(out));
  console.log("PASS sortCrossRows");
}

// freshCrosses: 合併 golden+death，取 cross_days<=fresh_days(非 null)，排序
{
  const cs = {
    fresh_days: 3,
    golden: [row("G1","golden",1,5), row("G2","golden",10,5)],
    death:  [row("D1","death",2,5),  row("D2","death",null,5)],
  };
  const fresh = freshCrosses(cs).map(r => r.sym);
  assert.deepStrictEqual(fresh, ["G1","D1"], JSON.stringify(fresh));
  console.log("PASS freshCrosses");
}

// freshCrosses: 空輸入安全
{
  assert.deepStrictEqual(freshCrosses({fresh_days:3,golden:[],death:[]}), []);
  assert.deepStrictEqual(freshCrosses(null), []);
  console.log("PASS freshCrosses empty");
}

console.log("\nAll front-end pure-fn tests passed");
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd web && node test_cross_render.mjs`
Expected: FAIL — `Error: 找不到函式 sortCrossRows`

- [ ] **Step 3: 寫最小實作**

在 `web/index.html` 的 `crossSortVal` 函式（結尾 `}` 在約 `index.html:345`）之後、`const esc =` 之前插入：

```javascript
// 交叉訊號排序：天數小→前、cross_days==null 墊底、同天數 score 大→前。
// 與後端 _cross_sort_key 同口徑，前端即使吃到未排序資料也穩定。
function sortCrossRows(rows){
  return (rows||[]).slice().sort((a,b)=>{
    const da = a.cross_days==null ? Infinity : a.cross_days;
    const db = b.cross_days==null ? Infinity : b.cross_days;
    if(da!==db) return da-db;
    return (b.score||0)-(a.score||0);
  });
}
// 從 cross_signals 取「近 fresh_days 天剛觸發」：合併 golden+death、排除無天數、依天數排序。
function freshCrosses(cs){
  if(!cs) return [];
  const fd = cs.fresh_days!=null ? cs.fresh_days : 3;
  const all = (cs.golden||[]).concat(cs.death||[]);
  return sortCrossRows(all.filter(r=>r.cross_days!=null && r.cross_days<=fd));
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd web && node test_cross_render.mjs`
Expected: PASS — `All front-end pure-fn tests passed`

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/test_cross_render.mjs
git commit -m "feat(web): 交叉訊號排序/篩選純函式 + Node 測試"
```

---

## Task 4: 前端 `crossSignalTable` + `renderCross` 渲染

**Files:**
- Modify: `web/index.html`（在 `crossTable` 函式之後，約 `index.html:481` 後，新增兩個函式）

說明：表格用既有 `buildTable(tableId, rows, cols, opts)` 引擎 → 自動取得點表頭排序、`empty` 空表文案、`td.sym.clickable` 點擊進個股（皆已全域委派，無需新事件）。每個表格需唯一 `tableId`。

- [ ] **Step 1: 寫實作（此為純 DOM 字串組裝，驗證放 Step 2 手動）**

在 `web/index.html` 的 `crossTable` 函式結尾 `}`（約 `index.html:481`）之後插入：

```javascript
// 交叉訊號表格：代號/名稱・狀態・幾天前・5日漲%・5日評分・Score。沿用 buildTable。
function crossSignalTable(tableId, rows, emptyMsg){
  const cols=[
    {h:"#", key:null, rownum:true},
    {h:"代號/名稱", key:"sym", type:"str", cell:r=>symCell(r.sym,r.name)},
    {h:"狀態", key:"cross", sortVal:crossSortVal,
      cell:r=>r.cross_state==="golden"?'<td><span class="pos">▲金叉</span></td>'
                                     :'<td><span class="neg">▼死叉</span></td>'},
    {h:"幾天前", key:"days",
      sortVal:r=>r.cross_days==null?9e9:r.cross_days,
      cell:r=>r.cross_days==null?'<td class="dim">—</td>'
             :r.cross_days===0?'<td><b>今日 <span style="color:var(--amber)">★</span></b></td>'
             :'<td class="dim">'+r.cross_days+' 天前</td>'},
    {h:"5日漲%", key:"r5", cell:r=>'<td class="'+cls(r.r5)+'">'+sgn(r.r5,1)+'%</td>'},
    {h:"5日評分", key:"sc5", cell:r=>'<td>'+fmtNum(r.sc5)+'</td>'},
    {h:"Score", key:"score", cell:r=>'<td>'+fmtNum(r.score)+'</td>'},
  ];
  return buildTable(tableId, rows, cols, {empty:emptyMsg});
}

// 交叉訊號分頁：🔥近 N 日剛觸發(展開) + 全部金叉(收起) + 全部死叉(收起)。
function renderCross(d){
  const cs = d.cross_signals;
  if(!cs){
    $("#content").innerHTML='<section><div class="sec-head"><h2>交叉訊號</h2></div>'+
      '<div class="note">此池資料尚未含交叉訊號（部署版本較舊）。請按右上「🔄 更新資料」重新產生。</div></section>';
    return;
  }
  const fresh = freshCrosses(cs);
  const fd = cs.fresh_days!=null?cs.fresh_days:3;
  const freshGold = fresh.filter(r=>r.cross_state==="golden").length;
  const freshDeath = fresh.length - freshGold;

  const freshBlock = fresh.length
    ? crossSignalTable("t-cross-fresh", sortCrossRows(fresh), "")
    : '<div class="note">近 '+fd+' 日無新交叉觸發。</div>';

  $("#content").innerHTML =
    '<section>'+
      '<div class="sec-head"><h2>交叉訊號</h2><span class="tag">MA10×MA50 · 本池 '+esc(d.pool_label)+'</span>'+
        '<span class="hint">本池 '+d.n_ok+' 檔，每日快照</span></div>'+
      '<div class="banner show" style="display:block;background:#fff8e6;border-color:#f0d488;color:#8a6400;margin:0 0 12px">'+
        '⚠️ <b>歷史/快照統計，非未來保證、非買賣建議。</b>金叉＝短均線(MA10)上穿長均線(MA50)、死叉＝下穿；「幾天前」＝距最近一次交叉的交易日數，0＝今日觸發。'+
      '</div>'+

      '<div class="tg-gname">🔥 最近剛觸發（≤'+fd+' 天）　<span class="dim" style="font-weight:400">金叉 '+freshGold+' ・ 死叉 '+freshDeath+'</span></div>'+
      freshBlock+

      '<details style="margin-top:14px"><summary class="tg-gname" style="cursor:pointer">▼ 全部金叉（'+cs.n_golden+' 檔）</summary>'+
        '<div style="margin-top:8px">'+crossSignalTable("t-cross-gold", sortCrossRows(cs.golden), "（本池目前無金叉）")+'</div>'+
      '</details>'+

      '<details style="margin-top:10px"><summary class="tg-gname" style="cursor:pointer">▼ 全部死叉（'+cs.n_death+' 檔）</summary>'+
        '<div style="margin-top:8px">'+crossSignalTable("t-cross-death", sortCrossRows(cs.death), "（本池目前無死叉）")+'</div>'+
      '</details>'+

      '<div class="legend">金叉＝MA10 上穿 MA50（偏多）、死叉＝下穿（偏空）。預設依「越新觸發越前、同天數 Score 大→前」排序，點欄頭可改排序。代號可點進個股看完整波段回測。</div>'+
    '</section>';
}
```

- [ ] **Step 2: 用真實資料煙霧測試 render（Node 模擬，不需瀏覽器）**

建立暫時測試 `web/test_cross_smoke.mjs`：

```javascript
// 煙霧測試：把 renderCross 依賴的純函式 + 真實 cross_signals 跑一遍，確認無例外、檔數正確。
import { readFileSync } from "node:fs";
import assert from "node:assert";
const html = readFileSync(new URL("./index.html", import.meta.url),"utf8");
function extract(name){const s=html.indexOf("function "+name);if(s<0)throw new Error("缺 "+name);const o=html.indexOf("{",s);let d=0;for(let i=o;i<html.length;i++){if(html[i]==="{")d++;else if(html[i]==="}"){d--;if(d===0)return html.slice(s,i+1);}}throw new Error("不平衡 "+name);}
const fns=new Function(extract("sortCrossRows")+extract("freshCrosses")+"\nreturn {sortCrossRows,freshCrosses};")();
const d=JSON.parse(readFileSync(new URL("./data/ndx100.json",import.meta.url),"utf8"));
const cs=d.cross_signals; assert(cs,"ndx100.json 缺 cross_signals");
const fresh=fns.freshCrosses(cs);
assert(fresh.every(r=>r.cross_days<=cs.fresh_days),"fresh 含超窗資料");
assert(fns.sortCrossRows(cs.golden).length===cs.n_golden);
console.log("smoke OK: n_golden",cs.n_golden,"n_death",cs.n_death,"fresh",fresh.length);
```

Run: `cd web && cp ../data/ndx100.json data/ 2>/dev/null; node test_cross_smoke.mjs`
Expected: `smoke OK: n_golden <X> n_death <Y> fresh <Z>`，無 AssertionError。

（若 Task 2 Step 5 未跑成功產生 ndx100.json，先補跑 export。）

- [ ] **Step 3: 刪除暫時煙霧測試（保留 Task 3 的單元測試）**

```bash
rm web/test_cross_smoke.mjs
```

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web): crossSignalTable + renderCross 三區塊渲染"
```

---

## Task 5: 主分頁按鈕 + `switchView` 接線 + `load()` 依子分頁 render

**Files:**
- Modify: `web/index.html`（nav `index.html:285`；`switchView` `index.html:1252`；`load()` 結尾 `render(d)` `index.html:1311`）

說明：交叉分頁與趨勢分頁共用同一份 `data/<pool>.json` 與同一套池分頁列。用模組級變數 `TREND_SUB`（值 `"trend"` 或 `"cross"`）記住目前在哪個子分頁；`load()` 取完資料後依此決定呼叫 `render(d)` 還是 `renderCross(d)`。

- [ ] **Step 1: 加主分頁按鈕**

在 `web/index.html:285`（`<button class="mtab active" data-view="trend">趨勢動能榜</button>` 那行）之後新增一行：

```html
    <button class="mtab" data-view="cross">交叉訊號</button>
```

- [ ] **Step 2: 加子分頁狀態變數 + `load()` 分派**

在 `web/index.html` 的 `let VIEW = "trend";`（約 `index.html:1251`）那行**之前**新增：

```javascript
let TREND_SUB = "trend";  // 趨勢分頁群內目前子頁："trend" 或 "cross"，共用同一份 pool JSON
```

把 `load()` 結尾的 `render(d);`（約 `index.html:1311`）改成：

```javascript
    if(TREND_SUB==="cross") renderCross(d); else render(d);
```

- [ ] **Step 3: `switchView` 加 cross 分支**

把 `web/index.html` 的 `switchView`（約 `index.html:1252-1261`）整個函式替換為：

```javascript
function switchView(v){
  VIEW = v;
  document.querySelectorAll(".mtab").forEach(t=>t.classList.toggle("active",t.dataset.view===v));
  const isPoolView = (v==="trend"||v==="cross");  // 交叉分頁與趨勢共用池分頁列
  $(".toolbar").style.display = isPoolView ? "flex" : "none";
  document.querySelector(".search").style.display = (v==="news") ? "none" : "flex";
  if(v==="macro") loadMacro();
  else if(v==="news") loadNewsFeed();
  else { TREND_SUB = v; load(); }   // v 為 "trend" 或 "cross"
}
```

- [ ] **Step 4: 手動驗證（瀏覽器）**

Run:
```bash
cd web && cp ../data/*.json data/ 2>/dev/null; python -m http.server 8899
```
然後開 `http://127.0.0.1:8899`，逐項確認：

1. 主分頁列出現「交叉訊號」按鈕（在趨勢動能榜與即時快訊之間）。
2. 點「交叉訊號」→ 顯示三區塊；池分頁列(tw150/ndx100/…)仍在。
3. 「🔥最近剛觸發」預設展開；「全部金叉/全部死叉」預設收起，點標題可展開。
4. 點某代號 → 跳進該個股詳情頁（與主表行為一致）。
5. 點表頭「幾天前」「Score」→ 排序切換、箭頭變化。
6. 切到只有 ndx100 有本地資料的池可看資料；切回「趨勢動能榜」→ 正常顯示主表（未被破壞）。
7. 切到「總體市場」「即時快訊」→ 正常（池分頁列隱藏）。

Expected: 全部符合。若某池無本地 JSON 會顯示載入失敗訊息（正常，部署後雲端會補齊）。

- [ ] **Step 5: Commit**

```bash
git add web/index.html
git commit -m "feat(web): 新增「交叉訊號」主分頁並接線 switchView/load"
```

---

## Task 6: 收尾 — 清理暫時測試檔、README 補一句

**Files:**
- Modify: `README.md`（五段輸出說明）
- 決定 `engine/test_cross_signals.py` / `web/test_cross_render.mjs` 去留

- [ ] **Step 1: 決定測試檔去留**

這兩個測試檔是長期有用的回歸測試，**保留**。確認 `.gitignore` 沒排除它們：

Run: `cd /c/Users/u9914/adr-trend-web && git status --porcelain engine/test_cross_signals.py web/test_cross_render.mjs`
Expected: 兩檔皆已被 git 追蹤（前次 commit 已加入），此處應無輸出或顯示已追蹤。

- [ ] **Step 2: README 補一句**

在 `README.md` 的「五段輸出」清單或架構說明附近，加一行說明新分頁（找到列出分頁/輸出的段落後補）：

```markdown
- **交叉訊號分頁** — 全池 MA10×MA50 金叉/死叉清單，分「近 3 日剛觸發 / 全部金叉 / 全部死叉」，可點進個股。
```

- [ ] **Step 3: 跑全部測試做最終回歸**

Run:
```bash
cd /c/Users/u9914/adr-trend-web/engine && python test_cross_signals.py && cd ../web && node test_cross_render.mjs
```
Expected: 後端 `7 passed`、前端 `All front-end pure-fn tests passed`。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README 補交叉訊號分頁說明"
```

---

## 驗收清單（對照 spec）

- [x] 全池每檔交叉狀態（非僅 Top N）— Task 1/2，`build_cross_signals(rows)` 吃全池 rows
- [x] 分「🔥剛觸發 + 全部狀態」兩類 — Task 4 `renderCross` 三區塊
- [x] 分池（tw150/ndx100/sp500/sp400/sp600）— Task 5 共用池分頁列
- [x] 剛觸發＝3 天內 — Task 1 `FRESH_CROSS_DAYS=3` + Task 3 `freshCrosses`
- [x] 欄位＝交叉天數+動能欄+可點進個股 — Task 4 `crossSignalTable` 欄位定義
- [x] 長表預設收起可展開 — Task 4 `<details>` 全部金叉/死叉收起、剛觸發展開
- [x] 邊界：空池/空剛觸發/None天數/舊JSON無欄位 — Task 1（略過 None state）、Task 4（empty 文案、`if(!cs)` fallback）
- [x] 不改 `adr_screen.py` — 全程未動
```

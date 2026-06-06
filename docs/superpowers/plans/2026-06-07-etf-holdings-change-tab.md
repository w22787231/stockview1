# ETF 持股異動分頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 stockview1.pages.dev 新增「ETF持股異動」主分頁，每日追蹤 5 檔台股主動式 ETF 的持股變化，以「日期 → ETF 分組」呈現最近 30 個交易日的新增/出清/加碼/減碼。

**Architecture:** 把本機 `etf_tool/fetch_holdings.py` 抓取邏輯移植成 `engine/fetch_etf.py`；新增 `engine/export_etf.py` 每日抓 5 檔持股、比對前一日 snapshot、算變化、追加進 `data/etf.json`(留 30 日)；前端加 `etf` 主分頁 + `loadEtf()` 渲染。GitHub Actions 每天自抓自累積，與本機脫鉤。

**Tech Stack:** Python 3.11(stdlib urllib，無第三方依賴)、純 HTML/CSS/JS、Node 做前端測試。

參考 spec：`docs/superpowers/specs/2026-06-07-etf-holdings-change-tab-design.md`

---

## File Structure

| 檔案 | 角色 | 改動 |
|---|---|---|
| `engine/fetch_etf.py` | ETF 持股抓取 | 新增(移植 etf_tool/fetch_holdings.py，邏輯不改) |
| `engine/export_etf.py` | 比對+算變化+寫 etf.json | 新增 |
| `engine/test_etf.py` | 後端離線測試 | 新增 |
| `web/index.html` | 前端 | +etf 分頁按鈕、switchView 分支、loadEtf/renderEtf |
| `web/test_etf_dom.mjs` | 前端 headless 測試 | 新增 |
| `.github/workflows/export-and-deploy.yml` | CI | +一步 export_etf.py |
| `etf_tool/*` | — | **不改** |

說明：抓取(fetch_etf)與資料產生(export_etf)分離 — fetch 是純抓網、export 是純資料邏輯(可注入假 fetcher 離線測)。

---

## Task 0：開乾淨的 feature 分支

**Files:** 無(git 操作)

- [ ] **Step 1: 從 main 開分支**

目前在 `feat/cpo-global-names`。先確認狀態、切到 main、開新分支：
```bash
cd /c/Users/u9914/adr-trend-web
git status --short
git stash list
git checkout main && git pull
git checkout -b feat/etf-holdings-tab
git branch --show-current
```
Expected: 顯示 `feat/etf-holdings-tab`。

> 註：spec commit 在 `feat/cpo-global-names` 上；新分支從 main 開即可，spec 不影響實作。若 main 上沒有該 spec 檔也無妨(實作不依賴它存在於 working tree)。

---

## Task 1：移植 `engine/fetch_etf.py`

**Files:**
- Create: `engine/fetch_etf.py`

- [ ] **Step 1: 移植抓取程式(原樣，邏輯不改)**

建立 `engine/fetch_etf.py`，內容與 `~/etf_tool/fetch_holdings.py` 完全相同。用此指令複製(避免手抄出錯)：
```bash
cd /c/Users/u9914/adr-trend-web
cp ~/etf_tool/fetch_holdings.py engine/fetch_etf.py
```

- [ ] **Step 2: 驗證可 import + 結構正確**

Run:
```bash
cd /c/Users/u9914/adr-trend-web/engine && python -c "
import fetch_etf as F
assert hasattr(F,'fetch_all'), '缺 fetch_all'
assert hasattr(F,'ETFS'), '缺 ETFS'
assert list(F.ETFS.keys())==['00981A','00988A','00403A','00982A','00990A'], F.ETFS.keys()
print('fetch_etf OK，ETFS 順序正確')
"
```
Expected: `fetch_etf OK，ETFS 順序正確`

- [ ] **Step 3: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add engine/fetch_etf.py
git commit -m "feat(engine): 移植 ETF 持股抓取 fetch_etf.py(自 etf_tool)"
```

---

## Task 2：`engine/export_etf.py` 核心邏輯 + 離線測試

**Files:**
- Create: `engine/export_etf.py`
- Create: `engine/test_etf.py`

- [ ] **Step 1: 寫失敗測試**

建立 `engine/test_etf.py`：
```python
# -*- coding: utf-8 -*-
"""export_etf 離線單元測試(注入假 fetcher，不連網)。
執行：cd engine && python test_etf.py"""
import os, json, tempfile
import export_etf as E


def _row(code, name, weight, qty):
    return {"etf": "", "etf_name": "", "code": code, "name": name,
            "weight": str(weight), "qty": str(qty)}


def _data(**etfs):
    """etfs: 00981A=[(code,name,w,q),...] → fetch_all 形態 dict。"""
    out = {}
    for etf, rows in etfs.items():
        out[etf] = [_row(*r) for r in rows]
    return out


def test_compute_changes_four_tags():
    prev = {"00981A": [_row("2330", "台積電", 10, 100), _row("2317", "鴻海", 5, 50)]}
    cur = {"00981A": [_row("2330", "台積電", 11, 120),   # 加碼(qty 100→120)
                      _row("3231", "緯創", 2, 30)]}        # 新增 / 2317 出清
    ch = E.compute_changes(cur, prev)
    by = {c["code"]: c for c in ch["00981A"]}
    assert by["2330"]["action"] == "加碼", by["2330"]
    assert by["2330"]["dqty"] == 20, by["2330"]
    assert by["3231"]["action"] == "新增", by["3231"]
    assert by["2317"]["action"] == "出清", by["2317"]
    # 持平不應出現在「真正變動」清單(compute_changes 含持平，filter 在 build 階段)
    cur2 = {"00981A": [_row("2330", "台積電", 10, 100)]}
    prev2 = {"00981A": [_row("2330", "台積電", 10, 100)]}
    ch2 = E.compute_changes(cur2, prev2)
    real = [c for c in ch2["00981A"] if c["action"] in ("新增", "出清", "加碼", "減碼")]
    assert real == [], real


def test_build_history_skips_no_change_day():
    """當日全無變動 → 不新增 history 條目。"""
    snap = {"00981A": [_row("2330", "台積電", 10, 100)]}
    j = {"snapshot": snap, "history": [], "etfs": {}, "order": []}
    # 今日與 snapshot 相同 → 無變動
    j2 = E.build_json(snap, j, today="2026-06-07")
    assert j2["history"] == [], j2["history"]


def test_build_history_appends_and_caps_30():
    """有變動 → 追加；history 超過 30 滾掉最舊。"""
    j = {"snapshot": {"00981A": []}, "history": [
        {"date": f"2026-04-{d:02d}", "changes": [{"etf": "00981A"}]} for d in range(1, 31)
    ], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 10, 100)]}  # vs 空 snapshot → 新增
    j2 = E.build_json(cur, j, today="2026-06-07")
    assert len(j2["history"]) == 30, len(j2["history"])          # 仍 30(滾掉最舊)
    assert j2["history"][0]["date"] == "2026-06-07", j2["history"][0]["date"]  # 新的在最前
    assert j2["history"][-1]["date"] != "2026-04-01", "最舊應被滾掉"


def test_build_history_same_day_dedup():
    """同日重跑 → 覆蓋當日那筆，不重複堆疊。"""
    j = {"snapshot": {"00981A": []}, "history": [], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 10, 100)]}
    j1 = E.build_json(cur, j, today="2026-06-07")
    j2 = E.build_json(cur, j1, today="2026-06-07")  # 同日再跑
    dates = [h["date"] for h in j2["history"]]
    assert dates.count("2026-06-07") == 1, dates


def test_failed_etf_keeps_old_snapshot():
    """單檔抓回空 → 保留該檔舊 snapshot，不誤判全出清。"""
    old = {"snapshot": {"00981A": [_row("2330", "台積電", 10, 100)],
                        "00982A": [_row("2454", "聯發科", 8, 80)]},
           "history": [], "etfs": {}, "order": []}
    cur = {"00981A": [_row("2330", "台積電", 11, 120)],  # 正常
           "00982A": []}                                  # 抓失敗(空)
    merged = E.merge_fetched(cur, old["snapshot"])
    assert merged["00982A"] == old["snapshot"]["00982A"], "失敗檔應保留舊快照"
    assert merged["00981A"] == cur["00981A"], "成功檔應更新"


def test_all_failed_returns_none():
    """全部抓回空 → 回 None(呼叫端不覆寫 etf.json)。"""
    assert E.merge_fetched({"00981A": [], "00982A": []}, {}) is None


def test_order_field_matches_etfs():
    j = E.build_json({"00981A": [_row("2330", "台積電", 10, 100)]},
                     None, today="2026-06-07")
    import fetch_etf as F
    assert j["order"] == list(F.ETFS.keys()), j["order"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("PASS", fn.__name__)
    print(f"\n{len(fns)} passed")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /c/Users/u9914/adr-trend-web/engine && python test_etf.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'export_etf'`

- [ ] **Step 3: 寫實作**

建立 `engine/export_etf.py`：
```python
# -*- coding: utf-8 -*-
"""主動式 ETF 每日持股變化 → data/etf.json(留最近 30 個有變動的交易日)。
網站版:GitHub Actions 每天自抓自累積，與本機 etf_tool 脫鉤。
用法:cd engine && python export_etf.py
"""
import os, json, datetime
import fetch_etf as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "etf.json")
HISTORY_DAYS = 30
ACTION_KEEP = ("新增", "出清", "加碼", "減碼")


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def _to_map(rows):
    return {r["code"]: r for r in rows}


def compute_changes(cur, prev):
    """每檔 ETF 算變化。回傳 {etf: [change,...]}，含持平(由呼叫端 filter)。
    change: {etf,etf_name,code,name,action,dqty,qty,dweight,weight}。"""
    out = {}
    for etf, rows in cur.items():
        cmap = _to_map(rows)
        pmap = _to_map(prev.get(etf, [])) if prev else {}
        name = F.ETFS.get(etf, {}).get("name", "")
        recs = []
        for code, r in cmap.items():
            cw, cq = _f(r["weight"]), _f(r["qty"])
            p = pmap.get(code)
            if not pmap:
                action = "基準"                      # 首次無前值
            elif p is None:
                action = "新增"
            else:
                dq = cq - _f(p["qty"])
                action = "加碼" if dq > 0 else ("減碼" if dq < 0 else "持平")
            pw = _f(p["weight"]) if p else 0.0
            pq = _f(p["qty"]) if p else 0.0
            recs.append({"etf": etf, "etf_name": name, "code": code, "name": r["name"],
                         "action": action, "dqty": int(cq - pq), "qty": int(cq),
                         "dweight": round(cw - pw, 2), "weight": cw})
        for code, p in pmap.items():            # 出清(昨有今無)
            if code not in cmap:
                recs.append({"etf": etf, "etf_name": name, "code": code, "name": p["name"],
                             "action": "出清", "dqty": -int(_f(p["qty"])), "qty": 0,
                             "dweight": -round(_f(p["weight"]), 2), "weight": 0.0})
        recs.sort(key=lambda x: x["weight"], reverse=True)   # 組內權重高→低
        out[etf] = recs
    return out


def merge_fetched(fetched, old_snapshot):
    """把今日抓到的持股與舊快照合併:某檔抓回空(失敗)→保留舊快照。
    全部失敗(都空)→回 None(呼叫端不覆寫)。"""
    if all(not rows for rows in fetched.values()):
        return None
    merged = {}
    for etf in F.ETFS:
        rows = fetched.get(etf, [])
        merged[etf] = rows if rows else old_snapshot.get(etf, [])
    return merged


def build_json(cur_snapshot, old_json, today):
    """用今日快照 + 舊 json 產新 json。純函式(不連網、不寫檔)，供測試。"""
    old_snap = (old_json or {}).get("snapshot") or {}
    history = list((old_json or {}).get("history") or [])
    changes = compute_changes(cur_snapshot, old_snap)
    # 取真正變動，扁平成一筆 day record
    day_changes = []
    for etf in F.ETFS:                          # 依固定順序
        for c in changes.get(etf, []):
            if c["action"] in ACTION_KEEP:
                day_changes.append(c)
    # 同日去重 + 有變動才加
    history = [h for h in history if h.get("date") != today]
    if day_changes:
        history.insert(0, {"date": today, "changes": day_changes})
    history = history[:HISTORY_DAYS]
    return {
        "generated_at": today + "T00:00:00Z",
        "etfs": {e: {"name": F.ETFS[e]["name"]} for e in F.ETFS},
        "order": list(F.ETFS.keys()),
        "snapshot": cur_snapshot,
        "history": history,
    }


def main():
    today = datetime.date.today().isoformat()
    print("=== 抓取 5 檔 ETF 持股 ===", flush=True)
    fetched = F.fetch_all()
    old = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    old_snap = (old or {}).get("snapshot") or {}
    merged = merge_fetched(fetched, old_snap)
    if merged is None:
        print("[!] 5 檔全抓失敗 → 不覆寫 etf.json，保留上次資料")
        return
    j = build_json(merged, old, today)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    n_changes = len(j["history"][0]["changes"]) if (j["history"] and j["history"][0]["date"] == today) else 0
    print(f"✓ etf.json 已更新:今日 {n_changes} 筆變動，history {len(j['history'])} 日")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /c/Users/u9914/adr-trend-web/engine && python test_etf.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add engine/export_etf.py engine/test_etf.py
git commit -m "feat(engine): export_etf 算變化+累積30日 etf.json + 離線測試"
```

---

## Task 3：真實資料端對端產生 etf.json(需網路)

**Files:**
- 產生(不 commit)：`data/etf.json`

- [ ] **Step 1: 實際抓一次**

Run:
```bash
cd /c/Users/u9914/adr-trend-web/engine && PYTHONUTF8=1 python export_etf.py
```
Expected: 印 `=== 抓取 5 檔 ETF 持股 ===`、5 檔各自筆數、`✓ etf.json 已更新`。
若某檔印 `ERR`(官網擋/改版)，只要不是 5 檔全失敗即可繼續。

- [ ] **Step 2: 驗證 etf.json 結構**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && python -c "
import json
d=json.load(open('data/etf.json',encoding='utf-8'))
assert set(['generated_at','etfs','order','snapshot','history'])<=set(d), list(d)
assert d['order']==['00981A','00988A','00403A','00982A','00990A'], d['order']
print('order OK')
for e in d['order']:
    print(f'  {e} {d[\"etfs\"][e][\"name\"]}: snapshot {len(d[\"snapshot\"].get(e,[]))} 檔')
print('history 日數:', len(d['history']))
if d['history']:
    h=d['history'][0]; print('最新日', h['date'], '變動', len(h['changes']), '筆')
"
```
Expected: order OK、各檔 snapshot 有檔數(成功抓的)、history 視當日有無變動(首次跑通常為基準日，history 可能空)。

- [ ] **Step 3: 確認 data/etf.json 是否該 commit**

Run: `cd /c/Users/u9914/adr-trend-web && git check-ignore data/etf.json && echo IGNORED || echo TRACKED`
- 若 `IGNORED`(data/ 被 gitignore，與其他 pool json 一樣由 CI 產生)→ 不需 commit，跳到 Task 4。
- 若 `TRACKED` → **不要** commit 這份本地抓的資料(它該由 CI 產)，用 `git checkout -- data/etf.json 2>/dev/null || true` 或留著不 add。
本 Task 不做 commit。

---

## Task 4：前端 `loadEtf` / `renderEtf` 渲染

**Files:**
- Modify: `web/index.html`(在 `loadChain` 函式之後新增；模組級變數區加 ETF 狀態)

### 復用的既有 helper(已存在，勿重定義)
- `fmtNum(n,d=0)` 千分位數字、`sgn(n,d=2)` 帶正負號、`cls(n)` pos/neg/dim、`esc(s)` HTML escape。
- `symCell(sym,name)` 產生可點 `td.sym.clickable[data-stk]`(點擊進個股，全域委派已接好)。
- `$(sel)` querySelector 捷徑；CSS class `sec-head`/`tag`/`hint`/`legend`/`tbl-wrap`/`tg-gname`/`banner show` 皆存在。

- [ ] **Step 1: 加模組級狀態變數**

在 `web/index.html` 找到 `let CHAIN_DATA` 宣告(grep `CHAIN_DATA` 找它的宣告行)，在其後新增一行：
```javascript
let ETF_DATA=null, ETF_FILTER={etf:"all", action:"all"};
```
若找不到 `let CHAIN_DATA`(命名不同)，則加在 `let VIEW =` 那行之前任一模組級區域。

- [ ] **Step 2: 新增 loadEtf + renderEtf + 子函式**

在 `loadChain` 函式的結尾 `}` 之後插入：
```javascript
// ── ETF 持股異動分頁 ───────────────────────────────
async function loadEtf(){
  for(const k in SORT_STATE) delete SORT_STATE[k];
  $("#meta").innerHTML='<div><b>ETF 持股異動</b> 5 檔主動式ETF</div><div>每日追蹤 · 來源各發行商官網</div>';
  $("#poolNote").innerHTML="";
  if(ETF_DATA){ renderEtf(); return; }
  $("#content").innerHTML='<div class="loading-screen">載入 ETF 持股異動 …</div>';
  try{
    const res=await fetch("data/etf.json?t="+Date.now(),{cache:"no-store"});
    if(!res.ok) throw new Error(res.status);
    ETF_DATA=await res.json();
    renderEtf();
  }catch(e){
    $("#content").innerHTML='<div class="loading-screen">ETF 資料尚未產生（'+esc(e.message)+'），請待下次更新。</div>';
  }
}

const ETF_ACTION_CLS={"新增":"etf-new","加碼":"pos","減碼":"neg","出清":"dim"};
const ETF_ACTION_ICON={"新增":"🆕新增","加碼":"➕加碼","減碼":"➖減碼","出清":"❌出清"};

function etfFilterBar(d){
  const etfBtns=['<button class="etf-fb'+(ETF_FILTER.etf==="all"?" on":"")+'" data-etf="all">全部</button>']
    .concat((d.order||[]).map(e=>'<button class="etf-fb'+(ETF_FILTER.etf===e?" on":"")+'" data-etf="'+e+'">'+e+' '+esc(d.etfs[e].name)+'</button>'));
  const acts=["all","新增","加碼","減碼","出清"];
  const actLabel={all:"全部動作","新增":"🆕新增","加碼":"➕加碼","減碼":"➖減碼","出清":"❌出清"};
  const actBtns=acts.map(a=>'<button class="etf-fb'+(ETF_FILTER.action===a?" on":"")+'" data-act="'+a+'">'+actLabel[a]+'</button>');
  return '<div class="etf-filters">'+etfBtns.join("")+'</div>'+
         '<div class="etf-filters">'+actBtns.join("")+'</div>';
}

function etfChangeTable(rows){
  const body=rows.map(r=>'<tr'+(r.code?' data-sym="'+esc(r.code)+'"':'')+'>'+
    symCell(r.code,r.name)+
    '<td class="'+(ETF_ACTION_CLS[r.action]||"dim")+'" style="font-weight:700">'+(ETF_ACTION_ICON[r.action]||esc(r.action))+'</td>'+
    '<td class="'+cls(r.dqty)+'">'+sgn(r.dqty,0)+'</td>'+
    '<td class="dim">'+fmtNum(r.qty)+'</td>'+
    '<td class="'+cls(r.dweight)+'">'+sgn(r.dweight,2)+'</td>'+
    '<td>'+fmtNum(r.weight,2)+'</td></tr>').join("");
  return '<div class="tbl-wrap"><table><thead><tr>'+
    '<th style="text-align:left">代碼/名稱</th><th>動作</th><th>張數變化</th><th>目前張數</th><th>權重變化</th><th>權重%</th>'+
    '</tr></thead><tbody>'+body+'</tbody></table></div>';
}

function renderEtf(){
  const d=ETF_DATA;
  if(!d || !d.history){ $("#content").innerHTML='<section><div class="sec-head"><h2>ETF 持股異動</h2></div><div class="note">ETF 資料尚未產生，請待下次更新。</div></section>'; return; }
  const latest=d.history.length?d.history[0].date:"—";
  // 依篩選過濾每日 changes
  const fE=ETF_FILTER.etf, fA=ETF_FILTER.action;
  const days=d.history.map(day=>{
    const cs=day.changes.filter(c=>(fE==="all"||c.etf===fE)&&(fA==="all"||c.action===fA));
    return {date:day.date, changes:cs};
  }).filter(day=>day.changes.length);

  let html='<section>'+
    '<div class="sec-head"><h2>ETF 持股異動</h2><span class="tag">5 檔主動式ETF · 每日追蹤</span>'+
      '<span class="hint">資料日 '+esc(latest)+'</span></div>'+
    '<div class="banner show" style="display:block;background:#fff8e6;border-color:#f0d488;color:#8a6400;margin:0 0 12px">'+
      '⚠️ 資料來源各 ETF 發行商官網（統一/群益/元大）。週末/假日持股不變動屬正常，故當日不列。'+
    '</div>'+ etfFilterBar(d);

  if(!days.length){
    html+='<div class="note">'+(d.history.length?'目前篩選條件下無變動紀錄。':'尚無變動紀錄（週末/假日或剛部署）。')+'</div>';
  }else{
    for(const day of days){
      html+='<div class="tg-gname" style="margin-top:16px;font-size:14px">📅 '+esc(day.date)+(day===days[0]?'（最新）':'')+'</div>';
      // 依 order 把當日 changes 分組成各 ETF
      for(const etf of d.order){
        const grp=day.changes.filter(c=>c.etf===etf);
        if(!grp.length) continue;
        const cnt=a=>grp.filter(c=>c.action===a).length;
        const tags=["新增","加碼","減碼","出清"].filter(a=>cnt(a)).map(a=>ETF_ACTION_ICON[a].slice(2)+cnt(a)).join(" ");
        html+='<div class="tg-gname" style="margin:10px 0 6px">▎'+esc(etf)+' '+esc(d.etfs[etf].name)+'　<span class="dim" style="font-weight:400">'+tags+'</span></div>'+
              etfChangeTable(grp);
      }
    }
  }
  html+='<div class="legend">🆕新增＝昨無今有；➕加碼/➖減碼＝張數增/減；❌出清＝昨有今無。每日依 ETF 分組，組內按權重高→低。代碼可點進個股。</div></section>';
  $("#content").innerHTML=html;

  // 篩選按鈕事件
  $("#content").querySelectorAll(".etf-fb").forEach(b=>b.onclick=()=>{
    if(b.dataset.etf!=null) ETF_FILTER.etf=b.dataset.etf;
    if(b.dataset.act!=null) ETF_FILTER.action=b.dataset.act;
    renderEtf();
  });
}
```

- [ ] **Step 3: 加 CSS(篩選鈕 + 新增色)**

在 `web/index.html` 的 `<style>` 區塊內(找 `.tg-gname` 規則附近)加：
```css
  .etf-filters{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
  .etf-fb{font-size:12.5px;padding:4px 10px;border:1px solid var(--line);border-radius:14px;
    background:var(--panel2);color:var(--ink2);cursor:pointer}
  .etf-fb:hover{border-color:var(--blue);color:var(--ink)}
  .etf-fb.on{background:var(--blue);color:#fff;border-color:var(--blue)}
  td.etf-new{color:#8a6400;background:#fff8e6;font-weight:700}
```

- [ ] **Step 4: 確認 JS 仍可解析(現有前端測試不破)**

Run: `cd /c/Users/u9914/adr-trend-web/web && node test_cross_render.mjs 2>&1 | tail -1`
Expected: 仍 `All front-end pure-fn tests passed`(代表 index.html script 區塊到既有測試函式為止仍可解析；新增程式碼未破壞語法)。

- [ ] **Step 5: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add web/index.html
git commit -m "feat(web): loadEtf/renderEtf — ETF 持股異動依日期→ETF分組渲染 + 篩選"
```

---

## Task 5：前端 headless DOM 測試

**Files:**
- Create: `web/test_etf_dom.mjs`

- [ ] **Step 1: 寫測試(抽 renderEtf 相關純函式，stub DOM)**

建立 `web/test_etf_dom.mjs`：
```javascript
// ETF 分頁 headless 測試:實際跑 renderEtf 對假 etf.json，斷言日期/ETF分組/篩選/空狀態。
// 執行:cd web && node test_etf_dom.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
function extract(name){
  const s = html.indexOf("function " + name);
  if (s < 0) throw new Error("缺 " + name);
  const o = html.indexOf("{", s);
  let d = 0;
  for (let i = o; i < html.length; i++){
    if (html[i] === "{") d++;
    else if (html[i] === "}"){ d--; if (d===0) return html.slice(s, i+1); }
  }
  throw new Error("不平衡 " + name);
}
// 也要抓兩個 const 表
function extractConst(name){
  const re = new RegExp("const " + name + "\\s*=\\s*\\{[^}]*\\}", "m");
  const m = html.match(re); if(!m) throw new Error("缺 const "+name); return m[0];
}

const stub = `
let CAPTURED="";
const SORT_STATE={};
const fmtNum=(n,d=0)=> n==null?"–":Number(n).toFixed(d);
const sgn=(n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls=n=> n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
const esc=s=>(s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function symCell(sym,name){return '<td class="sym clickable" data-stk="'+esc(sym)+'">'+esc(sym)+(name?'<span class="nm">'+esc(name)+'</span>':'')+'</td>';}
let ETF_DATA=null, ETF_FILTER={etf:"all",action:"all"};
const fakeEl={ set innerHTML(v){CAPTURED=v;}, get innerHTML(){return CAPTURED;}, querySelectorAll(){return [];} };
const $=()=>fakeEl;
`;

const src = stub + "\n" +
  extractConst("ETF_ACTION_CLS") + "\n" +
  extractConst("ETF_ACTION_ICON") + "\n" +
  extract("etfFilterBar") + "\n" +
  extract("etfChangeTable") + "\n" +
  extract("renderEtf") + "\n" +
  "return { renderEtf, setData:(d,f)=>{ETF_DATA=d; if(f)ETF_FILTER=f;}, get:()=>CAPTURED };";
const m = new Function(src)();

const DATA = {
  generated_at:"2026-06-07T00:00:00Z",
  order:["00981A","00982A"],
  etfs:{"00981A":{name:"統一台股增長"},"00982A":{name:"群益台灣精選強棒"}},
  snapshot:{},
  history:[
    {date:"2026-06-06", changes:[
      {etf:"00982A",etf_name:"群益台灣精選強棒",code:"3231",name:"緯創",action:"新增",dqty:5000,qty:5000,dweight:1.2,weight:2.1},
      {etf:"00981A",etf_name:"統一台股增長",code:"2330",name:"台積電",action:"加碼",dqty:120,qty:11960,dweight:0.3,weight:10.11},
    ]},
    {date:"2026-06-05", changes:[
      {etf:"00981A",etf_name:"統一台股增長",code:"2317",name:"鴻海",action:"減碼",dqty:-50,qty:450,dweight:-0.1,weight:3.2},
    ]},
  ],
};

// 1) 正常渲染:兩個日期、00981A 排在 00982A 前(依 order)
m.setData(DATA, {etf:"all",action:"all"});
m.renderEtf();
let out = m.get();
assert(out.includes("2026-06-06"), "缺最新日期");
assert(out.includes("2026-06-05"), "缺次日");
assert(out.includes("（最新）"), "缺最新標記");
// 同一天裡 00981A 分組標頭應出現在 00982A 之前
const i81 = out.indexOf("00981A 統一台股增長"), i82 = out.indexOf("00982A 群益台灣精選強棒");
assert(i81>0 && i82>0 && i81<i82, "ETF 分組順序應依 order(00981A 在前)");
assert(out.includes("台積電") && out.includes("緯創"), "缺個股");
console.log("PASS render + 分組順序");

// 2) ETF 篩選:只看 00982A → 不該出現 00981A 的台積電
m.setData(DATA, {etf:"00982A",action:"all"});
m.renderEtf(); out = m.get();
assert(out.includes("緯創") && !out.includes("台積電"), "ETF 篩選失效");
console.log("PASS ETF 篩選");

// 3) 動作篩選:只看 減碼 → 只剩鴻海那筆(2026-06-05)
m.setData(DATA, {etf:"all",action:"減碼"});
m.renderEtf(); out = m.get();
assert(out.includes("鴻海") && !out.includes("緯創"), "動作篩選失效");
console.log("PASS 動作篩選");

// 4) 空 history → fallback
m.setData({order:[],etfs:{},history:[]}, {etf:"all",action:"all"});
m.renderEtf(); out = m.get();
assert(out.includes("尚無變動紀錄"), "缺空狀態文案");
console.log("PASS 空狀態");

console.log("\nAll ETF DOM tests passed");
```

- [ ] **Step 2: 跑測試確認通過**

Run: `cd /c/Users/u9914/adr-trend-web/web && node test_etf_dom.mjs`
Expected: 結尾 `All ETF DOM tests passed`(4 個 PASS)。
若 `extractConst` 抓不到(因 ETF_ACTION_CLS 含 `}` 在值內被截斷)→ 該 const 是單行 `{...}` 無巢狀，正則 `\\{[^}]*\\}` 可正確匹配；若仍失敗，改用 `extract` 的數括號法包一層。

- [ ] **Step 3: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add web/test_etf_dom.mjs
git commit -m "test(web): ETF 分頁 headless 測試(日期/ETF分組/篩選/空狀態)"
```

---

## Task 6：加主分頁按鈕 + switchView 接線

**Files:**
- Modify: `web/index.html`(nav :343；switchView)

- [ ] **Step 1: 加 nav 按鈕**

找到這行(`web/index.html` 約 :343)：
```
    <button class="mtab" data-view="chain">產業鏈</button>
```
在其後、`data-view="news"` 之前插入一行：
```
    <button class="mtab" data-view="etf">ETF持股異動</button>
```

- [ ] **Step 2: switchView 加 etf 分支**

找到 switchView 裡這行：
```
  else if(v==="chain") loadChain();
```
在其後加：
```
  else if(v==="etf") loadEtf();
```

- [ ] **Step 3: 確認接線正確(grep)**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && grep -n 'data-view="etf"' web/index.html && grep -n 'v==="etf"' web/index.html && echo "wired OK"
```
Expected: 兩處各一行 + `wired OK`。

- [ ] **Step 4: 前端測試回歸**

Run: `cd /c/Users/u9914/adr-trend-web/web && node test_etf_dom.mjs 2>&1 | tail -1 && node test_cross_render.mjs 2>&1 | tail -1`
Expected: `All ETF DOM tests passed` + `All front-end pure-fn tests passed`。

- [ ] **Step 5: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add web/index.html
git commit -m "feat(web): 新增「ETF持股異動」主分頁並接線 switchView"
```

---

## Task 7：workflow 接線

**Files:**
- Modify: `.github/workflows/export-and-deploy.yml`

- [ ] **Step 1: 找到 chain 步驟，在其後加 ETF 步驟**

讀 `.github/workflows/export-and-deploy.yml`，找到跑 `export_chain.py` 的 step(grep `export_chain`)。在那個 step 之後、下一個 step 之前，插入：
```yaml
      - name: Export active ETF holdings change
        run: |
          cd engine
          python export_etf.py || true
```
縮排對齊既有 step(通常 step 的 `- name:` 在 6 空格縮排，確認與相鄰 step 一致)。

- [ ] **Step 2: 驗證 YAML 合法**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && python -c "import yaml; yaml.safe_load(open('.github/workflows/export-and-deploy.yml',encoding='utf-8')); print('YAML OK')"
```
Expected: `YAML OK`(若無 pyyaml: `pip install pyyaml -q` 後再跑)。

- [ ] **Step 3: 確認 export_etf 步驟存在**

Run: `cd /c/Users/u9914/adr-trend-web && grep -n "export_etf.py" .github/workflows/export-and-deploy.yml`
Expected: 一行命中。

- [ ] **Step 4: Commit**
```bash
cd /c/Users/u9914/adr-trend-web
git add .github/workflows/export-and-deploy.yml
git commit -m "ci: workflow 加 export_etf.py 步驟(|| true 容錯)"
```

---

## Task 8：收尾 — 全測試回歸

**Files:** 無(驗證)

- [ ] **Step 1: 跑全部相關測試**

Run:
```bash
cd /c/Users/u9914/adr-trend-web/engine && python test_etf.py 2>&1 | tail -1
cd /c/Users/u9914/adr-trend-web/web && node test_etf_dom.mjs 2>&1 | tail -1 && node test_cross_render.mjs 2>&1 | tail -1
```
Expected: `7 passed` / `All ETF DOM tests passed` / `All front-end pure-fn tests passed`。

- [ ] **Step 2: Python 語法總檢**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && python -c "import ast; [ast.parse(open('engine/'+f,encoding='utf-8').read()) for f in ('fetch_etf.py','export_etf.py','test_etf.py')]; print('py OK')"
```
Expected: `py OK`

- [ ] **Step 3: 確認分支 commit 完整**

Run: `cd /c/Users/u9914/adr-trend-web && git log --oneline main..HEAD`
Expected: 看到 Task 1/2/4/5/6/7 的 commit(Task 3 不 commit)。

---

## 驗收清單（對照 spec）

- [x] 網站自抓(移植 fetch_holdings) — Task 1 fetch_etf.py
- [x] 算變化(新增/出清/加碼/減碼) — Task 2 compute_changes
- [x] 留最近 30 日 + 同日去重 + 週末無變化不記 — Task 2 build_json
- [x] 容錯:單檔失敗保留舊快照/全失敗不覆寫 — Task 2 merge_fetched
- [x] 排序:日期→ETF(order)→組內權重 — Task 2(day_changes 依 order) + Task 4(renderEtf 分組)
- [x] 前端 etf 分頁 + 日期/ETF 分組 + 動作上色 + 代碼可點 — Task 4
- [x] ETF/動作篩選 — Task 4 etfFilterBar
- [x] 空狀態 / 無 etf.json fallback — Task 4 renderEtf
- [x] workflow 自動跑 + || true 容錯 — Task 7
- [x] 不改 etf_tool — 全程未動

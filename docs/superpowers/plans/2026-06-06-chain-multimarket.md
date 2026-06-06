# 產業鏈跨市場擴充 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓產業鏈分頁支援多市場個股（台/美/中/港/日/歐，依代號後綴自動標記），CPO 鏈補入全球龍頭，並由 Obsidian 報告新增「AR/XR 智慧眼鏡」整條鏈。

**Architecture:** 前端新增純函式 `marketOf(sym)` 依後綴判市場、`memberCard` 改用之並泛化去後綴；資料層只擴 `engine/universe/tw_chain.json`（CPO 補龍頭 + 新增 ar-xr 鏈）。`export_chain.py` 不改（對任何 yfinance 代號通用）。代號一律存 yfinance 格式（A股 `.SS`/`.SZ`）。

**Tech Stack:** 原生 JS/CSS、Python（既有 export_chain.py）、Node headless 測試、yfinance。

---

## 路徑與背景
- 工作目錄：`c:/Users/u9914/adr-trend-web`，分支 `feat/cpo-global-names`（已從 main 開，含產業鏈+漲跌+中文搜尋）。
- 分類定義檔：`engine/universe/tw_chain.json`（版控）。`export_chain.py` 讀它→抓 yfinance→輸出 `data/` + `web/data/`（皆 gitignore）。
- 前端 `web/index.html`：`memberCard`（~1042 行）、`.mstock-mkt` CSS（~293 行）、`FLOW_LABEL`/`quoteCol` 已存在。
- 撞號：`2382.HK`=舜宇 ≠ `2382.TW`=廣達，各自獨立成員。
- A股：報告寫 `.SH` 一律存 `.SS`（yfinance 用 .SS）。

## 檔案結構
- **Modify** `web/index.html` — 新增 `marketOf`、`memberCard` 改用之、code 去後綴泛化、`.mstock-mkt` 市場配色 CSS。Task 1–2。
- **Create** `web/test_chain_intl.mjs` — marketOf 與跨市場 memberCard headless 測試。Task 1。
- **Modify** `engine/universe/tw_chain.json` — CPO 鏈補國際龍頭。Task 3。
- **Modify** `engine/universe/tw_chain.json` — 新增 ar-xr 鏈。Task 4。
- 驗證：跑 `export_chain.py`，產出 `data/tw_chain.json` + `web/data/`。Task 5。

---

## Task 1: marketOf 函式 + 市場配色 CSS — TDD

**Files:**
- Modify: `web/index.html`（新增 `marketOf`、`.mstock-mkt` 配色）
- Test: `web/test_chain_intl.mjs`

- [ ] **Step 1: 寫失敗測試** — Create `web/test_chain_intl.mjs`：

```javascript
// headless 驗 marketOf：各市場後綴 → 正確標記與 cls。抽函式跑斷言。
import { readFileSync } from "node:fs";
import assert from "node:assert";
import vm from "node:vm";

const ROOT = "C:/Users/u9914/adr-trend-web/web";
const html = readFileSync(ROOT + "/index.html", "utf8");
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const appJs = scripts[scripts.length - 1];

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
vm.runInContext(extract("marketOf") + "\nglobalThis.marketOf = marketOf;", sandbox);

const cases = [
  ["2330.TW", "市", "tw"],
  ["3363.TWO", "櫃", "tw"],
  ["NVDA", "美", "us"],
  ["688234.SS", "滬", "cn"],
  ["002241.SZ", "深", "cn"],
  ["2018.HK", "港", "hk"],
  ["5301.T", "日", "jp"],
  ["SGL.DE", "德", "eu"],
  ["SIVE.ST", "瑞", "eu"],
  ["EL.PA", "法", "eu"],
];
for (const [sym, mkt, cls] of cases) {
  const r = sandbox.marketOf(sym);
  assert.equal(r.mkt, mkt, `${sym} mkt 應為 ${mkt}，實得 ${r.mkt}`);
  assert.equal(r.cls, cls, `${sym} cls 應為 ${cls}，實得 ${r.cls}`);
}
// 無法判斷 → 空標記
const unknown = sandbox.marketOf("FOO.XYZ");
assert.equal(unknown.mkt, "", "未知後綴 mkt 應為空");

console.log("✅ marketOf 各市場後綴測試全過");
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_intl.mjs`
Expected: FAIL（`缺函式 marketOf`）

- [ ] **Step 3: 新增 marketOf 函式**

在 `web/index.html` 的 `memberCard` 函式**之前**（即 `FLOW_LABEL`/`quoteCol` 附近，找到 `function memberCard(m){` 那行，在它上面）插入：

```javascript
// 依代號後綴判市場（吃完整 sym，後綴比對優先）。回傳 {mkt:標記字, cls:CSS類}。
const MARKET_MAP = {
  ".TW":["市","tw"], ".TWO":["櫃","tw"],
  ".SS":["滬","cn"], ".SZ":["深","cn"],
  ".HK":["港","hk"], ".T":["日","jp"], ".DE":["德","eu"],
  ".ST":["瑞","eu"], ".MC":["西","eu"], ".PA":["法","eu"], ".AS":["荷","eu"], ".L":["英","eu"],
};
function marketOf(sym){
  sym = sym||"";
  const dot = sym.lastIndexOf(".");
  if(dot>=0){
    const suf = sym.slice(dot);
    if(MARKET_MAP[suf]) return {mkt:MARKET_MAP[suf][0], cls:MARKET_MAP[suf][1]};
    return {mkt:"", cls:""};   // 有後綴但不認得
  }
  // 無後綴 → 美股
  return {mkt:"美", cls:"us"};
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_intl.mjs`
Expected: `✅ marketOf 各市場後綴測試全過`

- [ ] **Step 5: 加市場配色 CSS**

在 `web/index.html` 找到（~293 行）：
```css
  .mstock-mkt{font-family:var(--mono);font-size:9.5px;color:var(--ink3);border:1px solid var(--line);
```
這條規則**結尾**（該行所屬的 `}` 之後）插入市場別配色：
```css
  .mstock-mkt.us{color:var(--blue);border-color:#cfe0fb;background:#eef4ff}
  .mstock-mkt.eu{color:#c2630a;border-color:#f0d0a8;background:#fff4e6}
  .mstock-mkt.cn{color:var(--red);border-color:#f3c0c8;background:#fdeef0}
  .mstock-mkt.hk{color:#0e8a8a;border-color:#a8e0e0;background:#e6f7f7}
  .mstock-mkt.jp{color:#7c3aed;border-color:#d9c8f7;background:#f3eefe}
```

- [ ] **Step 6: 既有測試不回歸**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_dom.mjs && node web/test_cross_dom.mjs 2>&1 | tail -1`
Expected: chain dom ✅、cross dom passed

- [ ] **Step 7: Commit**

```bash
git add web/index.html web/test_chain_intl.mjs
git commit -m "feat: marketOf 依代號後綴判市場(台美中港日歐) + 市場配色 CSS"
```

---

## Task 2: memberCard 改用 marketOf + code 去後綴泛化 — TDD

**Files:**
- Modify: `web/index.html`（`memberCard`）
- Test: `web/test_chain_intl.mjs`（追加）

- [ ] **Step 1: 追加失敗測試**

在 `web/test_chain_intl.mjs` 的 `console.log("✅ marketOf...` **之前**插入：

```javascript
// memberCard 跨市場：抽 memberCard + 相依 helper
const helpers = `
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const sgn = (n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls = n => n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
const FLOW_LABEL = {inflow:"x",outflow:"x",quiet:"x",neutral:"x"};
`;
vm.runInContext(helpers + extract("quoteCol") + extract("memberCard") + "\nglobalThis.memberCard = memberCard;", sandbox);

// 滬股：顯示「滬」、code 去 .SS、cls=cn
const hcn = sandbox.memberCard({sym:"688234.SS", name:"天岳先進", r1:1, r5:2, r20:3, flow:"inflow"});
assert.ok(hcn.includes("mstock-mkt cn"), "滬股應有 cn class");
assert.ok(hcn.includes(">滬<"), "應顯示 滬");
assert.ok(hcn.includes(">688234<"), "code 應去 .SS 顯示 688234");
assert.ok(hcn.includes('data-stk="688234.SS"'), "data-stk 應保留完整 sym");

// 美股：顯示「美」、code 不變
const hus = sandbox.memberCard({sym:"NVDA", name:"輝達", r1:1, r5:1, r20:1});
assert.ok(hus.includes("mstock-mkt us") && hus.includes(">美<"), "美股應顯示 美/us");

// 歐股：SIVE.ST → 瑞、code=SIVE
const heu = sandbox.memberCard({sym:"SIVE.ST", name:"Sivers"});
assert.ok(heu.includes(">瑞<") && heu.includes(">SIVE<"), "SIVE.ST 應顯示 瑞 + code SIVE");

// 台股不回歸
const htw = sandbox.memberCard({sym:"3363.TWO", name:"上詮"});
assert.ok(htw.includes(">櫃<") && htw.includes(">3363<"), "台股櫃仍正確");
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_intl.mjs`
Expected: FAIL（`滬股應有 cn class` —— 現 memberCard 用舊的 .TW/.TWO 二分，滬股 mkt 為空）

- [ ] **Step 3: 改 memberCard**

在 `web/index.html` 找到現有 memberCard 開頭三行：
```javascript
function memberCard(m){
  const sym = m.sym||"";
  const code = sym.replace(/\.(TW|TWO)$/,"");
  const mkt = /\.TWO$/.test(sym) ? "櫃" : (/\.TW$/.test(sym) ? "市" : "");
```
改為：
```javascript
function memberCard(m){
  const sym = m.sym||"";
  const code = sym.replace(/\.(TW|TWO|SS|SZ|HK|T|DE|ST|MC|PA|AS|L)$/,"");
  const mk = marketOf(sym);
```
並把下方 mkt 標記那行（原 `(mkt?'<span class="mstock-mkt">'+mkt+'</span>':'')`）改為：
```javascript
      (mk.mkt?'<span class="mstock-mkt '+mk.cls+'">'+mk.mkt+'</span>':'')+
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_intl.mjs`
Expected: `✅ marketOf 各市場後綴測試全過`（含新 memberCard 斷言）

- [ ] **Step 5: 既有測試不回歸**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_dom.mjs && node web/test_cross_dom.mjs 2>&1 | tail -1`
Expected: chain dom ✅、cross dom passed

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/test_chain_intl.mjs
git commit -m "feat: memberCard 改用 marketOf 顯示多市場標記 + code 去後綴泛化"
```

---

## Task 3: CPO 鏈補入全球龍頭（資料）

**Files:**
- Modify: `engine/universe/tw_chain.json`（CPO 鏈 id=cpo）

說明：在 cpo 鏈的 `stages` 內，新增兩個環節、並補入既有環節。用 Edit 精準插入，不要重寫整檔。先 Read `engine/universe/tw_chain.json` 找到 cpo 鏈各 stage。

- [ ] **Step 1: 在「光源 / 雷射 (ELS)」環節的 members 末尾補 SIVE.ST**

該環節現有 members 只有 `4908.TWO`（眾達-KY）。在其 members 陣列末尾加：
```json
,{"sym":"SIVE.ST","name":"Sivers","tags":["矽光子","雷射","ELS"],"note":"瑞典矽光子/雷射元件，矽光子光源國際標的。"}
```

- [ ] **Step 2: 新增「運算晶片 / CPO 推手」環節（插在 cpo 鏈 stages 最前，上游）**

在 cpo 鏈 `"stages":[` 之後、第一個 stage 之前插入：
```json
{"pos":"上游","name":"運算晶片 / CPO 推手","desc":"GPU/交換器 ASIC 帶動 CPO 商轉的終端需求龍頭（國際）。","concepts":["GPU","ASIC","CPO推手"],"members":[
{"sym":"NVDA","name":"NVIDIA 輝達","tags":["GPU","CPO推手"],"note":"AI GPU 龍頭，將 CPO 應用於機架/板對板光互連，導入台積電 COUPE。"},
{"sym":"AVGO","name":"Broadcom 博通","tags":["交換器ASIC","CPO推手"],"note":"引領 CPO 交換機商轉，利用台積電製程推動 2026 大規模出貨。"},
{"sym":"MRVL","name":"Marvell","tags":["光DSP","CPO"],"note":"資料中心互連與光通訊晶片，CPO/光DSP 卡位。"}
]},
```

- [ ] **Step 3: 新增「光收發 / CPO 模組」環節（插在 FAU 對準環節之後，中游）**

在 cpo 鏈中找到「FAU 光纖對準 / 光學耦合」環節的 `}` 之後插入：
```json
{"pos":"中游","name":"光收發 / CPO 模組","desc":"高速光收發模組與 CPO 光引擎國際龍頭（美）。","concepts":["光模組","光收發","CPO模組"],"members":[
{"sym":"COHR","name":"Coherent","tags":["光模組","光學材料"],"note":"光收發與光學材料國際龍頭（原 II-VI），CPO/資料中心光連結。"},
{"sym":"LITE","name":"Lumentum","tags":["光模組","雷射"],"note":"雷射與光元件大廠，資料中心光收發。"},
{"sym":"CIEN","name":"Ciena","tags":["光網路","相干光"],"note":"光網路系統與相干光傳輸。"}
]},
```

- [ ] **Step 4: 在「電光熱測試 / 探針介面」環節 members 末尾補 KEYS**

```json
,{"sym":"KEYS","name":"Keysight","tags":["測試量測","高頻"],"note":"高頻電光量測儀器，CPO/矽光子測試平台國際龍頭。"}
```

- [ ] **Step 5: 在「光通訊高彈性 / 收發模組」環節 members 末尾補 FN**

```json
,{"sym":"FN","name":"Fabrinet","tags":["光學代工","OEM"],"note":"光通訊/光學元件代工龍頭，CPO 模組製造受惠。"}
```

- [ ] **Step 6: 驗證 JSON 合法**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && node -e "const d=require('./engine/universe/tw_chain.json'); const cpo=d.chains.find(c=>c.id==='cpo'); let m=0; cpo.stages.forEach(s=>m+=s.members.length); console.log('cpo 環節='+cpo.stages.length,'成員='+m); const all=[]; cpo.stages.forEach(s=>s.members.forEach(x=>all.push(x.sym))); console.log('含 NVDA/COHR/SIVE.ST/KEYS/FN:', ['NVDA','COHR','SIVE.ST','KEYS','FN'].every(x=>all.includes(x)))"
```
Expected: `cpo 環節=8 成員=...`、`含 ...: true`（JSON 合法且龍頭都在）

- [ ] **Step 7: Commit**

```bash
git add engine/universe/tw_chain.json
git commit -m "feat: CPO 鏈補入全球龍頭(NVDA/AVGO/MRVL/COHR/LITE/CIEN/SIVE.ST/KEYS/FN)"
```

---

## Task 4: 新增「AR/XR 智慧眼鏡」鏈（資料）

**Files:**
- Modify: `engine/universe/tw_chain.json`（在 chains 陣列末尾新增 ar-xr 鏈）

說明：在 `chains` 陣列最後一個鏈的 `}` 之後、`]` 之前，插入下面完整的 ar-xr 鏈物件（前面加逗號）。代號全用 yfinance 格式（A股 .SS/.SZ）。

- [ ] **Step 1: 插入 ar-xr 鏈**

在 `engine/universe/tw_chain.json` 的 `chains` 陣列末尾插入（注意前置逗號）：

```json
,{"id":"ar-xr","name":"AR/XR 智慧眼鏡","desc":"消費級 AI/AR 眼鏡進入多巨頭出貨期（Meta 帶頭、Apple/Samsung/Google 跟進）。由終端逆向穿透至上游材料，找未被定價的瓶頸層。資料來源：Obsidian chokepoint-scan 拆鏈報告。","concepts":["AR眼鏡","XR","光波導","光學級SiC","microLED","Meta","Apple"],"stages":[
{"pos":"上游","name":"L1.0 石墨耗材 / 長晶熱場","desc":"長晶爐 2000°C+ 等靜壓石墨坩堝/熱場，SiC 長晶與磊晶必用耗材，已實證短缺。報告評為最未定價的『賣鏟子』層。","concepts":["等靜壓石墨","長晶耗材"],"members":[
{"sym":"5301.T","name":"東海碳素 Tokai Carbon","tags":["等靜壓石墨","SiC塗層"],"note":"L1.0 石墨耗材 · CP4/4 · 🟢未定價。AI功率+AR光學雙需求，估值僅錨半導體耗材。"},
{"sym":"5310.T","name":"東洋炭素 Toyo Tanso","tags":["等靜壓石墨","熱場"],"note":"L1.0 長晶/磊晶熱場耗材 · 🟢未定價。全球高階等靜壓石墨少數供應商。"},
{"sym":"SGL.DE","name":"SGL Carbon","tags":["等靜壓石墨","susceptor"],"note":"L1.0 SIGRAFINE 等靜壓石墨、Si/SiC 磊晶 susceptor（德，去中化溢價）。"},
{"sym":"300316.SZ","name":"晶盛機電","tags":["長晶爐","設備"],"note":"L1.5 PVT 長晶爐+加工設備（跨 L1/L3 層）。"}
]},
{"pos":"上游","name":"L2 光學級 SiC 基板","desc":"SiC 折射率 2.7、單層全彩、最薄最輕；良率<20%、單片損失 US$500，真實物理瓶頸。⚠報告修正：Lumus CES2026 玻璃波導突破 70°FoV，SiC『唯一路徑』溢價下修。","concepts":["光學級SiC","波導基板"],"members":[
{"sym":"688234.SS","name":"天岳先進(A) SICC","tags":["光學級SiC","SiC基板"],"note":"L2 光學級 SiC · CP4/4 · 🟢尚未定價。全球 SiC 基板市占 16.7%；Meta Orion 已下單；中國標的有地緣折價。"},
{"sym":"2631.HK","name":"天岳先進(H) SICC","tags":["光學級SiC","SiC基板"],"note":"L2 天岳先進港股（同公司 A+H）。"},
{"sym":"COHR","name":"Coherent","tags":["光學級SiC","光學材料"],"note":"L2 SiC + 光學材料西方主力（原 II-VI），擴 300mm；享去中化溢價。"},
{"sym":"WOLF","name":"Wolfspeed","tags":["SiC","12吋"],"note":"L2 SiC 基板，2026/1 首片 12 吋單晶。"}
]},
{"pos":"上游","name":"L3 製程 / 設備 (NIL/蝕刻)","desc":"奈米壓印 NIL（波導量產關鍵，EVG 私有近壟斷）、SiC 蝕刻。三條波導路線都需設備層，抗路線風險。","concepts":["NIL","蝕刻設備"],"members":[
{"sym":"AMAT","name":"Applied Materials","tags":["蝕刻設備","SiC製程"],"note":"L3 SiC 蝕刻（XR1 70°製程）·全路線受惠但 AR 佔比被稀釋。（EVG 私有，NIL 近壟斷，無公開標的）"}
]},
{"pos":"中游","name":"L4 微顯示 (LCoS/microLED/OLED)","desc":"Meta Ray-Ban Display 用 LCoS；microLED 為下一代（良率未過）；Apple/三星偏 micro-OLED（Sony 產能受限）。","concepts":["LCoS","microLED","microOLED"],"members":[
{"sym":"603501.SS","name":"韋爾股份/豪威 OmniVision","tags":["LCoS","微顯示"],"note":"L4 LCoS 微顯示 · 🔴已定價。Meta Ray-Ban Display 採用；題材已炒過。"},
{"sym":"HIMX","name":"奇景光電 Himax","tags":["LCoS","WiseEye AI"],"note":"L4 LCoS + WiseEye 超低功耗 AI 感測雙卡位 · 🟡定價中。等 2H26 量產驗證。"},
{"sym":"6758.T","name":"Sony 索尼","tags":["microOLED","CIS"],"note":"L4 micro-OLED 全球龍頭，但產能<50萬台/年為死穴；Apple 被迫找替代。ADR=SONY。"},
{"sym":"000725.SZ","name":"京東方 BOE","tags":["microOLED","面板"],"note":"L4 micro-OLED 替代供應，Apple 評估中。"}
]},
{"pos":"中游","name":"L4 高折射率玻璃 (繞射波導材料)","desc":"若 Apple/三星走繞射式(SRG)波導，材料瓶頸轉向高折射率玻璃。反射式+繞射式都吃，抗路線風險。","concepts":["高折玻璃","繞射波導"],"members":[
{"sym":"5201.T","name":"AGC 旭硝子","tags":["高折玻璃","波導晶圓"],"note":"L4 高折射率玻璃晶圓，1.9 折射率量產 AR/MR 波導。"},
{"sym":"7741.T","name":"Hoya","tags":["高折玻璃","精密光學"],"note":"L4 高均勻度高折玻璃、AR/MR 波導晶圓。"},
{"sym":"5218.T","name":"Ohara 小原","tags":["光學玻璃","鑭系"],"note":"L4 含鑭系高折特殊配方光學玻璃。"}
]},
{"pos":"中游","name":"L5 光波導 / 微光學","desc":"真正稀缺層。Meta 用 Lumus 反射波導（私有），公開市場靠廣達(代工)+SCHOTT(私,高折玻璃)+台廠光學間接卡位。","concepts":["光波導","微光學","Lumus生態"],"members":[
{"sym":"2382.TW","name":"廣達 Quanta","tags":["波導代工","光學引擎"],"note":"L5 Lumus 反射波導量產代工+已投專用產線 · CP4/4 · 🟡定價中。公開可買最直接卡位。"},
{"sym":"3406.TW","name":"玉晶光","tags":["微光學","波導"],"note":"L5 微光學/波導卡位，Apple/Sony 鏡頭供應商。AR 營收佔比仍小（題材為主）。"},
{"sym":"3363.TWO","name":"上詮","tags":["光學卡位","CPO"],"note":"L5 光學卡位（CPO/光通訊本業，AR 為延伸）。⚠上櫃。"},
{"sym":"3019.TW","name":"亞洲光學","tags":["AR光學","metalens"],"note":"L5 AR/metalens 微光學。"},
{"sym":"6456.TW","name":"業成 GIS","tags":["microLED面板","AR"],"note":"L5/L4 microLED AR 面板 2H26 量產。"}
]},
{"pos":"下游","name":"L6 系統組裝 / 聲學 / EMS","desc":"歌爾為 Meta 主力組裝廠，且真護城河在聲學（微喇叭/MEMS麥全球第一），市場低估為『組裝』。EMS 含立訊（簽 OpenAI 硬體）。","concepts":["組裝","聲學","EMS"],"members":[
{"sym":"002241.SZ","name":"歌爾股份 GoerTek","tags":["組裝","聲學龍頭"],"note":"L6 Meta 主力組裝+聲學全球第一（微喇叭/MEMS麥）· 組裝🔴已定價但聲學護城河被低估。控股 OmniLight、收 Plessey。地緣標靶。"},
{"sym":"002475.SZ","name":"立訊精密 Luxshare","tags":["EMS","OpenAI"],"note":"L6 EMS 整機代工，簽下 OpenAI 硬體代工（新終端錨點前置）。"},
{"sym":"2018.HK","name":"瑞聲科技 AAC","tags":["聲學","微喇叭"],"note":"L6 聲學（微喇叭/MEMS麥），前五大。"},
{"sym":"KN","name":"Knowles","tags":["MEMS麥克風"],"note":"L6 MEMS 麥克風 23% 市占（WLP 雙雄），享去中化溢價。"},
{"sym":"6794.T","name":"Foster Electric","tags":["微喇叭"],"note":"L6 微喇叭前五大。"},
{"sym":"EL.PA","name":"EssilorLuxottica","tags":["品牌","鏡框"],"note":"L6 Ray-Ban 品牌/鏡框，Meta 合作方。"}
]},
{"pos":"周邊","name":"相機 / 鏡頭 (CIS)","desc":"眼鏡攝影是 Ray-Ban Meta 銷量翻倍主因。CIS/鏡頭確定受惠但已被定價（成熟層，AR 為增量）。","concepts":["CIS","鏡頭"],"members":[
{"sym":"3008.TW","name":"大立光 Largan","tags":["鏡頭","CIS"],"note":"周邊 鏡頭龍頭（iPhone 鏈，AR 增量）。"},
{"sym":"2382.HK","name":"舜宇光學 Sunny Optical","tags":["鏡頭","光學"],"note":"周邊 鏡頭/光學。⚠港股 2382≠台股廣達 2382.TW。"},
{"sym":"ON","name":"onsemi","tags":["CIS","影像感測"],"note":"周邊 CIS 影像感測。"}
]},
{"pos":"周邊","name":"被動元件 / 載板","desc":"AI 眼鏡是 MLCC 超微縮(008004級)與 SLP 載板的新增需求曲線。","concepts":["MLCC","載板"],"members":[
{"sym":"6981.T","name":"村田 Murata","tags":["超微型MLCC"],"note":"周邊 超微型 MLCC 龍頭（0.25×0.125mm）。"},
{"sym":"6976.T","name":"太陽誘電 Taiyo Yuden","tags":["超微型MLCC"],"note":"周邊 超微型 MLCC。"},
{"sym":"2327.TW","name":"國巨 Yageo","tags":["MLCC","被動元件"],"note":"周邊 MLCC/被動元件。"}
]},
{"pos":"周邊","name":"主晶片 SoC","desc":"Qualcomm 近壟斷 Android XR + Meta 陣營，確定受惠但已定價、AR 佔比小（CP 高 alpha 低）。","concepts":["SoC","Snapdragon"],"members":[
{"sym":"QCOM","name":"Qualcomm","tags":["SoC","Snapdragon AR"],"note":"周邊 SoC 主晶片近壟斷（Snapdragon AR1/AR1+）· 🔴已定價。"}
]}
]}
```

- [ ] **Step 2: 驗證 JSON 合法且 ar-xr 鏈完整**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && node -e "
const d=require('./engine/universe/tw_chain.json');
const ar=d.chains.find(c=>c.id==='ar-xr');
if(!ar) throw new Error('找不到 ar-xr 鏈');
let m=0; const mkts={}; ar.stages.forEach(s=>s.members.forEach(x=>{m++; const suf=(x.sym.match(/\.(\w+)\$/)||[,'US'])[1]; mkts[suf]=(mkts[suf]||0)+1; if(!x.sym||!x.name)throw new Error('缺sym/name');}));
console.log('ar-xr 環節='+ar.stages.length,'成員='+m);
console.log('市場分布(後綴):', JSON.stringify(mkts));
console.log('總鏈數:', d.chains.length);
"
```
Expected: `ar-xr 環節=10 成員=34`、市場分布含 TW/SZ/SS/HK/T/DE 等多種、`總鏈數: 4`
（成員 34 = L1.0(4)+L2(4)+L3(1)+L4微顯示(4)+L4玻璃(3)+L5(5)+L6(6)+CIS(3)+被動(3)+SoC(1)；晶盛 300316.SZ 只列於 L1.0，L3 僅 AMAT，EVG 私有不列）

- [ ] **Step 3: Commit**

```bash
git add engine/universe/tw_chain.json
git commit -m "feat: 新增 AR/XR 智慧眼鏡產業鏈(L0-L7, 多市場 37檔, 來自 Obsidian 拆鏈報告)"
```

---

## Task 5: 跑 export 產出行情 + 端到端驗證

**Files:** 無（產生 data/ 產出檔，被 gitignore）

- [ ] **Step 1: 跑 export_chain.py（抓 yfinance）**

Run: `cd /c/Users/u9914/adr-trend-web/engine && python export_chain.py`
Expected: 輸出形如 `[chain] -> 2 路徑  (4 鏈, N 環節, M 檔, 失敗 K)`。M 約 70+（去重後唯一代號）；失敗 K 應很小（報告 35 檔+CPO 既有皆已驗證可抓，偶有個別失敗正常）。

- [ ] **Step 2: 驗證產出 JSON：四鏈、多市場、flow 都在**

Run:
```bash
cd /c/Users/u9914/adr-trend-web && node -e "
const d=require('./web/data/tw_chain.json');
console.log('鏈:', d.chains.map(c=>c.name).join(' / '));
let tot=0, q=0, f=0; const fl={};
d.chains.forEach(c=>c.stages.forEach(s=>s.members.forEach(m=>{tot++; if(m.r5!==undefined&&m.r5!==null)q++; if(m.flow){f++;fl[m.flow]=(fl[m.flow]||0)+1;}})));
console.log('成分股='+tot,'有5日漲='+q,'有flow='+f,'分布='+JSON.stringify(fl));
console.log('失敗:', (d.failed||[]).join(',')||'(無)');
"
```
Expected: 4 條鏈名印出、`成分股` 70+、多數有 r5 與 flow、`失敗` 清單很短（個別代號）。

- [ ] **Step 3: 既有全測試不回歸**

Run: `cd /c/Users/u9914/adr-trend-web && node web/test_chain_intl.mjs && node web/test_chain_dom.mjs && node web/test_search_dom.mjs && node web/test_cross_dom.mjs 2>&1 | tail -1`
Expected: 四個測試全綠。

- [ ] **Step 4: 本機起站台抽驗跨市場個股呈現**

Run（背景起站，驗完收掉）:
```bash
cd /c/Users/u9914/adr-trend-web/web && python -m http.server 8767 >/tmp/h3.log 2>&1 &
```
然後:
```bash
curl -s "http://localhost:8767/data/tw_chain.json" | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const d=JSON.parse(s);const ar=d.chains.find(c=>c.id==='ar-xr');const sicc=ar.stages.flatMap(x=>x.members).find(m=>m.sym==='688234.SS');console.log('站台 ar-xr 天岳:',JSON.stringify({sym:sicc.sym,r5:sicc.r5,flow:sicc.flow}));})"
```
Expected: 站台可服務、天岳先進有 r5/flow 數值。驗完結束 http.server。

- [ ] **Step 5: 無 commit（產出檔 gitignore）**

確認 `git status` 乾淨（產出檔被忽略）：
Run: `cd /c/Users/u9914/adr-trend-web && git status --short`
Expected: 空（無未追蹤的 data 檔顯示）。

---

## 完成後
- 推分支 `feat/cpo-global-names`、開 PR。
- 合併後觸發 workflow（或等排程），線上產業鏈分頁即顯示 CPO 全球龍頭 + AR/XR 新鏈，各檔帶市場標記與資金流向。

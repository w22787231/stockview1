// headless 驗 memberCard：抽函式 + stub helper，驗各情境輸出。
import { readFileSync } from "node:fs";
import assert from "node:assert";
import vm from "node:vm";

const ROOT = "C:/Users/u9914/adr-trend-web/web";
const html = readFileSync(ROOT + "/index.html", "utf8");
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const appJs = scripts[scripts.length - 1];

// 抽出需要的函式：memberCard（與其相依的 FLOW_LABEL/quoteCol 一起在 appJs 裡）
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
const helpers = `
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const sgn = (n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls = n => n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
`;
// FLOW_LABEL 與 quoteCol 是 memberCard 的相依，需一起載入
const flS = appJs.indexOf("const FLOW_LABEL");
const flowLabel = flS >= 0 ? appJs.slice(flS, appJs.indexOf("\n", flS)) : "";
vm.runInContext(helpers + "\n" + flowLabel + "\n" + extract("quoteCol") + "\n" + extract("memberCard") + "\nglobalThis.memberCard = memberCard;", sandbox);

// 情境 1：完整行情 + inflow
const h1 = sandbox.memberCard({sym:"3363.TWO", name:"上詮", tags:["FAU"], note:"夥伴",
  r1:2.0, r5:3.07, r20:3.07, volr:2.1, flow:"inflow"});
assert.ok(h1.includes("mstock-quote"), "缺漲跌列");
assert.ok(h1.includes("mstock-flow inflow"), "缺 inflow 徽章");
assert.ok(h1.includes("資金流入"), "缺流入文字");
assert.ok(h1.includes('data-stk="3363.TWO"'), "缺可點 data-stk");
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

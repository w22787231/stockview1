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
const unknown = sandbox.marketOf("FOO.XYZ");
assert.equal(unknown.mkt, "", "未知後綴 mkt 應為空");

// memberCard 跨市場：抽 memberCard + 相依 helper
const helpers = `
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const sgn = (n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls = n => n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
const FLOW_LABEL = {inflow:"x",outflow:"x",quiet:"x",neutral:"x"};
`;
vm.runInContext(helpers + extract("quoteCol") + extract("memberCard") + "\nglobalThis.memberCard = memberCard;", sandbox);

const hcn = sandbox.memberCard({sym:"688234.SS", name:"天岳先進", r1:1, r5:2, r20:3, flow:"inflow"});
assert.ok(hcn.includes("mstock-mkt cn"), "滬股應有 cn class");
assert.ok(hcn.includes(">滬<"), "應顯示 滬");
assert.ok(hcn.includes(">688234<"), "code 應去 .SS 顯示 688234");
assert.ok(hcn.includes('data-stk="688234.SS"'), "data-stk 應保留完整 sym");

const hus = sandbox.memberCard({sym:"NVDA", name:"輝達", r1:1, r5:1, r20:1});
assert.ok(hus.includes("mstock-mkt us") && hus.includes(">美<"), "美股應顯示 美/us");

const heu = sandbox.memberCard({sym:"SIVE.ST", name:"Sivers"});
assert.ok(heu.includes(">瑞<") && heu.includes(">SIVE<"), "SIVE.ST 應顯示 瑞 + code SIVE");

const htw = sandbox.memberCard({sym:"3363.TWO", name:"上詮"});
assert.ok(htw.includes(">櫃<") && htw.includes(">3363<"), "台股櫃仍正確");

console.log("✅ marketOf 各市場後綴測試全過");

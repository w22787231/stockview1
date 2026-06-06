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

console.log("✅ marketOf 各市場後綴測試全過");

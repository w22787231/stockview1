// headless 驗搜尋核心純函式：lookupByName(中文名查代號) 與 resolveSymByCode(代號解析)。
// 抽函式 + 真實 tw_names.json，跑斷言確認中文名/代號雙向搜尋正確。
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
vm.runInContext(
  extract("lookupByName") + "\n" + extract("resolveSymByCode") +
  "\nglobalThis.lookupByName = lookupByName; globalThis.resolveSymByCode = resolveSymByCode;",
  sandbox
);

// 用真實 names 對照表建 NAME_IDX（與 loadNames 同樣結構）
const map = JSON.parse(readFileSync(ROOT + "/data/tw_names.json", "utf8"));
const names = Object.keys(map).map(sym => ({ sym, name: String(map[sym] || "") }));
const byName = {};
names.forEach(x => { if (x.name) byName[x.name] = x.sym; });
const ni = { names, byName };

// 1) 中文名精確命中 → exact 有值（截圖的「鴻海」案例）
const r1 = sandbox.lookupByName(ni, "鴻海");
assert.equal(r1.exact, "2317.TW", "鴻海 應精確對到 2317.TW，實得 " + r1.exact);

// 2) 中文名部分比對 → matches 多筆、精確者（若有）排前
const r2 = sandbox.lookupByName(ni, "台");
assert.ok(r2.matches.length >= 2, "「台」應有多筆，實得 " + r2.matches.length);

// 3) 查無中文名 → exact null、matches 空
const r3 = sandbox.lookupByName(ni, "這不是公司名XYZ");
assert.equal(r3.exact, null);
assert.equal(r3.matches.length, 0);

// 4) 空字串 → 安全回空
const r4 = sandbox.lookupByName(ni, "");
assert.equal(r4.exact, null);
assert.equal(r4.matches.length, 0);

// 5) resolveSymByCode：數字代號解析
const syms = ["2330.TW", "3363.TWO", "NVDA"];
assert.equal(sandbox.resolveSymByCode(syms, "2330"), "2330.TW", "2330 應解析為 2330.TW");
assert.equal(sandbox.resolveSymByCode(syms, "3363"), "3363.TWO", "3363 應解析為 3363.TWO");
assert.equal(sandbox.resolveSymByCode(syms, "NVDA"), "NVDA");
assert.equal(sandbox.resolveSymByCode(syms, "9999"), null, "不存在代號應回 null");

console.log("✅ 搜尋核心測試全過：中文名精確/部分比對、查無、代號解析");

// 抽出 safeHavenBox,stub 最小 DOM,斷言輸出含標題/現值/百分位/反轉按鈕/S&P500說明。
import { readFileSync } from "node:fs";
import assert from "node:assert";
const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
function extract(name){
  const s = html.indexOf("function " + name);
  if (s < 0) throw new Error("缺函式 " + name);
  const o = html.indexOf("{", s);
  let d = 0;
  for (let i = o; i < html.length; i++){
    if (html[i] === "{") d++;
    else if (html[i] === "}"){ d--; if (d===0) return html.slice(s, i+1); }
  }
  throw new Error("不平衡 " + name);
}
const stub = `
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let SH_INV=false;
let SH_RANGE='all';
const SH_WINS=[["1m",21,"1M"],["3m",63,"3M"],["6m",126,"6M"],["all",Infinity,"ALL"]];
`;
const N = 60;
const withS = {
  cur: 3.04, pctile: 74,
  dates: Array.from({length: N}, (_, i) => "2026-05-" + String((i % 28) + 1).padStart(2, "0")),
  y: Array.from({length: N}, (_, i) => +(1.5 * Math.sin(i / 10)).toFixed(2)),
  sp500: Array.from({length: N}, (_, i) => 6000 + i * 2),
  src: "test",
};
const src = stub + extract("safeHavenBox") + "\nglobalThis.__OUT=safeHavenBox(" + JSON.stringify(withS) + ");\n";
const fn = new Function(src + "return globalThis.__OUT;");
const out = fn();
assert.ok(out.includes("Safe Haven Demand"), "缺標題");
assert.ok(out.includes("+3.04pt"), "缺現值");
assert.ok(out.includes("第 <b>74</b> 百分位"), "缺歷史百分位");
assert.ok(out.includes("shInvBtn") && out.includes("反轉視角"), "缺反轉按鈕");
assert.ok(out.includes("紫線=S&amp;P500"), "缺 S&P500 疊圖說明");
assert.ok(out.includes("shChart"), "缺圖表容器");
assert.ok(out.includes('data-shw="1m"') && out.includes('data-shw="all"'), "缺時間按鈕");

const srcInv = stub.replace("let SH_INV=false;", "let SH_INV=true;")
  + extract("safeHavenBox") + "\nglobalThis.__OUT=safeHavenBox(" + JSON.stringify(withS) + ");\n";
const outInv = new Function(srcInv + "return globalThis.__OUT;")();
assert.ok(outInv.includes("(-y)") && outInv.includes(" active"), "反轉狀態按鈕未反映 SH_INV");
console.log("SAFE_HAVEN_DOM_OK");

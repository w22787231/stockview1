// 抽出 erpBox,stub 最小 DOM,斷言輸出含標題/現值/百分位/按鈕。
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
let ERP_RANGE='3y';
`;
const src = stub + extract("erpBox")
  + "\nglobalThis.__OUT=erpBox({cur:0.2,fwd_pe:21.1,dgs10:4.54,pctile:7,"
  + "dates:['2026-06-25','2026-07-02','2026-07-10'],erp:[0.48,0.32,0.2],"
  + "src:'test'});\n";
const fn = new Function(src + "return globalThis.__OUT;");
const out = fn();
assert.ok(out.includes("股票風險溢酬 ERP"), "缺標題");
assert.ok(out.includes("+0.2%"), "缺現值");
assert.ok(out.includes("21.1x"), "缺 Forward P/E");
assert.ok(out.includes("4.54%"), "缺 10Y 殖利率");
assert.ok(out.includes("第 <b>7</b> 百分位"), "缺歷史百分位");
assert.ok(out.includes("data-er="), "缺時間按鈕");
assert.ok(out === "" || out.includes("erpChart"), "缺圖表容器");
console.log("ERP_DOM_OK");

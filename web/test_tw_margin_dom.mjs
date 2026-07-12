// 抽出 renderTwMarginRatio + updStamp,stub 最小 DOM/echarts,斷言輸出含標題/更新時間/130%/現值。
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
let CAP='';
const $ = sel => ({ set innerHTML(v){ CAP=v; }, get innerHTML(){ return CAP; }, querySelectorAll(){ return []; } });
const document = { getElementById(){ return null; } };  // draw 早退(!el)
const window = {};                                       // 無 echarts → draw 早退
`;
const src = stub + extract("updStamp") + "\nlet TWMR_DATA=null, TWMR_WIN='all';\n"
  + "const TWMR_WINS=[['1m',21,'1M'],['3m',63,'3M'],['6m',126,'6M'],['1y',252,'1Y'],['all',Infinity,'全部']];\n"
  + extract("renderTwMarginRatio") + extract("drawTwMarginRatioChart")
  + "\nrenderTwMarginRatio({as_of:'20260706',level:194.55,diff:-0.8,"
  + "dates:['20260702','20260703','20260706'],ratio:[195.1,195.3,194.55],twii:[23400,23450,23380],"
  + "src:'TWSE'});\nglobalThis.__OUT=CAP;\n";
const fn = new Function(src + "return globalThis.__OUT;");
const out = fn();
assert.ok(out.includes("台股大盤融資維持率"), "缺標題");
assert.ok(out.includes("更新時間:星期"), "缺更新時間戳(星期)");
assert.ok(out.includes("194.55"), "缺現值");
assert.ok(out.includes("130%") || out.includes("斷頭"), "缺 130% 說明");
assert.ok(out.includes("data-twmrw"), "缺時間按鈕");
console.log("TW_MARGIN_DOM_OK");

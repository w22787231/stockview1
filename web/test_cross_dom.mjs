// 暫時 headless 驗證：實際執行 renderCross 對真實 ndx100 資料，斷言輸出 HTML 正確。
// 抽出相關函式 + stub 最小 DOM/helpers，跑一遍確認無 runtime error 且三區塊都在。
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

// 最小 stub：buildTable 只把 rows 串成可斷言的標記；helpers 簡化但保留行為特徵。
const stub = `
let CAPTURED = {};
function buildTable(id, rows, cols, opts){
  CAPTURED[id] = rows.length;
  if(opts && opts.empty && !rows.length) return '<div class="note">'+opts.empty+'</div>';
  const body = rows.map(r=>cols.map(c=>c.rownum?'<td>#</td>':c.cell(r)).join('')).join('');
  return '<table id="'+id+'">'+body+'</table>';
}
function symCell(sym,name){ return '<td class="sym clickable" data-stk="'+sym+'">'+sym+(name?'<span class="nm">'+name+'</span>':'')+'</td>'; }
function crossSortVal(r){ return r.cross_state==='golden'?1:0; }
const cls = x => x==null?'dim':(x>=0?'pos':'neg');
const sgn = (x,n)=> x==null?'–':((x>=0?'+':'')+Number(x).toFixed(n==null?2:n));
const fmtNum = (x,n)=> x==null?'–':Number(x).toFixed(n==null?0:n);
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let CONTENT = '';
const $ = sel => ({ set innerHTML(v){ CONTENT = v; }, get innerHTML(){ return CONTENT; } });
`;

const src = stub +
  extract("sortCrossRows") + "\n" +
  extract("freshCrosses") + "\n" +
  extract("crossSignalTable") + "\n" +
  extract("renderCross") + "\n" +
  "return { renderCross, getContent: ()=>CONTENT, getCaptured: ()=>CAPTURED };";

const mod = new Function(src)();

const d = JSON.parse(readFileSync(new URL("./data/ndx100.json", import.meta.url), "utf8"));
const cs = d.cross_signals;

// 1) 正常資料：執行不報錯
mod.renderCross(d);
const out = mod.getContent();
const cap = mod.getCaptured();

assert(out.includes("交叉訊號"), "缺標題");
assert(out.includes("MA10×MA50"), "缺 MA 標籤");
assert(out.includes(d.pool_label), "缺 pool_label");  // NDX100 無特殊字元
assert(out.includes("最近剛觸發"), "缺剛觸發區");
assert(out.includes("全部金叉（"+cs.n_golden+" 檔）"), "金叉檔數標籤錯");
assert(out.includes("全部死叉（"+cs.n_death+" 檔）"), "死叉檔數標籤錯");
assert(out.includes('id="t-cross-gold"'), "缺金叉表");
assert(out.includes('id="t-cross-death"'), "缺死叉表");
// 表格列數要對得上資料
assert.strictEqual(cap["t-cross-gold"], cs.n_golden, "金叉表列數="+cap["t-cross-gold"]);
assert.strictEqual(cap["t-cross-death"], cs.n_death, "死叉表列數="+cap["t-cross-death"]);
// fresh 表存在且列數 = freshCrosses 數（若 >0）
const freshCount = (cs.golden.concat(cs.death)).filter(r=>r.cross_days!=null && r.cross_days<=cs.fresh_days).length;
if(freshCount>0){
  assert(out.includes('id="t-cross-fresh"'), "有 fresh 但缺表");
  assert.strictEqual(cap["t-cross-fresh"], freshCount, "fresh 表列數錯");
}
console.log("normal render OK: gold", cap["t-cross-gold"], "death", cap["t-cross-death"], "fresh", freshCount);

// 2) 無 cross_signals：走 fallback 文案，不報錯
mod.renderCross({});
assert(mod.getContent().includes("尚未含交叉訊號"), "缺 fallback 文案");
console.log("fallback OK");

// 3) 空池：golden/death 皆空 → empty 訊息
mod.renderCross({pool_label:"X", n_ok:0, cross_signals:{fresh_days:3, golden:[], death:[], n_golden:0, n_death:0}});
const empt = mod.getContent();
assert(empt.includes("（本池目前無金叉）"), "缺金叉空訊息");
assert(empt.includes("（本池目前無死叉）"), "缺死叉空訊息");
assert(empt.includes("近 3 日無新交叉觸發"), "缺剛觸發空訊息");
console.log("empty pool OK");

console.log("\nheadless renderCross tests passed");

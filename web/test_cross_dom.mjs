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
  const head = cols.map(c=>'<th>'+c.h+'</th>').join('');
  const body = rows.map(r=>cols.map(c=>c.rownum?'<td>#</td>':c.cell(r)).join('')).join('');
  return '<table id="'+id+'"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table>';
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
  "let CROSS_MODE='pool';\n" +
  extract("crossModeBar") + "\n" +
  extract("_pushOn") + "\n" +
  extract("pushBar") + "\n" +
  extract("sortCrossRows") + "\n" +
  extract("freshCrosses") + "\n" +
  extract("_crossBtScore") + "\n" +
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
assert(out.includes("EMA20×EMA60"), "缺 EMA 標籤");
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

// 4) 回測欄位：fresh 表 + 全部金叉表都 withBacktest=true,須出現
//    金叉勝率/平均報酬/平均賺/平均賠/賺賠比/金叉評分/樣本 表頭 + 數值;死叉表不帶。
const freshRow = {sym:"ZZZ", name:null, cross_state:"golden", cross_days:1,
                  sc5:80, r5:5.0, score:1000, bt_win_rate:67, bt_avg:12.3, bt_n:9,
                  bt_avg_win:18.0, bt_avg_loss:-4.0, bt_pl_ratio:4.5, bt_worst:-9.0};
const oldRow  = {sym:"YYY", name:null, cross_state:"golden", cross_days:40,
                 sc5:50, r5:1.0, score:500, bt_win_rate:40, bt_avg:2.1, bt_n:12,
                 bt_avg_win:10.0, bt_avg_loss:-3.0, bt_pl_ratio:3.33, bt_worst:-31.0};
mod.renderCross({pool_label:"T", n_ok:2,
  cross_signals:{fresh_days:3, golden:[freshRow, oldRow], death:[], n_golden:2, n_death:0}});
const bt = mod.getContent();
assert(bt.includes("金叉勝率"), "缺 金叉勝率 表頭");
assert(bt.includes("平均報酬"), "缺 平均報酬 表頭");
assert(bt.includes("平均賺"), "缺 平均賺 表頭");
assert(bt.includes("平均賠"), "缺 平均賠 表頭");
assert(bt.includes("賺賠比"), "缺 賺賠比 表頭");
assert(bt.includes(">最差<"), "缺 最差 表頭");
assert(bt.includes("金叉評分"), "缺 金叉評分 表頭");
assert(bt.includes("-31.0%"), "缺 bt_worst 值");      // oldRow 最差 ≤-25% 應標紅
assert(bt.includes(">樣本<"), "缺 樣本 表頭");
assert(bt.includes("67%"), "缺 bt_win_rate 值");      // 67 -> "67%"
assert(bt.includes("+12.3%"), "缺 bt_avg 值");        // sgn(12.3,1)
assert(bt.includes("+18.0%"), "缺 bt_avg_win 值");
assert(bt.includes("-4.0%"), "缺 bt_avg_loss 值");
assert(bt.includes("4.50"), "缺 bt_pl_ratio 值");     // toFixed(2)
// 全部金叉表現在也帶回測欄
const goldSeg = bt.slice(bt.indexOf('id="t-cross-gold"'), bt.indexOf('</table>', bt.indexOf('id="t-cross-gold"')));
assert(goldSeg.includes("金叉評分"), "全部金叉表應帶回測欄");
console.log("backtest columns OK (fresh + 全部金叉)");

console.log("\nheadless renderCross tests passed");

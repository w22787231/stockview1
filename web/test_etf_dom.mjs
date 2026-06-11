// ETF 分頁 headless 測試:實際跑 renderEtf 對假 etf.json，斷言日期/ETF分組/篩選/空狀態。
// 執行:cd web && node test_etf_dom.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
function extract(name){
  const s = html.indexOf("function " + name);
  if (s < 0) throw new Error("缺 " + name);
  const o = html.indexOf("{", s);
  let d = 0;
  for (let i = o; i < html.length; i++){
    if (html[i] === "{") d++;
    else if (html[i] === "}"){ d--; if (d===0) return html.slice(s, i+1); }
  }
  throw new Error("不平衡 " + name);
}
function extractConst(name){
  const re = new RegExp("const " + name + "\\s*=\\s*\\{[^}]*\\}", "m");
  const m = html.match(re); if(!m) throw new Error("缺 const "+name); return m[0];
}

const stub = `
let CAPTURED="";
const SORT_STATE={};
const fmtNum=(n,d=0)=> n==null?"–":Number(n).toFixed(d);
const sgn=(n,d=2)=> n==null?"–":(n>=0?"+":"")+Number(n).toFixed(d);
const cls=n=> n==null?"dim":(n>0?"pos":(n<0?"neg":"dim"));
const esc=s=>(s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function symCell(sym,name){return '<td class="sym clickable" data-stk="'+esc(sym)+'">'+esc(sym)+(name?'<span class="nm">'+esc(name)+'</span>':'')+'</td>';}
let ETF_DATA=null, ETF_FILTER={etf:"all",action:"all"};
const fakeEl={ set innerHTML(v){CAPTURED=v;}, get innerHTML(){return CAPTURED;}, querySelectorAll(){return [];} };
const $=()=>fakeEl;
`;

const src = stub + "\n" +
  extractConst("ETF_ACTION_CLS") + "\n" +
  extractConst("ETF_ACTION_ICON") + "\n" +
  extract("etfFilterBar") + "\n" +
  extract("etfChangeTable") + "\n" +
  extract("etfSnapshotTables") + "\n" +
  extract("etfRecentAddDrop") + "\n" +
  extract("renderEtf") + "\n" +
  "return { renderEtf, setData:(d,f)=>{ETF_DATA=d; if(f)ETF_FILTER=f;}, get:()=>CAPTURED };";
const m = new Function(src)();

const DATA = {
  generated_at:"2026-06-07T00:00:00Z",
  order:["00981A","00982A"],
  etfs:{"00981A":{name:"統一台股增長"},"00982A":{name:"群益台灣精選強棒"}},
  snapshot:{},
  history:[
    {date:"2026-06-06", changes:[
      {etf:"00982A",etf_name:"群益台灣精選強棒",code:"3231",name:"緯創",action:"新增",dqty:5000,qty:5000,dweight:1.2,weight:2.1},
      {etf:"00981A",etf_name:"統一台股增長",code:"2330",name:"台積電",action:"加碼",dqty:120,qty:11960,dweight:0.3,weight:10.11},
    ]},
    {date:"2026-06-05", changes:[
      {etf:"00981A",etf_name:"統一台股增長",code:"2317",name:"鴻海",action:"減碼",dqty:-50,qty:450,dweight:-0.1,weight:3.2},
    ]},
  ],
};

// daily：每日明細區(7 天摘要 details 之後),用來測「日期/篩選/順序」而不受 7 天區塊干擾
const dailyPart = o => { const i=o.indexOf("</details>"); return i<0?o:o.slice(i); };

// 1) 正常渲染:兩個日期、每日明細區 00981A 排在 00982A 前(依 order)
m.setData(DATA, {etf:"all",action:"all"});
m.renderEtf();
let out = m.get();
assert(out.includes("2026-06-06"), "缺最新日期");
assert(out.includes("2026-06-05"), "缺次日");
assert(out.includes("（最新）"), "缺最新標記");
const dly = dailyPart(out);
const i81 = dly.indexOf("00981A 統一台股增長"), i82 = dly.indexOf("00982A 群益台灣精選強棒");
assert(i81>0 && i82>0 && i81<i82, "ETF 分組順序應依 order(00981A 在前)");
assert(out.includes("台積電") && out.includes("緯創"), "缺個股");
console.log("PASS render + 分組順序");

// 1b) 近 7 天 新增/出清 區塊:含標題 + 緯創(新增,不受動作篩選影響)
assert(out.includes("近 7 天 新增・出清紀錄"), "缺 7 天區塊標題");
const recPart = out.slice(0, out.indexOf("</details>"));
assert(recPart.includes("緯創") && recPart.includes("🆕新增"), "7 天區塊缺新增事件");
console.log("PASS 近 7 天 新增/出清 區塊");

// 2) ETF 篩選:只看 00982A → 不該出現 00981A 的台積電
m.setData(DATA, {etf:"00982A",action:"all"});
m.renderEtf(); out = m.get();
assert(out.includes("緯創") && !out.includes("台積電"), "ETF 篩選失效");
console.log("PASS ETF 篩選");

// 3) 動作篩選:只看 減碼 → 每日明細區只剩鴻海(緯創新增僅在 7 天摘要,不算違規)
m.setData(DATA, {etf:"all",action:"減碼"});
m.renderEtf(); out = m.get();
assert(dailyPart(out).includes("鴻海") && !dailyPart(out).includes("緯創"), "動作篩選失效");
console.log("PASS 動作篩選");

// 4) 空 history → fallback
m.setData({order:[],etfs:{},history:[]}, {etf:"all",action:"all"});
m.renderEtf(); out = m.get();
assert(out.includes("尚無逐日異動紀錄"), "缺空狀態文案");
console.log("PASS 空狀態");

console.log("\nAll ETF DOM tests passed");

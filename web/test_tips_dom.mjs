// headless 驗證：對合成 tips.json 跑 renderTips + drawTipsChart，
// 斷言卡片數值、5 顆時間按鈕、視窗切片、ECharts option(2 grid / 3 series / 3 yAxis)。
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

// ── 合成資料：300 個交易日，tips 在 1.8~2.4% 遊走，sp500 4000~5200，corr20 前 20 為 null ──
const N = 300;
const dates=[], tips=[], sp500=[], corr20=[];
let day = Date.UTC(2024,0,1);
for(let i=0;i<N;i++){
  const dt = new Date(day + i*86400000);
  dates.push(dt.toISOString().slice(0,10));
  tips.push(+(2.1 + 0.3*Math.sin(i/25)).toFixed(3));
  sp500.push(+(4600 + 300*Math.sin(i/40) + i).toFixed(2));
  corr20.push(i<20 ? null : +(-0.4 + 0.5*Math.sin(i/15)).toFixed(3));
}
const DATA = {
  as_of: dates[dates.length-1], corr_win:20,
  tips_last: tips[tips.length-1], tips_diff_bps: 3.0, corr20_last: corr20[corr20.length-1],
  windows:["3m","6m","1y","3y","5y"], default_window:"1y",
  series:{dates, tips, sp500, corr20},
};

// ── stub：$ / esc / echarts,並捕捉 setOption 與按鈕 ──
let BOX_HTML="", CHART_HTML="", CAP=null, BTNS=[];
const chartEl={ set innerHTML(v){CHART_HTML=v;}, get innerHTML(){return CHART_HTML;}, _ro:null };
const boxEl={
  set innerHTML(v){ BOX_HTML=v;
    // 解析 data-tw 按鈕數量
    BTNS=[...v.matchAll(/data-tw="([^"]+)"/g)].map(m=>({dataset:{tw:m[1]}, onclick:null}));
  },
  get innerHTML(){return BOX_HTML;},
  querySelectorAll(sel){ return sel.includes("data-tw") ? BTNS : []; },
};
const stub = `
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const $ = sel => sel==='#tipsBlock' ? BOX : CHART;
let TIPS_WIN="1y";
const TIPS_WIN_LABEL={"3m":"3月","6m":"6月","1y":"1年","3y":"3年","5y":"5年"};
const TIPS_WIN_N={"3m":63,"6m":126,"1y":252,"3y":756,"5y":1260};
`;
const src = "const {BOX,CHART,ECH,DATA}=__ctx;\n" +
  "const echarts=ECH;\n" +
  "const window={echarts:ECH, addEventListener(){}, removeEventListener(){}};\n" +
  stub +
  "let TIPS_DATA=DATA;\n" +      // 模擬 loadTips 已填快取,讓按鈕 onclick 的 renderTips(TIPS_DATA) 可用
  extract("drawTipsChart") + "\n" +
  extract("renderTips") + "\n" +
  "return { renderTips };";

// echarts stub
const ECH = {
  getInstanceByDom(){ return null; },
  init(){ return { setOption(opt){ CAP=opt; }, resize(){}, dispose(){} }; },
};
const factory = new Function("__ctx", src);
const api = factory({BOX:boxEl, CHART:chartEl, ECH, DATA});

// 1) 正常渲染不報錯
api.renderTips(DATA);
const box = boxEl.innerHTML;
assert.ok(box.includes("TIPS 實質利率 × S&P500"), "缺標題");
assert.ok(box.includes(tips[tips.length-1].toFixed(2)+"%"), "缺 TIPS 當前值卡");
assert.ok(box.includes("20日相關"), "缺相關卡");

// 2) 5 顆時間按鈕、預設 1y active
assert.strictEqual(BTNS.length, 5, "時間按鈕數應為 5，實得 "+BTNS.length);
assert.ok(box.includes('data-tw="1y"'), "缺 1y 按鈕");
const activeMatch = box.match(/class="btn active" data-tw="([^"]+)"/);
assert.ok(activeMatch && activeMatch[1]==="1y", "預設 active 應為 1y");

// 3) ECharts option：2 grid / 3 series / 3 yAxis / 2 xAxis
assert.ok(CAP, "setOption 未被呼叫");
assert.strictEqual(CAP.grid.length, 2, "grid 應為 2(主圖+子圖)");
assert.strictEqual(CAP.series.length, 3, "series 應為 3(TIPS/SP500/corr)");
assert.strictEqual(CAP.yAxis.length, 3, "yAxis 應為 3");
assert.strictEqual(CAP.xAxis.length, 2, "xAxis 應為 2(共用時間軸)");
// 子圖相關 series 綁 gridIndex1(xAxisIndex1/yAxisIndex2),且有 0 基準 markLine
const corrS = CAP.series[2];
assert.strictEqual(corrS.xAxisIndex, 1, "corr series 應綁 xAxisIndex1");
assert.strictEqual(corrS.yAxisIndex, 2, "corr series 應綁 yAxisIndex2");
assert.ok(corrS.markLine, "corr 子圖應有 0 基準線");
// yAxis[2] 為相關軸,min/max = -1/1
assert.strictEqual(CAP.yAxis[2].min, -1, "相關軸 min 應 -1");
assert.strictEqual(CAP.yAxis[2].max, 1, "相關軸 max 應 1");
// 1y 視窗:min(252, 300)=252 點
assert.strictEqual(CAP.series[0].data.length, 252, "1y 應切 252 點,實得 "+CAP.series[0].data.length);

// 4) 切換到 3m → 63 點
BTNS.find(b=>b.dataset.tw==="3m").onclick();   // 觸發重繪(renderTips 內綁的 onclick)
assert.strictEqual(CAP.series[0].data.length, 63, "3m 應切 63 點,實得 "+CAP.series[0].data.length);

// 5) 相關子圖前 20 點為 null(暖身),不連線
const corrData3m = CAP.series[2].data;   // 3m=63 點,全在暖身之後,應皆非 null
assert.ok(corrData3m.every(p=>p[1]!==null), "3m 視窗(近 63 日)相關應皆有值");

console.log("✅ test_tips_dom 全部通過：卡片/5 按鈕/2grid-3series/視窗切片(252→63)/相關子圖");

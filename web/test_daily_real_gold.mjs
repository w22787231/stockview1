import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
function extract(name){
  const start = html.indexOf("function " + name);
  if(start < 0) throw new Error("找不到函式：" + name);
  const open = html.indexOf("{", start); let depth = 0;
  for(let i=open;i<html.length;i++){
    if(html[i]==="{") depth++;
    else if(html[i]==="}" && --depth===0) return html.slice(start,i+1);
  }
  throw new Error("函式未完整結束：" + name);
}

const dates=[], real=[], gold=[], corr5=[], corr10=[], corr20=[];
for(let i=0;i<80;i++){
  dates.push(new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10));
  real.push(+(1.8+i/100).toFixed(3)); gold.push(2650+i*3); corr5.push(i<5?null:+(-.2+i/100).toFixed(3)); corr10.push(i<10?null:+(-.4+i/100).toFixed(3)); corr20.push(i<20?null:+(-.6+i/100).toFixed(3));
}
const block={corr_windows:[5,10,20],series:{'10Y 實質利率':{dates,values:real},'黃金期貨':{dates,values:gold},'5日相關':{dates,values:corr5},'10日相關':{dates,values:corr10},'20日相關':{dates,values:corr20}}};
let option=null;
const chart={_ro:null,innerHTML:""};
const ECH={getInstanceByDom(){return null;},init(){return{setOption(v){option=v;},resize(){},dispose(){}};}};
const src=`const {CHART,ECH}=__ctx; const $=s=>s==='#daily-chart-real-gold'?CHART:null; const echarts=ECH; const window={echarts:ECH,addEventListener(){},removeEventListener(){}}; const DAILY_CHART_RANGE_DAYS={"1m":31,"3m":93,"6m":184,"1y":366,all:null}; ${extract('_dailyRangeStart')} ${extract('renderDailyRealGoldChart')} return {renderDailyRealGoldChart};`;
const api=new Function('__ctx',src)({CHART:chart,ECH});
api.renderDailyRealGoldChart('daily-chart-real-gold',block);

assert.ok(option,'應建立圖表設定');
assert.strictEqual(option.grid.length,2,'主圖與相關性子圖應各有一個 grid');
assert.strictEqual(option.series.length,3,'應只保留實際利率、黃金與20日相關性');
assert.strictEqual(option.yAxis.length,3,'主圖需雙軸，子圖需相關性軸');
assert.strictEqual(option.series[1].yAxisIndex,1,'黃金應使用主圖右側軸');
assert.strictEqual(option.series[2].name,'20日相關','應只顯示20日主判讀線');
assert.ok(option.series.slice(2).every(s=>s.xAxisIndex===1&&s.yAxisIndex===2),'相關性應在下方子圖');
assert.deepStrictEqual(option.series[2].markLine.data.map(x=>x.yAxis).sort((a,b)=>a-b),[-.6,-.35,0],'應有 -0.60、-0.35 與 0 的判讀虛線');
assert.strictEqual(option.yAxis[2].min,-1,'相關性下限應為 -1');
assert.strictEqual(option.yAxis[2].max,1,'相關性上限應為 1');
api.renderDailyRealGoldChart('daily-chart-real-gold',block,'1m');
assert.ok(option.series.every(series=>series.data.length<=32),'1M 按鈕必須把實際利率、黃金與相關性共同裁切到近一個月');
console.log('daily real-gold chart test passed');

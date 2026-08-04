import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import assert from "node:assert";

const require = createRequire(import.meta.url);
const real = require("echarts");
const html = readFileSync(new URL("index.html", import.meta.url), "utf8");
function extract(name){
  const start=html.indexOf("function "+name); assert.ok(start>=0, name+" missing");
  const open=html.indexOf("{",start); let depth=0;
  for(let i=open;i<html.length;i++){
    if(html[i]==="{") depth++;
    else if(html[i]==="}" && --depth===0) return html.slice(start,i+1);
  }
  throw new Error(name+" extraction failed");
}
let option;
const echarts={
  getInstanceByDom(){return null;},
  init(){
    const chart=real.init(null,null,{renderer:"svg",ssr:true,width:900,height:330});
    return {setOption(o){option=o;chart.setOption(o);assert.ok(chart.renderToSVGString().length>100);},resize(){},dispose(){chart.dispose();}};
  },
};
const draw=new Function("return (function($,window,echarts){"+extract("drawNdxForwardPeChart")+";return drawNdxForwardPeChart;})")()(()=>({}),{echarts,addEventListener(){},removeEventListener(){}},echarts);
const dates=[],pe=[],qqq=[];
for(let i=0;i<121;i++){dates.push(new Date(Date.UTC(2016,i,29)).toISOString().slice(0,10));pe.push(18+i/30);qqq.push(100+i*4);}
draw("chart",dates,pe,qqq);
assert.strictEqual(option.series.length,2,"須有估值與 QQQ 兩條線");
assert.strictEqual(option.yAxis.length,2,"須有兩個 y 軸");
assert.strictEqual(option.series[1].yAxisIndex,1,"QQQ 須使用右軸");
assert.strictEqual(option.series[0].data.length,121,"估值序列長度錯誤");
console.log("NDX Forward P/E × QQQ ECharts 雙軸圖：通過");
process.exit(0);

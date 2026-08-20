import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");

function extract(name){
  const start = html.indexOf("function " + name);
  if(start < 0) throw new Error("缺函式 " + name);
  const open = html.indexOf("{", start);
  let depth = 0;
  for(let i=open; i<html.length; i++){
    if(html[i] === "{") depth++;
    else if(html[i] === "}" && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error("函式括號不平衡：" + name);
}

assert.match(html, /期末美元流動性預估/);
assert.match(html, /TGA 期末預估/);
assert.match(html, /銀行準備金期末預估/);
assert.match(html, /完整淨流動性期末預估/);
assert.match(html, /data-liquidity-factor/);

const DATA = {
  status: "ok", generated_at: "2026-08-20T00:00:00Z",
  tga: { actual: [{date:"2026-08-19",value:600000}], forecast: [{date:"2026-08-31",value:650000,change:50000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}] },
  reserves: { actual: [{date:"2026-08-19",value:2800000}], forecast: [{date:"2026-08-31",value:2750000,change:-50000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}] },
  full_liquidity: { actual: [{date:"2026-08-19",value:3850000}], forecast: [{date:"2026-08-31",value:3800000,change:-50000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}] },
  factors: [
    {id:"tga",name:"TGA",forecast:[{date:"2026-08-31",change:50000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}]},
    {id:"walcl",name:"Fed assets",forecast:[{date:"2026-08-31",change:10000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}]},
    {id:"rrp",name:"ON RRP",forecast:[{date:"2026-08-31",change:-10000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}]},
    {id:"currency",name:"Currency",forecast:[{date:"2026-08-31",change:2000,source_type:"model",confidence:"medium",as_of:"2026-08-19"}]},
    {id:"fima_other",name:"FIMA",forecast:[{date:"2026-08-31",change:1000,source_type:"model",confidence:"low",as_of:"2026-08-19"}]},
    {id:"treasury_events",name:"Treasury events",forecast:[]},
  ],
};

let BOX_HTML = "", CAPTURED_OPTION = null, BUTTONS = [];
const chart = {};
const box = {
  set innerHTML(value){
    BOX_HTML = value;
    BUTTONS = [...value.matchAll(/data-liq-win="([^"]+)"/g)].map(match => ({dataset:{liqWin:match[1]},onclick:null}));
  },
  get innerHTML(){ return BOX_HTML; },
  querySelectorAll(selector){ return selector === "[data-liq-win]" ? BUTTONS : []; },
};
const document = { getElementById(id){ return id === "liquidityForecastChart" ? chart : null; } };
const echarts = { getInstanceByDom(){ return null; }, init(){ return {setOption(option){ CAPTURED_OPTION=option; },resize(){}}; } };
const source = `
  const $ = selector => selector === "#liquidityForecastBlock" ? BOX : null;
  const esc = value => String(value == null ? "" : value);
  const updStamp = () => "";
  const window = {echarts:ECH, addEventListener(){}, removeEventListener(){}};
  const document = DOC;
  const echarts = ECH;
  let LIQUIDITY_LEVELS_WIN = "1m";
  let LIQUIDITY_LEVELS = DATA;
  ${extract("_liqFmt")}
  ${extract("_liqChange")}
  ${extract("_liqForecastWindow")}
  ${extract("_liqDirection")}
  ${extract("renderLiquidityForecast")}
  ${extract("drawLiquidityForecast")}
  return {renderLiquidityForecast};
`;
const api = new Function("BOX", "DOC", "ECH", "DATA", source)(box, document, echarts, DATA);
api.renderLiquidityForecast(DATA);

assert.strictEqual((BOX_HTML.match(/data-liquidity-factor=/g) || []).length, 6, "應渲染六張因子卡");
assert.deepStrictEqual(BUTTONS.map(button => button.dataset.liqWin), ["1m","3m","6m"], "應提供 1M／3M／6M 預估範圍");
assert.ok(CAPTURED_OPTION, "應呼叫 ECharts setOption");
assert.strictEqual(CAPTURED_OPTION.series.length, 3, "主圖只應有三條線");
assert.deepStrictEqual(CAPTURED_OPTION.series.map(series => series.name), ["TGA 期末預估","銀行準備金期末預估","完整淨流動性期末預估"]);
assert.ok(CAPTURED_OPTION.series.every(series => series.data.some(point => point.lineStyle && point.lineStyle.type === "dashed")), "預估節點須為虛線");

console.log("✅ test_terminal_liquidity_dom 通過：三線、期末卡、六因子卡與 1M/3M/6M 預估範圍");

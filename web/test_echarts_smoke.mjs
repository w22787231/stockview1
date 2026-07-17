// 真 ECharts SSR 煙霧測試:把 index.html 裡實際的 draw*Chart 函式,用「真 ECharts」
// (與線上同版 5.5.0)在 SSR 模式渲染,任何佈局層錯誤(如多 grid piecewise visualMap
// 觸發的 "reading 'coord'")都會在此當場拋出。stub 版 echarts 抓不到這類錯,故需本測試。
//
// 目前涵蓋 drawTipsChart(TIPS 實質利率 × S&P500,含 20 日相關子圖)、drawYieldCurveChart
// (10 天期殖利率 + 2s10s 子圖)、drawErp(ERP × S&P500 右軸,含反轉視角)、drawSafeHaven
// (Safe Haven Demand × S&P500 右軸,含反轉視角)、drawLevRatioChart(SOXX/QQQ 股價 +
// SOXL/SOXX、QQQ/TQQQ 成交額比值,2 grid 各左右分軸)、drawTwDayTradingChart(台股當沖
// 占大盤比重,單 grid 三線,含早期稀疏/null 資料)、drawSoxxMaChart(SOXX 股價×200MA,
// 2 grid,下圖偏離率含 continuous visualMap 正負上色)。跨多個時間視窗與含 null 暖身的
// 相關序列各渲染一次。要新增其他圖,照 smoke() 模式加即可。
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import assert from "node:assert";

const require = createRequire(import.meta.url);
const echartsReal = require("echarts");   // devDependency;版本對齊 index.html CDN
const html = readFileSync(new URL("index.html", import.meta.url), "utf8");

function extract(name) {
  const s = html.indexOf("function " + name);
  if (s < 0) throw new Error("index.html 缺函式 " + name);
  const o = html.indexOf("{", s);
  let d = 0;
  for (let i = o; i < html.length; i++) {
    if (html[i] === "{") d++;
    else if (html[i] === "}") { d--; if (d === 0) return html.slice(s, i + 1); }
  }
  throw new Error("括號不平衡:" + name);
}

// 用真 ECharts SSR 取代瀏覽器 canvas init:setOption 當下即跑完整佈局(含 markLine/visualMap)
let RENDER_COUNT = 0;
function makeEcharts() {
  return {
    version: echartsReal.version,
    getInstanceByDom() { return null; },
    init() {
      const r = echartsReal.init(null, null, { renderer: "svg", ssr: true, width: 900, height: 380 });
      return {
        setOption(opt) { r.setOption(opt); const svg = r.renderToSVGString(); RENDER_COUNT++; if (!svg || svg.length < 100) throw new Error("SVG 空白"); },
        resize() {}, dispose() { r.dispose(); },
      };
    },
  };
}

// 產生 N 點合成資料:前 warm 個相關值為 null(暖身),模擬真實 corr20
function synth(N, warm) {
  const dates = [], tips = [], sp500 = [], corr = [];
  let base = Date.UTC(2003, 0, 2);
  for (let i = 0; i < N; i++) {
    dates.push(new Date(base + i * 86400000).toISOString().slice(0, 10));
    tips.push(+(1.6 + 1.1 * Math.sin(i / 200)).toFixed(3));
    sp500.push(+(1000 + i * 0.9).toFixed(2));
    corr.push(i < warm ? null : +(-0.35 + 0.55 * Math.sin(i / 30)).toFixed(3));
  }
  return { dates, tips, sp500, corr };
}

function smokeTips(label, N, warm, win, invert) {
  const echarts = makeEcharts();
  const window = { echarts, addEventListener() {}, removeEventListener() {} };
  const el = {};
  const $ = () => el;
  const drawTipsChart = new Function(
    "return (function($, window, echarts){ let TIPS_INV=" + (!!invert) + "; " + extract("drawTipsChart") + " return drawTipsChart; })"
  )()($, window, echarts);
  const d = synth(N, warm);
  try {
    drawTipsChart("tipsChart", d.dates, d.tips, d.sp500, d.corr, win);
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}

console.log("真 ECharts SSR 煙霧測試(drawTipsChart):");
smokeTips("1y 視窗(252點)", 252, 20, "1y", false);
smokeTips("3m 視窗(63點,含null暖身)", 63, 20, "3m", false);
smokeTips("max 視窗(5800點)", 5800, 20, "max", false);
smokeTips("極短(僅25點,corr幾乎全null)", 25, 20, "1y", false);
smokeTips("反轉視角(-TIPS)", 252, 20, "1y", true);

// ── drawYieldCurveChart(10 天期多線 + 2s10s 子圖,多 grid + visualMap + markLine)──
function synthYc(N) {
  const KEYS = ["3m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y"];
  const dates = [], yields = {}, spread = [];
  let base = Date.UTC(2006, 0, 2);
  KEYS.forEach(k => yields[k] = []);
  for (let i = 0; i < N; i++) {
    dates.push(new Date(base + i * 86400000).toISOString().slice(0, 10));
    KEYS.forEach((k, ki) => yields[k].push(+(1.0 + ki * 0.25 + 0.8 * Math.sin(i / 120)).toFixed(2)));
    spread.push(+(yields["10y"][i] - yields["2y"][i]).toFixed(2));   // 含負值(倒掛)
  }
  const mats = KEYS.map(k => ({ key: k, label: k.toUpperCase() }));
  return { dates, yields, mats, spread };
}
function smokeYc(label, N) {
  const echarts = makeEcharts();
  const window = { echarts, addEventListener() {}, removeEventListener() {} };
  const el = {};
  const $ = () => el;
  // drawYieldCurveChart 依賴函式外的 YC_COLORS 常數,一併從 index.html 抽出注入(保持同步)
  const ycColors = (html.match(/const\s+YC_COLORS\s*=\s*\[[^\]]*\]/) || ["const YC_COLORS=[]"])[0];
  const draw = new Function(
    "return (function($, window, echarts){ " + ycColors + "; " + extract("drawYieldCurveChart") + " return drawYieldCurveChart; })"
  )()($, window, echarts);
  const d = synthYc(N);
  try {
    draw("yieldCurveChart", d.dates, d.yields, d.mats, d.spread);
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawYieldCurveChart):");
smokeYc("5y 視窗(1260點,10線+利差子圖)", 1260);
smokeYc("max 視窗(5000點)", 5000);

// ── drawErp / _renderErp(ERP 線 + S&P500 右軸疊圖,含反轉視角 ERP_INV)──
function synthErp(N){
  const dates=[], erp=[], spy=[];
  let base=Date.UTC(2019,3,26);
  for(let i=0;i<N;i++){
    dates.push(new Date(base+i*7*86400000).toISOString().slice(0,10));   // 週頻
    erp.push(+(0.2+3.0*Math.sin(i/40)).toFixed(2));
    spy.push(+(3000+i*3.2).toFixed(2));
  }
  return {cur:erp[erp.length-1], fwd_pe:21.1, dgs10:4.54, pctile:7, dates, erp, spy};
}
function smokeErp(label, N, invert){
  const echarts = makeEcharts();
  const chartEl={}, rangeEl={querySelectorAll:()=>[]}, invEl={};
  const window = { echarts, addEventListener(){}, removeEventListener(){} };
  const document = { getElementById(id){
    if(id==="erpChart") return chartEl;
    if(id==="erpRange") return rangeEl;
    if(id==="erpInvBtn") return invEl;
    return null;
  }};
  const drawErp = new Function(
    "return (function(document, window, echarts){ let ERP_RANGE='all'; let ERP_INV=" + (!!invert) + "; "
    + extract("drawErp") + " " + extract("_renderErp") + " return drawErp; })"
  )()(document, window, echarts);
  try {
    drawErp(synthErp(N));
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawErp):");
smokeErp("3y 視窗(156點,含S&P500右軸)", 156, false);
smokeErp("反轉視角(-ERP)", 156, true);
smokeErp("ALL 視窗(363點)", 363, false);

// ── drawSafeHaven / _renderSafeHaven(Safe Haven Demand 線 + S&P500 右軸,含反轉視角 SH_INV)──
function synthSafeHaven(N){
  const dates=[], y=[], sp500=[];
  let base=Date.UTC(2025,7,1);
  for(let i=0;i<N;i++){
    dates.push(new Date(base+i*86400000).toISOString().slice(0,10));
    y.push(+(1.5*Math.sin(i/20)).toFixed(2));
    sp500.push(+(6000+i*1.5).toFixed(2));
  }
  return {cur:y[y.length-1], pctile:74, dates, y, sp500};
}
function smokeSafeHaven(label, N, invert, range){
  const echarts = makeEcharts();
  const chartEl={}, invEl={}, rangeEl={querySelectorAll:()=>[]};
  const window = { echarts, addEventListener(){}, removeEventListener(){} };
  const document = { getElementById(id){
    if(id==="shChart") return chartEl;
    if(id==="shInvBtn") return invEl;
    if(id==="shRange") return rangeEl;
    return null;
  }};
  const drawSafeHaven = new Function(
    "return (function(document, window, echarts){ let SH_INV=" + (!!invert) + "; "
    + "let SH_RANGE='" + (range || "all") + "'; "
    + "const SH_WINS=[['1m',21,'1M'],['3m',63,'3M'],['6m',126,'6M'],['all',Infinity,'ALL']]; "
    + extract("drawSafeHaven") + " " + extract("_renderSafeHaven") + " return drawSafeHaven; })"
  )()(document, window, echarts);
  try {
    drawSafeHaven(synthSafeHaven(N));
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawSafeHaven):");
smokeSafeHaven("250點(近1年,含S&P500右軸)", 250, false);
smokeSafeHaven("反轉視角(-y)", 250, true);
smokeSafeHaven("1M 視窗(21點)", 250, false, "1m");

// ── drawLevRatioChart(SOXX/QQQ 股價 + SOXL/SOXX、QQQ/TQQQ 成交額比值,2 grid 各左右分軸)──
function synthLev(N){
  const dates=[], soxxPrice=[], ratio1=[], qqqPrice=[], ratio2=[];
  let base=Date.UTC(2010,2,11);
  for(let i=0;i<N;i++){
    dates.push(new Date(base+i*86400000).toISOString().slice(0,10));
    soxxPrice.push(+(60+40*Math.sin(i/200)+i*0.05).toFixed(2));
    ratio1.push(+(2.0+1.2*Math.sin(i/90)).toFixed(3));
    qqqPrice.push(+(100+i*0.08+30*Math.sin(i/150)).toFixed(2));
    ratio2.push(+(5.0+2.0*Math.sin(i/70)).toFixed(3));
  }
  return {dates, soxxPrice, ratio1, qqqPrice, ratio2};
}
function smokeLevRatio(label, N, win){
  const echarts = makeEcharts();
  const window = { echarts, addEventListener(){}, removeEventListener(){} };
  const el = {};
  const $ = () => el;
  const drawLevRatioChart = new Function(
    "return (function($, window, echarts){ " + extract("drawLevRatioChart") + " return drawLevRatioChart; })"
  )()($, window, echarts);
  const d = synthLev(N);
  try {
    drawLevRatioChart("levRatioChart", d.dates, d.soxxPrice, d.ratio1, d.qqqPrice, d.ratio2, win);
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawLevRatioChart):");
smokeLevRatio("1y 視窗(252點)", 252, "1y");
smokeLevRatio("max 視窗(4112點,16年)", 4112, "max");
smokeLevRatio("3m 視窗(63點)", 63, "3m");

// ── drawTwDayTradingChart(台股當沖占大盤比重,單 grid 三線,早期資料點稀疏含 null)──
function synthTwDt(N, sparse){
  const dates=[], qtyPct=[], buyPct=[], sellPct=[];
  let base=Date.UTC(2026,6,17);
  for(let i=0;i<N;i++){
    dates.push(new Date(base+i*86400000).toISOString().slice(0,10));
    qtyPct.push(+(25+8*Math.sin(i/15)).toFixed(2));
    if(sparse && i%3!==0){ buyPct.push(null); sellPct.push(null); }
    else{
      buyPct.push(+(35+10*Math.sin(i/15+0.3)).toFixed(2));
      sellPct.push(+(35+10*Math.sin(i/15-0.3)).toFixed(2));
    }
  }
  return {dates, qtyPct, buyPct, sellPct};
}
function smokeTwDt(label, N, sparse){
  const echarts = makeEcharts();
  const window = { echarts, addEventListener(){}, removeEventListener(){} };
  const el = {};
  const $ = () => el;
  const drawTwDayTradingChart = new Function(
    "return (function($, window, echarts){ " + extract("drawTwDayTradingChart") + " return drawTwDayTradingChart; })"
  )()($, window, echarts);
  const d = synthTwDt(N, sparse);
  try {
    drawTwDayTradingChart("twDayTradingChart", d.dates, d.qtyPct, d.buyPct, d.sellPct);
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawTwDayTradingChart):");
smokeTwDt("極短(僅4點,剛上線第一天)", 4, false);
smokeTwDt("稀疏(60點,buy/sell含null回填天)", 60, true);
smokeTwDt("1y 視窗(252點)", 252, false);

// ── drawSoxxMaChart(SOXX 股價 × 200MA,2 grid:上圖股價共軸,下圖偏離率含正負piecewise視覺映射)──
function synthSoxxMa(N){
  const dates=[], close=[], ma200=[], dev=[];
  let base=Date.UTC(2002,4,3);
  for(let i=0;i<N;i++){
    dates.push(new Date(base+i*86400000).toISOString().slice(0,10));
    const c = 100+80*Math.sin(i/300)+i*0.03;
    const m = 100+70*Math.sin((i-100)/300)+i*0.03;
    close.push(+c.toFixed(2));
    ma200.push(+m.toFixed(2));
    dev.push(+((c/m-1)*100).toFixed(2));
  }
  return {dates, close, ma200, dev};
}
function smokeSoxxMa(label, N){
  const echarts = makeEcharts();
  const window = { echarts, addEventListener(){}, removeEventListener(){} };
  const el = {};
  const $ = () => el;
  const drawSoxxMaChart = new Function(
    "return (function($, window, echarts){ " + extract("drawSoxxMaChart") + " return drawSoxxMaChart; })"
  )()($, window, echarts);
  const d = synthSoxxMa(N);
  try {
    drawSoxxMaChart("soxxMaChart", d.dates, d.close, d.ma200, d.dev);
    console.log(`  ${label}: ✅ 真 ECharts ${echarts.version} 渲染成功`);
  } catch (e) {
    console.log(`  ${label}: ❌ ${e.message}`);
    throw e;
  }
}
console.log("真 ECharts SSR 煙霧測試(drawSoxxMaChart):");
smokeSoxxMa("1y 視窗(252點)", 252);
smokeSoxxMa("max 視窗(6089點,24年)", 6089);
smokeSoxxMa("極短(僅3點)", 3);

assert.ok(RENDER_COUNT >= 22, "應完成至少 22 次真渲染,實得 " + RENDER_COUNT);
console.log(`✅ test_echarts_smoke 通過:${RENDER_COUNT} 次真 ECharts 渲染皆無崩潰`);
// ECharts SSR 實例會佔住 node 事件迴圈,明確結束避免測試掛住(CI/npm test 會逾時)
process.exit(0);

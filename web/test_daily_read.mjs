import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
const startMarker = "// ── 每日市場判讀 ──";
const endMarker = "// ── 宏觀評分總攬";
const start = html.indexOf(startMarker);
const end = html.indexOf(endMarker);

assert.ok(start >= 0, "缺每日市場判讀的純函式區塊");
assert.ok(end > start, "每日市場判讀區塊必須位於宏觀評分前");

const source = html.slice(start, end);
let boxHtml = "";
const box = { set innerHTML(value){ boxHtml=value; }, get innerHTML(){ return boxHtml; } };
const api = new Function("const $ = () => BOX; const esc = value => String(value == null ? '' : value); const loadLiquidityForecast = () => {}; const BOX = arguments[0];\n" + source + "\nreturn { buildDailyRead, renderDailyRead };")(box);

const riskInputs = {
  score: { items: [
    { name: "10年 TIPS 實質利率", score: 10, status: "實質利率高" },
    { name: "美債殖利率曲線 2s10s", score: 25, status: "偏平坦" },
    { name: "HYG 高收益債", score: 15, status: "信用壓力升溫" },
    { name: "金融壓力指數 FSI", score: 20, status: "壓力升高" },
    { name: "VIX 波動率", score: 20, status: "波動升高" },
    { name: "市場廣度(SP500)", score: 20, status: "廣度轉弱" },
  ]},
  macro: { indices: [
    { label: "美元指數", last: 101, chg: 0.6 },
    { label: "黃金", last: 2400, chg: 1.2 },
  ]},
  themeFlow: { groups: [
    { theme: "防禦", avg: { r1: 1.4, r5: 2.1, r20: 3.2 } },
    { theme: "半導體", avg: { r1: -2.2, r5: -4.1, r20: -6.5 } },
  ]},
};

const rotationInputs = {
  score: { items: [
    { name: "10年 TIPS 實質利率", score: 50, status: "中性" },
    { name: "美債殖利率曲線 2s10s", score: 50, status: "中性" },
    { name: "HYG 高收益債", score: 70, status: "信用穩定" },
    { name: "金融壓力指數 FSI", score: 65, status: "壓力低" },
    { name: "VIX 波動率", score: 55, status: "平靜" },
    { name: "市場廣度(SP500)", score: 65, status: "廣度健康" },
  ]},
  macro: { indices: [
    { label: "美元指數", last: 100, chg: 0.1 },
    { label: "黃金", last: 2300, chg: -0.1 },
  ]},
  themeFlow: { groups: [
    { theme: "能源", avg: { r1: 1.9, r5: 4.2, r20: 8.1 } },
    { theme: "AI雲端", avg: { r1: -1.7, r5: -3.4, r20: -7.5 } },
  ]},
  checklist: { groups: [
    { title: "估值壓力", rows: [
      { label: "10Y TIPS", available: true, last: 2.1, unit: "%", change_unit: "bps", changes: { today: 12 }, level: "高 98%", signal: "↑ 加速", note: "高位再升，壓制估值", score: -2, source: "FRED" },
      { label: "殖利率曲線", available: true, last: -0.3, unit: "%", change_unit: "bps", changes: { today: -8 }, level: "低 20%", signal: "↓ 惡化", note: "曲線倒掛加深", score: 2, source: "FRED" },
      { label: "高收益債", available: true, last: 0.4, unit: "%", change_unit: "bps", changes: { today: -3 }, level: "中 50%", signal: "↑ 改善", note: "信用利差收斂", score: 1, source: "FRED" },
      { label: "波動率", available: true, last: 18, unit: "", change_unit: "pt", changes: { today: 1.2 }, level: "高 80%", signal: "↑ 升溫", note: "波動壓力增加", score: -1, source: "CBOE" },
    ]},
  ]},
};

const risk = api.buildDailyRead(riskInputs);
assert.equal(risk.theme, "風險撤退", "信用、情緒、股票內部同時轉弱應判為風險撤退");
assert.ok(risk.falsifiers.length > 0, "風險撤退必須提供可驗證的推翻訊號");

const rotation = api.buildDailyRead(rotationInputs);
assert.equal(rotation.theme, "板塊輪動", "內部健康但產業漲跌分化應判為板塊輪動");
assert.equal(rotation.modules.length, 6, "檢查表必須固定六項");
assert.ok(rotation.confidence.available >= 5, "有資料的模組必須納入確信度分母");
assert.equal(rotation.evidenceTotal, 4, "四筆量化列都應計入旁證總數");
assert.deepEqual(rotation.evidence.map(row => row.label), ["10Y TIPS", "殖利率曲線", "高收益債"], "旁證只取絕對分數最高三筆，絕對分數同分時維持原始列順序");
assert.deepEqual(rotation.evidence.map(row => [row.changes.today, row.change_unit]), [[12, "bps"], [-8, "bps"], [-3, "bps"]], "旁證必須保留今日變動與單位");

const empty = api.buildDailyRead({});
assert.equal(empty.modules.filter(m => !m.available).length, 6, "缺資料時不得虛構任何訊號");
assert.equal(empty.confidence.available, 0, "缺資料不得計入確信度");

console.log("✅ test_daily_read 通過：分類、推翻訊號、六項固定列與缺資料容錯");

assert.ok(html.includes('data-mtab="dailyread"'), "缺每日判讀分頁按鈕");
assert.ok(html.includes('id="dailyReadBlock"'), "缺每日判讀容器");
assert.ok(html.includes('Promise.allSettled'), "每日判讀應容忍個別資料檔失敗");
assert.ok(html.includes("'daily_checklist'"), "每日判讀應載入 daily_checklist.json");
assert.ok(html.includes('daily-checklist-table'), "每日判讀應渲染可掃讀的資料表");
assert.ok(html.includes('daily-chart-rates'), "每日判讀應有利率結構圖容器");
assert.ok(html.includes('daily-chart-risk'), "每日判讀應有波動與信用壓力圖容器");
assert.ok(html.includes('daily-chart-internals'), "每日判讀應有股票內部圖容器");
assert.ok(html.includes('daily-chart-credit'), "每日判讀應有信用結構圖容器");
assert.ok(html.includes('daily-chart-bitcoin-gold'), "每日判讀應有比特幣與黃金圖容器");
assert.ok(html.includes('比特幣 × 黃金'), "每日判讀應標示比特幣與黃金圖表");
assert.ok(html.includes('IG 指數殖利率、10Y 美債殖利率、HY 指數殖利率'), "信用結構圖必須標示殖利率三條線");
assert.ok(html.includes('IG 利差（OAS）、BBB 利差（OAS）、HY 利差（OAS）'), "信用結構圖必須標示 OAS 三條線");
assert.ok(html.includes('data-daily-chart-range'), "每日判讀的圖表必須提供時間範圍按鈕");
assert.ok(html.includes('1M') && html.includes('3M') && html.includes('6M') && html.includes('1Y') && html.includes('3Y') && html.includes('5Y') && html.includes('ALL'), "圖表時間按鈕必須包含 1M/3M/6M/1Y/3Y/5Y/ALL");
assert.ok(html.includes('<th>水平</th>'), "量化表應顯示歷史水平欄位");
assert.ok(html.includes('<th>判讀結論</th>'), "量化表應顯示獨立判讀結論欄位");
assert.ok(html.includes('<th>註記</th>'), "量化表應顯示白話註記欄位");
assert.ok(!html.includes('市場總分'), "頁面不得顯示市場總分");

api.renderDailyRead(rotation);
assert.ok(boxHtml.includes("市場主題"), "缺市場主題列");
assert.ok(boxHtml.includes("推翻訊號"), "缺推翻訊號");
assert.equal((boxHtml.match(/data-daily-module=/g)||[]).length, 6, "應固定渲染六項檢查表");
assert.ok(boxHtml.includes("高 98%"), "量化表應渲染水平");
assert.ok(boxHtml.includes("↑ 加速"), "量化表應渲染判讀結論");
assert.ok(boxHtml.includes("高位再升，壓制估值"), "量化表應渲染註記");
assert.ok(boxHtml.includes("旁證 3/4"), "頁首應顯示已取前三筆與完整旁證數");
assert.ok(boxHtml.includes("10Y TIPS：↑ 加速（+12.0bp）"), "今日主角旁證應同時渲染變動與判讀結論");

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
const api = new Function(source + "\nreturn { buildDailyRead };")();

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
};

const risk = api.buildDailyRead(riskInputs);
assert.equal(risk.theme, "風險撤退", "信用、情緒、股票內部同時轉弱應判為風險撤退");
assert.ok(risk.falsifiers.length > 0, "風險撤退必須提供可驗證的推翻訊號");

const rotation = api.buildDailyRead(rotationInputs);
assert.equal(rotation.theme, "板塊輪動", "內部健康但產業漲跌分化應判為板塊輪動");
assert.equal(rotation.modules.length, 6, "檢查表必須固定六項");
assert.ok(rotation.confidence.available >= 5, "有資料的模組必須納入確信度分母");

const empty = api.buildDailyRead({});
assert.equal(empty.modules.filter(m => !m.available).length, 6, "缺資料時不得虛構任何訊號");
assert.equal(empty.confidence.available, 0, "缺資料不得計入確信度");

console.log("✅ test_daily_read 通過：分類、推翻訊號、六項固定列與缺資料容錯");

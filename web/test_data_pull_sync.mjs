// 守門測試:前端 index.html 會 fetch 的每個 data/*.json,都必須能在 web_only 部署中取得,
// 也就是必須在 engine/pull_live_data.py 的拉取範圍內(TOP 清單或腳本內 /data/*.json),
// 或是版控內既有的靜態檔。否則 web_only(純前端)部署會掉檔 → 前端顯示「尚未產生」。
//
// 這條測試會擋住「加了新資料圖、卻忘了把檔名加進 pull_live_data.py」這類同步漏失
// (本專案曾因 tips.json 未列入而在 web_only 部署後 404)。
import { readFileSync } from "node:fs";
import assert from "node:assert";

const here = new URL(".", import.meta.url);
const indexHtml = readFileSync(new URL("index.html", here), "utf8");
const pullPy = readFileSync(new URL("../engine/pull_live_data.py", here), "utf8");

// 1) 前端實際會抓的 data/*.json(去重)
const fetched = [...new Set(
  [...indexHtml.matchAll(/["'`]data\/([a-z0-9_]+)\.json/gi)].map(m => m[1])
)].sort();

// 2) pull_live_data.py 涵蓋的檔名:TOP 陣列 + 腳本內任何 /data/<name>.json
const topBlock = (pullPy.match(/TOP\s*=\s*\[([\s\S]*?)\]/) || [])[1] || "";
const topNames = [...topBlock.matchAll(/["']([a-z0-9_]+)["']/gi)].map(m => m[1]);
const inlinePaths = [...pullPy.matchAll(/\/data\/([a-z0-9_]+)\.json/gi)].map(m => m[1]);

// 3) 版控內既有的靜態資料檔(不經由 pull 產生/拉取;見 .gitignore 的 ! 例外)
const COMMITTED = ["supply_chain", "valuations"];

const covered = new Set([...topNames, ...inlinePaths, ...COMMITTED]);

const missing = fetched.filter(n => !covered.has(n));

console.log(`前端 fetch 的 data/*.json:${fetched.length} 個`);
console.log(`pull_live_data 涵蓋:${topNames.length} (TOP) + ${inlinePaths.length} (內嵌) + ${COMMITTED.length} (版控)`);
if (missing.length) {
  console.log("❌ 下列前端會抓、但 web_only 部署不會提供(不在 pull_live_data 也非版控靜態檔):");
  missing.forEach(n => console.log("   - data/" + n + ".json"));
  console.log("   → 請把檔名加進 engine/pull_live_data.py 的 TOP 清單。");
}
assert.strictEqual(missing.length, 0,
  "有前端會抓卻不會被 web_only 部署提供的資料檔:" + missing.join(", "));

// 反向健檢:tips 必須同時在前端與 pull 清單(本次回歸的具體案例)
assert.ok(fetched.includes("tips"), "index.html 應 fetch data/tips.json");
assert.ok(covered.has("tips"), "pull_live_data.py 應涵蓋 tips(否則 web_only 部署會掉 tips.json)");

console.log("✅ test_data_pull_sync 通過:前端所有 data/*.json 都在 web_only 部署範圍內");

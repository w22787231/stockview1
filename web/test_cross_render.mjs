// 前端交叉訊號純函式測試。執行：cd web && node test_cross_render.mjs
// 從 index.html 抽出兩個純函式來測（以「數大括號」找出函式完整本體，避免被巢狀 } 截斷）。
import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");

function extract(name) {
  const start = html.indexOf("function " + name);
  if (start < 0) throw new Error("找不到函式 " + name);
  const open = html.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") { depth--; if (depth === 0) return html.slice(start, i + 1); }
  }
  throw new Error("函式 " + name + " 大括號不平衡");
}

// 把純函式載進來
const src = extract("sortCrossRows") + "\n" + extract("freshCrosses");
const mod = new Function(src + "\nreturn { sortCrossRows, freshCrosses };")();
const { sortCrossRows, freshCrosses } = mod;

function row(sym, state, days, score) {
  return { sym, cross_state: state, cross_days: days, score };
}

// sortCrossRows: 天數小→前、None→墊底、同天數 score 大→前
{
  const rows = [row("OLD","golden",40,9), row("NEW","golden",1,1),
                row("NEVER","golden",null,5), row("HI","golden",10,8),
                row("LO","golden",10,2)];
  const out = sortCrossRows(rows).map(r => r.sym);
  assert.deepStrictEqual(out, ["NEW","HI","LO","OLD","NEVER"], JSON.stringify(out));
  console.log("PASS sortCrossRows");
}

// freshCrosses: 合併 golden+death，取 cross_days<=fresh_days(非 null)，排序
{
  const cs = {
    fresh_days: 3,
    golden: [row("G1","golden",1,5), row("G2","golden",10,5)],
    death:  [row("D1","death",2,5),  row("D2","death",null,5)],
  };
  const fresh = freshCrosses(cs).map(r => r.sym);
  assert.deepStrictEqual(fresh, ["G1","D1"], JSON.stringify(fresh));
  console.log("PASS freshCrosses");
}

// freshCrosses: 空輸入安全
{
  assert.deepStrictEqual(freshCrosses({fresh_days:3,golden:[],death:[]}), []);
  assert.deepStrictEqual(freshCrosses(null), []);
  console.log("PASS freshCrosses empty");
}

console.log("\nAll front-end pure-fn tests passed");

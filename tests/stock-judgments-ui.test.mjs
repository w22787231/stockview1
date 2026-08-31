import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(here, "..", "web", "index.html"), "utf8");
const source = fs.readFileSync(path.join(here, "..", "web", "stock-judgments.js"), "utf8");
const context = vm.createContext({ window: {} });
vm.runInContext(source, context);
const { liquidityJudgment, valuationJudgment } = context.window.StockJudgments;

test("individual-stock view includes explainable liquidity and valuation judgments", () => {
  assert.match(html, /stock-judgments\.js/);
  assert.match(html, /流動性判斷/);
  assert.match(html, /估值判斷/);
});

test("liquidity judgment distinguishes an actively traded stock from a thin one", () => {
  const active = Array.from({ length: 40 }, () => ({ c: 100, v: 200_000 }));
  const thin = Array.from({ length: 40 }, (_, index) => ({ c: 10, v: index < 20 ? 10_000 : 1_000 }));
  assert.equal(liquidityJudgment(active).label, "流動性佳");
  assert.equal(liquidityJudgment(thin).label, "流動性風險高");
});

test("valuation judgment balances price multiples with growth and profitability", () => {
  assert.equal(valuationJudgment({ pe: 12, forwardPe: 16, peg: 1, rev_growth: 0.2, roe: 0.18 }).label, "相對偏低");
  assert.equal(valuationJudgment({ pe: 50, forwardPe: 45, peg: 3, rev_growth: -0.1, roe: 0.03 }).label, "相對偏高");
});

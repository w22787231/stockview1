import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(here, "..", "web", "index.html"), "utf8");

test("news cards render summary, importance and merged-source fields", () => {
  assert.match(html, /it\.summary_zh/);
  assert.match(html, /it\.why_zh/);
  assert.match(html, /it\.sources/);
  assert.match(html, /另有/);
});

test("news cards keep the existing fallback title behavior", () => {
  assert.match(html, /it\.title_zh\s*\|\|\s*it\.title/);
});

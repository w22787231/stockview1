import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const workerPath = path.join(here, "..", "web", "_worker.js");
const source = fs.readFileSync(workerPath, "utf8")
  .replace("export default {", "globalThis.__worker = {")
  + "\nglobalThis.__newsTest = { normalizeNewsUrl, ruleDedupe, semanticDedupe, enrichNewsItems };\n";

const context = vm.createContext({
  console,
  URL,
  Request,
  Response,
  AbortController,
  setTimeout,
  clearTimeout,
  caches: { default: { match: async () => null, put: async () => {} } },
});
vm.runInContext(source, context, { filename: workerPath });
const { normalizeNewsUrl, ruleDedupe, semanticDedupe, enrichNewsItems } = context.__newsTest;

test("normalizes tracking parameters before URL deduplication", () => {
  assert.equal(
    normalizeNewsUrl("https://example.com/story?utm_source=x&id=7&fbclid=abc"),
    "https://example.com/story?id=7",
  );
});

test("rule dedupe merges duplicate URLs and keeps newest representative", () => {
  const items = [
    { title: "AI chip demand jumps", link: "https://example.com/a?utm_source=rss", src: "Yahoo Finance", ts: 100, description: "Older" },
    { title: "AI chip demand jumps!", link: "https://example.com/a", src: "CNBC Tech", ts: 200, description: "Newer" },
  ];
  const result = ruleDedupe(items);
  assert.equal(result.length, 1);
  assert.equal(result[0].src, "CNBC Tech");
  assert.deepEqual(JSON.parse(JSON.stringify(result[0].sources)), [
    { src: "Yahoo Finance", link: "https://example.com/a?utm_source=rss" },
  ]);
});

test("semantic dedupe merges model clusters and preserves unrelated events", async () => {
  const items = [
    { title: "OpenAI launches a new coding model", link: "https://cnbc.com/1", src: "CNBC Tech", ts: 300, description: "Launch details", sources: [] },
    { title: "New OpenAI model targets software developers", link: "https://finance.yahoo.com/2", src: "Yahoo Finance", ts: 200, description: "Developer model", sources: [] },
    { title: "Nvidia opens a new factory", link: "https://cnbc.com/3", src: "CNBC", ts: 100, description: "Factory news", sources: [] },
  ];
  const env = { AI: { run: async () => ({ response: JSON.stringify({ groups: [[0, 1], [2]] }) }) } };
  const result = await semanticDedupe(items, env);
  assert.equal(result.length, 2);
  assert.equal(result[0].title, items[0].title);
  assert.equal(result[0].sources.length, 1);
  assert.equal(result[1].title, items[2].title);
});

test("semantic dedupe falls back unchanged when AI output is invalid", async () => {
  const items = [
    { title: "A", link: "https://example.com/a", src: "CNBC", ts: 2, description: "", sources: [] },
    { title: "B", link: "https://example.com/b", src: "Yahoo Finance", ts: 1, description: "", sources: [] },
  ];
  const env = { AI: { run: async () => ({ response: "not json" }) } };
  assert.deepEqual(await semanticDedupe(items, env), items);
});

test("enrichment returns aligned Traditional Chinese fields and caps input at 15", async () => {
  const items = Array.from({ length: 20 }, (_, i) => ({
    title: `Story ${i}`,
    link: `https://example.com/${i}`,
    src: "CNBC",
    ts: 20 - i,
    description: "Detail",
    sources: [],
  }));
  let received = 0;
  const env = { AI: { run: async (_model, payload) => {
    const input = JSON.parse(payload.messages[1].content);
    received = input.length;
    return { response: JSON.stringify(input.map((_, i) => ({
      title_zh: `標題${i}`,
      summary_zh: `第一句。第二句。`,
      why_zh: `為何重要：影響${i}`,
    }))) };
  } } };
  const result = await enrichNewsItems(items, env);
  assert.equal(received, 15);
  assert.equal(result.length, 15);
  assert.equal(result[0].title_zh, "標題0");
  assert.equal(result[0].summary_zh, "第一句。第二句。");
  assert.equal(result[0].why_zh, "為何重要：影響0");
});

test("enrichment degrades to original items when AI is unavailable", async () => {
  const items = [{ title: "English", link: "https://example.com", src: "CNBC", ts: 1, description: "Detail", sources: [] }];
  const result = await enrichNewsItems(items, {});
  assert.equal(result.length, 1);
  assert.equal(result[0].title, "English");
  assert.equal(result[0].title_zh, undefined);
});

test("news endpoint returns 15 deduped items without AI and hides raw descriptions", async () => {
  const rssItems = Array.from({ length: 20 }, (_, i) => `
    <item>
      <title>Unique story ${i}</title>
      <link>https://example.com/story-${i}?utm_source=rss</link>
      <description>Untrusted raw detail ${i}</description>
      <pubDate>${new Date(Date.UTC(2026, 6, 11, 20 - i)).toUTCString()}</pubDate>
    </item>`).join("");
  context.fetch = async () => new Response(`<rss><channel>${rssItems}</channel></rss>`, { status: 200 });
  const response = await context.__worker.fetch(new Request("https://stockview.test/api/news?feed=tech"), {});
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.count, 15);
  assert.equal(body.items.length, 15);
  assert.equal(body.items[0].description, undefined);
});

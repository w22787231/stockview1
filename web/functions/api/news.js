// Cloudflare Pages Function: GET /api/news?feed=tw|world|tech|finance
// 邊緣端代理 RSS(避開 CORS),合併、去重、依時間排序回 JSON。邊緣快取 120 秒。
//   tw      = 台股中文(鉅亨/Yahoo股市/Google News台股)
//   world   = 🌍 國際大事(Google News WORLD)
//   tech    = 💻 科技/AI(Google News TECHNOLOGY + AI 搜尋)
//   finance = 💰 財經/市場(Google News BUSINESS + Yahoo Finance + CNBC)

const GNT = (t) => `https://news.google.com/rss/headlines/section/topic/${t}?hl=en-US&gl=US&ceid=US:en`;
const GNS = (q) => `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;

const GROUPS = {
  tw: [
    { url: "https://news.cnyes.com/rss/v1/news/category/tw_stock", src: "鉅亨·台股" },
    { url: "https://news.cnyes.com/rss/v1/news/category/headline", src: "鉅亨·頭條" },
    { url: "https://tw.stock.yahoo.com/rss?category=news", src: "Yahoo股市" },
    { url: "https://news.google.com/rss/search?q=%E5%8F%B0%E8%82%A1+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", src: "" },
  ],
  world: [
    { url: GNT("WORLD"), src: "" },
  ],
  tech: [
    { url: GNT("TECHNOLOGY"), src: "" },
    { url: GNS("artificial+intelligence+OR+AI+OR+semiconductor+OR+chip+when:1d"), src: "" },
  ],
  finance: [
    { url: GNT("BUSINESS"), src: "" },
    { url: "https://finance.yahoo.com/news/rssindex", src: "Yahoo Finance" },
    { url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", src: "CNBC" },
  ],
};

function pick(block, tag) {
  const m = block.match(new RegExp("<" + tag + "[^>]*>([\\s\\S]*?)</" + tag + ">", "i"));
  if (!m) return "";
  return m[1].replace(/<!\[CDATA\[/g, "").replace(/\]\]>/g, "").trim();
}
function decode(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&#160;/g, " ")
          .replace(/&amp;/g, "&");
}
function stripTags(s) { return s.replace(/<[^>]+>/g, "").trim(); }

async function fetchFeed(feed) {
  try {
    const r = await fetch(feed.url, {
      headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml,application/xml,text/xml,*/*" },
      cf: { cacheTtl: 120, cacheEverything: true },
    });
    if (!r.ok) return [];
    const xml = await r.text();
    const chunks = xml.split(/<item[ >]/).slice(1);
    const out = [];
    for (const block of chunks.slice(0, 40)) {
      let title = decode(stripTags(pick(block, "title")));
      let link = stripTags(pick(block, "link"));
      if (!link) { const lm = block.match(/<link[^>]*href="([^"]+)"/i); if (lm) link = lm[1]; }
      const pub = pick(block, "pubDate") || pick(block, "published") || pick(block, "updated");
      let src = feed.src || decode(stripTags(pick(block, "source")));
      if (!feed.src) {                       // Google News 標題常是「標題 - 來源」
        const dash = title.lastIndexOf(" - ");
        if (dash > 0) { if (!src) src = title.slice(dash + 3); title = title.slice(0, dash); }
      }
      const ts = pub ? Date.parse(pub) : 0;
      if (title && link) out.push({ title, link, src: src || "新聞", ts: isNaN(ts) ? 0 : ts });
    }
    return out;
  } catch (e) { return []; }
}

export async function onRequestGet(context) {
  const feedKey = new URL(context.request.url).searchParams.get("feed") || "tw";
  const feeds = GROUPS[feedKey] || GROUPS.tw;
  const lists = await Promise.all(feeds.map(fetchFeed));
  const all = [].concat(...lists);
  const seen = new Set(), uniq = [];
  for (const it of all) {
    const k = it.title.replace(/\s+/g, "").slice(0, 40).toLowerCase();
    if (!k || seen.has(k)) continue;
    seen.add(k); uniq.push(it);
  }
  uniq.sort((a, b) => b.ts - a.ts);
  const items = uniq.slice(0, 50).map(it => ({
    title: it.title, link: it.link, src: it.src,
    time: it.ts ? new Date(it.ts).toISOString() : null,
  }));
  const body = JSON.stringify({ feed: feedKey, generated_at: new Date().toISOString(), count: items.length, items });
  return new Response(body, {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=120",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

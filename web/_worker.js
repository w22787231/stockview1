// Cloudflare Pages 進階模式 Worker:/api/news 動態代理 RSS,其餘走靜態資產。
// (functions/ 目錄在 wrangler pages deploy 下未被編譯,故改用 _worker.js,必被識別。)

const GNT = (t) => `https://news.google.com/rss/headlines/section/topic/${t}?hl=en-US&gl=US&ceid=US:en`;
const GNS = (q) => `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;

const GROUPS = {
  tw: [
    { url: "https://news.cnyes.com/rss/v1/news/category/tw_stock", src: "鉅亨·台股" },
    { url: "https://news.cnyes.com/rss/v1/news/category/headline", src: "鉅亨·頭條" },
    { url: "https://tw.stock.yahoo.com/rss?category=news", src: "Yahoo股市" },
    { url: "https://news.google.com/rss/search?q=%E5%8F%B0%E8%82%A1+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", src: "" },
  ],
  world: [   // Google News 從邊緣 IP 會被擋,改用非 Google 國際源
    { url: "https://feeds.bbci.co.uk/news/world/rss.xml", src: "BBC" },
    { url: "https://www.aljazeera.com/xml/rss/all.xml", src: "Al Jazeera" },
    { url: "https://feeds.npr.org/1004/rss.xml", src: "NPR" },
  ],
  tech: [
    { url: "https://feeds.bbci.co.uk/news/technology/rss.xml", src: "BBC" },
    { url: "https://techcrunch.com/feed/", src: "TechCrunch" },
    { url: "https://feeds.arstechnica.com/arstechnica/index", src: "Ars Technica" },
  ],
  finance: [
    { url: GNT("BUSINESS"), src: "" },
    { url: "https://finance.yahoo.com/news/rssindex", src: "Yahoo Finance" },
    { url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", src: "CNBC" },
  ],
};

function pick(block, tag) {
  const m = block.match(new RegExp("<" + tag + "[^>]*>([\\s\\S]*?)</" + tag + ">", "i"));
  return m ? m[1].replace(/<!\[CDATA\[/g, "").replace(/\]\]>/g, "").trim() : "";
}
function decode(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&#160;/g, " ").replace(/&amp;/g, "&");
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
    const out = [];
    for (const block of xml.split(/<item[ >]/).slice(1).slice(0, 40)) {
      let title = decode(stripTags(pick(block, "title")));
      let link = stripTags(pick(block, "link"));
      if (!link) { const lm = block.match(/<link[^>]*href="([^"]+)"/i); if (lm) link = lm[1]; }
      const pub = pick(block, "pubDate") || pick(block, "published") || pick(block, "updated");
      let src = feed.src || decode(stripTags(pick(block, "source")));
      if (!feed.src) {
        const dash = title.lastIndexOf(" - ");
        if (dash > 0) { if (!src) src = title.slice(dash + 3); title = title.slice(0, dash); }
      }
      const ts = pub ? Date.parse(pub) : 0;
      if (title && link) out.push({ title, link, src: src || "新聞", ts: isNaN(ts) ? 0 : ts });
    }
    return out;
  } catch (e) { return []; }
}

async function handleNews(request) {
  const feedKey = new URL(request.url).searchParams.get("feed") || "tw";
  const feeds = GROUPS[feedKey] || GROUPS.tw;
  const lists = await Promise.all(feeds.map(fetchFeed));
  const seen = new Set(), uniq = [];
  for (const it of [].concat(...lists)) {
    const k = it.title.replace(/\s+/g, "").slice(0, 40).toLowerCase();
    if (!k || seen.has(k)) continue;
    seen.add(k); uniq.push(it);
  }
  uniq.sort((a, b) => b.ts - a.ts);
  const items = uniq.slice(0, 50).map(it => ({
    title: it.title, link: it.link, src: it.src,
    time: it.ts ? new Date(it.ts).toISOString() : null,
  }));
  return new Response(JSON.stringify({ feed: feedKey, generated_at: new Date().toISOString(), count: items.length, items }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=120",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/news") return handleNews(request);
    return env.ASSETS.fetch(request);   // 其餘交給靜態資產(index.html、data/* 等)
  },
};

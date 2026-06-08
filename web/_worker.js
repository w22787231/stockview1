// Cloudflare Pages 進階模式 Worker:/api/news 動態代理 RSS,其餘走靜態資產。
// (functions/ 目錄在 wrangler pages deploy 下未被編譯,故改用 _worker.js,必被識別。)

// 只用「從 Cloudflare 邊緣可成功抓」的源:cnyes / Yahoo / CNBC。
// (Google News、BBC、Al Jazeera 等會被邊緣資料中心 IP 擋,故不用。)
const CNBC = (id) => `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=${id}`;
const GROUPS = {
  tw: [
    { url: "https://news.cnyes.com/rss/v1/news/category/tw_stock", src: "鉅亨·台股" },
    { url: "https://news.cnyes.com/rss/v1/news/category/headline", src: "鉅亨·頭條" },
    { url: "https://tw.stock.yahoo.com/rss?category=news", src: "Yahoo股市" },
  ],
  world: [
    { url: CNBC(100727362), src: "CNBC World" },
    { url: CNBC(100003114), src: "CNBC" },
  ],
  tech: [
    { url: CNBC(19854910), src: "CNBC Tech" },
    { url: CNBC(10001147), src: "CNBC Biz" },
  ],
  finance: [
    { url: "https://finance.yahoo.com/news/rssindex", src: "Yahoo Finance" },
    { url: CNBC(20910258), src: "CNBC 市場" },
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

function hasCJK(s) { return /[一-鿿]/.test(s || ""); }

// Cloudflare Workers AI(env.AI)把多則英文標題翻成台灣繁中。
// 用 LLM(非 m2m100,因 m2m100 只出簡體);要求回 JSON 陣列以逐則對位。
// 沒綁 AI / 解析失敗 / 長度不符 → 回 null(前端顯英文原文)。
const TRANSLATE_MODEL = "@cf/meta/llama-3.1-8b-instruct";
async function translateBatch(titles, env) {
  if (!titles.length || !env || !env.AI) return null;
  try {
    const sys = "你是專業新聞編譯。把使用者提供的英文新聞標題翻成台灣慣用的繁體中文(不要簡體)。"
      + "只輸出一個 JSON 字串陣列,長度與順序與輸入完全相同,不要任何說明、編號或 markdown。";
    const r = await env.AI.run(TRANSLATE_MODEL, {
      messages: [{ role: "system", content: sys }, { role: "user", content: JSON.stringify(titles) }],
      max_tokens: 1536, temperature: 0.1,
    });
    let txt = ((r && r.response) || "").trim();
    const s = txt.indexOf("["), e = txt.lastIndexOf("]");
    if (s < 0 || e <= s) return null;
    const arr = JSON.parse(txt.slice(s, e + 1));
    return (Array.isArray(arr) && arr.length === titles.length) ? arr.map(x => String(x)) : null;
  } catch (e) { return null; }
}

// 對 items 的英文標題補 title_zh(分塊 10 則/批,各批獨立容錯;中文標題自動跳過)。
async function attachZh(items, env) {
  if (!env || !env.AI) return;
  const idxs = items.map((it, i) => (hasCJK(it.title) ? -1 : i)).filter(i => i >= 0);
  if (!idxs.length) return;
  const CHUNK = 10, batches = [];
  for (let i = 0; i < idxs.length; i += CHUNK) batches.push(idxs.slice(i, i + CHUNK));
  const results = await Promise.all(batches.map(b => translateBatch(b.map(i => items[i].title), env)));
  batches.forEach((b, bi) => {
    const tr = results[bi];
    if (!tr) return;
    b.forEach((idx, j) => {
      const zh = (tr[j] || "").trim();
      if (zh && zh !== items[idx].title) items[idx].title_zh = zh;
    });
  });
}

async function fetchFeed(feed) {
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 6000);   // 單源 6 秒逾時,不拖累整體
  try {
    const r = await fetch(feed.url, {
      headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml,application/xml,text/xml,*/*" },
      cf: { cacheTtl: 120, cacheEverything: true },
      signal: ctrl.signal,
    });
    clearTimeout(tid);
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

async function handleNews(request, env) {
  const feedKey = new URL(request.url).searchParams.get("feed") || "tw";
  const cache = caches.default;
  const cacheKey = new Request("https://news.cache/api/news?feed=" + feedKey);  // 穩定 key,忽略 &t=
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
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
  await attachZh(items, env);   // 英文標題補繁中 title_zh(快取前做一次,120 秒內共用)
  const resp = new Response(JSON.stringify({ feed: feedKey, generated_at: new Date().toISOString(), count: items.length, items }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=120",
      "Access-Control-Allow-Origin": "*",
    },
  });
  if (items.length) { try { await cache.put(cacheKey, resp.clone()); } catch (e) {} }  // 有內容才快取
  return resp;
}

// ── 即時報價:代理 Yahoo chart API(任意代號,不限預生的 1700 檔)──
async function fetchQuote(sym, withKline) {
  const range = withKline ? "6mo" : "1d";
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=${range}`,
      { headers: { "User-Agent": "Mozilla/5.0" }, cf: { cacheTtl: 20 }, signal: ctrl.signal });
    clearTimeout(tid);
    if (!r.ok) return null;
    const j = await r.json();
    const res = j && j.chart && j.chart.result && j.chart.result[0];
    if (!res || !res.meta) return null;
    const m = res.meta;
    if (m.regularMarketPrice == null) return null;
    const q = {
      sym: m.symbol || sym, name: m.longName || m.shortName || sym, currency: m.currency || "",
      price: m.regularMarketPrice, prev: (m.chartPreviousClose != null ? m.chartPreviousClose : m.previousClose),
      dayHigh: m.regularMarketDayHigh, dayLow: m.regularMarketDayLow,
      wkHigh: m.fiftyTwoWeekHigh, wkLow: m.fiftyTwoWeekLow, vol: m.regularMarketVolume,
    };
    if (withKline) {
      const qd = res.indicators && res.indicators.quote && res.indicators.quote[0];
      const c = (qd && qd.close) || [], v = (qd && qd.volume) || [];
      const cl = [], vl = [];
      for (let i = 0; i < c.length; i++) {
        if (c[i] == null) continue;                       // close 為 null 整列丟棄,保持 closes/volumes 對位
        cl.push(Math.round(c[i] * 100) / 100);
        vl.push(v[i] == null ? 0 : v[i]);
      }
      q.closes = cl; q.volumes = vl;
      // kline 模式 range=6mo,meta.chartPreviousClose 是「6 個月前的前收」非昨收 →
      // 日漲跌會變成半年漲幅。改用倒數第二根 close 當真正昨收。
      if (cl.length >= 2) q.prev = cl[cl.length - 2];
    }
    return q;
  } catch (e) { clearTimeout(tid); return null; }
}

async function handleQuotes(request) {
  const url = new URL(request.url);
  const withKline = url.searchParams.get("kline") === "1";
  let syms = (url.searchParams.get("syms") || "").split(",").map(s => s.trim()).filter(Boolean);
  syms = syms.slice(0, withKline ? 5 : 40);
  const arr = await Promise.all(syms.map(s => fetchQuote(s, withKline)));
  const quotes = {};
  syms.forEach((s, i) => { if (arr[i]) quotes[s] = arr[i]; });
  return new Response(JSON.stringify({ quotes, ts: new Date().toISOString() }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=20",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

// ── 基本面:Yahoo quoteSummary(需 crumb+cookie)→ fwdEPS/fwdPE/PEG/目標價/產業 ──
async function _yahooCrumb() {
  let cookie = "";
  try {
    const r = await fetch("https://fc.yahoo.com/", { headers: { "User-Agent": "Mozilla/5.0" }, redirect: "manual" });
    const sc = (r.headers.getSetCookie ? r.headers.getSetCookie() : [r.headers.get("set-cookie")]).filter(Boolean);
    cookie = sc.map(s => s.split(";")[0]).join("; ");
  } catch (e) {}
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb",
    { headers: { "User-Agent": "Mozilla/5.0", "Cookie": cookie } });
  return { crumb: (await cr.text()).trim(), cookie };
}
async function fetchFund(sym, crumb, cookie) {
  const raw = o => (o && o.raw != null) ? o.raw : (typeof o === "number" ? o : null);
  try {
    const u = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/" + encodeURIComponent(sym) +
      "?modules=defaultKeyStatistics,financialData,summaryProfile,price&crumb=" + encodeURIComponent(crumb);
    const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0", "Cookie": cookie }, cf: { cacheTtl: 600 } });
    if (!r.ok) return null;
    const j = await r.json();
    const res = j.quoteSummary && j.quoteSummary.result && j.quoteSummary.result[0];
    if (!res) return null;
    const ks = res.defaultKeyStatistics || {}, fd = res.financialData || {}, sp = res.summaryProfile || {}, pr = res.price || {};
    return {
      name: pr.longName || pr.shortName || sym,
      fwdEps: raw(ks.forwardEps), fwdPe: raw(ks.forwardPE), trailPe: raw(ks.trailingPE),
      peg: raw(ks.trailingPegRatio) != null ? raw(ks.trailingPegRatio) : raw(ks.pegRatio),
      target: raw(fd.targetMeanPrice), industry: sp.industry || null,
    };
  } catch (e) { return null; }
}
async function handleFundamentals(request) {
  const url = new URL(request.url);
  const syms = (url.searchParams.get("syms") || "").split(",").map(s => s.trim()).filter(Boolean).slice(0, 30);
  const cache = caches.default;
  const ckey = new Request("https://fund.cache/api/fundamentals?syms=" + syms.join(","));
  const hit = await cache.match(ckey);
  if (hit) return hit;
  let crumb = "", cookie = "";
  try { ({ crumb, cookie } = await _yahooCrumb()); } catch (e) {}
  const fundamentals = {};
  if (crumb && !/Invalid|Unauthorized/i.test(crumb)) {
    const arr = await Promise.all(syms.map(s => fetchFund(s, crumb, cookie)));
    syms.forEach((s, i) => { if (arr[i]) fundamentals[s] = arr[i]; });
  }
  const resp = new Response(JSON.stringify({ fundamentals, ts: new Date().toISOString() }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=600",
      "Access-Control-Allow-Origin": "*",
    },
  });
  if (Object.keys(fundamentals).length) { try { await cache.put(ckey, resp.clone()); } catch (e) {} }
  return resp;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/news") return handleNews(request, env);
    if (url.pathname === "/api/quotes") return handleQuotes(request);
    if (url.pathname === "/api/fundamentals") return handleFundamentals(request);
    return env.ASSETS.fetch(request);   // 其餘交給靜態資產(index.html、data/* 等)
  },
};

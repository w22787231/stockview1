// Cloudflare Pages 進階模式 Worker:/api/news 動態代理 RSS,其餘走靜態資產。
// (functions/ 目錄在 wrangler pages deploy 下未被編譯,故改用 _worker.js,必被識別。)

// 只用「從 Cloudflare 邊緣可成功抓」的源:cnyes / Yahoo / CNBC。
// (Google News、BBC、Al Jazeera 等會被邊緣資料中心 IP 擋,故不用。)
const CNBC = (id) => `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=${id}`;
const GROUPS = {
  market: [],
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

function _htmlEsc(s) {
  return String(s || "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
async function loadDigestItems(env, feedKey) {
  if (!env || !env.PUSH_SUBS || feedKey !== "market") return [];
  try {
    const lst = await env.PUSH_SUBS.list({ prefix: "digest:", limit: 20 });
    const vals = await Promise.all(lst.keys.map(k => env.PUSH_SUBS.get(k.name)));
    return vals.map(v => { try { return JSON.parse(v); } catch (e) { return null; } })
      .filter(Boolean)
      .sort((a, b) => Date.parse(b.time || 0) - Date.parse(a.time || 0))
      .slice(0, 5)
      .map(d => ({
        title: d.title || "每日市場總覽",
        link: d.link || ("/api/news/digest?id=" + encodeURIComponent(d.id || "")),
        src: d.src || "Codex市場總覽",
        time: d.time || null,
      }));
  } catch (e) { return []; }
}
async function handleNewsIngest(request, env) {
  if (request.method === "OPTIONS")
    return new Response(null, { headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST,OPTIONS", "Access-Control-Allow-Headers": "Content-Type,x-poller-token" } });
  if (request.method !== "POST") return _pjson({ error: "POST only" }, 405);
  if (!env || !env.PUSH_SUBS) return _pjson({ error: "push_not_configured", hint: "尚未綁定 PUSH_SUBS KV" }, 503);
  if (!env.POLLER_TOKEN || request.headers.get("x-poller-token") !== env.POLLER_TOKEN) return _pjson({ error: "unauthorized" }, 401);
  let body; try { body = await request.json(); } catch (e) { return _pjson({ error: "bad_json" }, 400); }
  const title = String((body && body.title) || "").trim().slice(0, 160);
  const text = String((body && (body.body || body.summary || body.text)) || "").trim().slice(0, 24000);
  if (!title || !text) return _pjson({ error: "title_and_body_required" }, 400);
  const feed = (["market", "tw", "finance", "main"].includes(body.feed) ? body.feed : "market");
  const id = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  const item = { id, feed, title, body: text, src: body.src || "Codex市場總覽", time: body.time || new Date().toISOString() };
  await env.PUSH_SUBS.put("digest:" + id, JSON.stringify(item), { expirationTtl: 60 * 60 * 24 * 14 });
  return _pjson({ ok: true, id, link: "/api/news/digest?id=" + encodeURIComponent(id) });
}
async function handleNewsDigest(request, env) {
  const id = new URL(request.url).searchParams.get("id") || "";
  if (!env || !env.PUSH_SUBS || !id) return new Response("Not found", { status: 404 });
  const v = await env.PUSH_SUBS.get("digest:" + id);
  if (!v) return new Response("Not found", { status: 404 });
  let d; try { d = JSON.parse(v); } catch (e) { return new Response("Not found", { status: 404 }); }
  const html = "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
    + "<title>" + _htmlEsc(d.title) + "</title><style>body{font-family:-apple-system,'Segoe UI','Microsoft JhengHei',sans-serif;line-height:1.75;max-width:860px;margin:0 auto;padding:24px;color:#1a2433;background:#f6f8fb}article{background:#fff;border:1px solid #e3e8f0;border-radius:12px;padding:22px;box-shadow:0 4px 16px rgba(16,30,54,.05)}h1{font-size:24px;line-height:1.35;margin:0 0 8px}.meta{color:#667085;font-size:13px;margin-bottom:18px}pre{white-space:pre-wrap;font:inherit;margin:0}a{color:#2563eb}</style></head><body><article>"
    + "<h1>" + _htmlEsc(d.title) + "</h1><div class='meta'>" + _htmlEsc(d.src || "Codex市場總覽") + " · " + _htmlEsc(d.time || "") + " · <a href='/?src=push#tw_all'>回股觀觀股</a></div>"
    + "<pre>" + _htmlEsc(d.body) + "</pre></article></body></html>";
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}

async function handleNews(request, env) {
  const feedKey = new URL(request.url).searchParams.get("feed") || "tw";
  const cache = caches.default;
  const cacheKey = new Request("https://news.cache/api/news?feed=" + feedKey);  // 穩定 key,忽略 &t=
  const hit = await cache.match(cacheKey);
  const hasDigestOverlay = (feedKey === "market");
  if (hit && !hasDigestOverlay) return hit;
  const feeds = GROUPS[feedKey] || GROUPS.tw;
  const lists = await Promise.all(feeds.map(fetchFeed));
  const seen = new Set(), uniq = [];
  for (const it of [].concat(...lists)) {
    const k = it.title.replace(/\s+/g, "").slice(0, 40).toLowerCase();
    if (!k || seen.has(k)) continue;
    seen.add(k); uniq.push(it);
  }
  uniq.sort((a, b) => b.ts - a.ts);
  const digestItems = await loadDigestItems(env, feedKey);
  const items = uniq.slice(0, Math.max(0, 50 - digestItems.length)).map(it => ({
    title: it.title, link: it.link, src: it.src,
    time: it.ts ? new Date(it.ts).toISOString() : null,
  }));
  await attachZh(items, env);   // 英文標題補繁中 title_zh(快取前做一次,120 秒內共用)
  items.unshift(...digestItems); // Codex 市場總覽置頂
  const resp = new Response(JSON.stringify({ feed: feedKey, generated_at: new Date().toISOString(), count: items.length, items }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=120",
      "Access-Control-Allow-Origin": "*",
    },
  });
  if (items.length && !hasDigestOverlay) { try { await cache.put(cacheKey, resp.clone()); } catch (e) {} }  // 有內容才快取
  return resp;
}

// ── 即時報價:代理 Yahoo chart API(任意代號,不限預生的 1700 檔)──
async function fetchQuote(sym, withKline, klRange) {
  const range = withKline ? (klRange || "1y") : "1d";   // 1y:讓持股均線交叉欄的 EMA20/60 收斂(6mo 會假交叉);自訂交叉頁帶 kr=5y 抓 5 年算評分
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
  const klRange = url.searchParams.get("kr") || "1y";   // kline 範圍:1y(預設)/5y(自訂交叉頁回測)
  let syms = (url.searchParams.get("syms") || "").split(",").map(s => s.trim()).filter(Boolean);
  syms = syms.slice(0, withKline ? 5 : 40);
  const arr = await Promise.all(syms.map(s => fetchQuote(s, withKline, klRange)));
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

// ── 選擇權鏈:Yahoo options(需 crumb+cookie)→ 各履約價 OI/量/IV(算 PCR/MaxPain/分布)──
async function fetchOptions(sym, crumb, cookie, date) {
  try {
    let u = "https://query1.finance.yahoo.com/v7/finance/options/" + encodeURIComponent(sym) +
      "?crumb=" + encodeURIComponent(crumb);
    if (date) u += "&date=" + encodeURIComponent(date);
    const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0", "Cookie": cookie }, cf: { cacheTtl: 180 } });
    if (!r.ok) return null;
    const j = await r.json();
    const res = j.optionChain && j.optionChain.result && j.optionChain.result[0];
    if (!res) return null;
    const q = res.quote || {};
    const opt = (res.options || [])[0] || {};
    const leg = a => (a || []).map(o => ({
      strike: o.strike, oi: o.openInterest || 0, vol: o.volume || 0,
      iv: o.impliedVolatility != null ? o.impliedVolatility : null, last: o.lastPrice != null ? o.lastPrice : null,
    }));
    return {
      sym: sym, name: q.shortName || q.longName || sym,
      price: q.regularMarketPrice != null ? q.regularMarketPrice : null,
      currency: q.currency || "", expiry: opt.expirationDate || null,
      expirations: res.expirationDates || [],
      calls: leg(opt.calls), puts: leg(opt.puts),
    };
  } catch (e) { return null; }
}
async function handleOptions(request) {
  const url = new URL(request.url);
  const sym = (url.searchParams.get("sym") || "").trim().toUpperCase();
  const date = (url.searchParams.get("date") || "").trim();
  const cors = { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" };
  if (!sym) return new Response(JSON.stringify({ error: "no sym" }), { status: 400, headers: cors });
  let crumb = "", cookie = "";
  try { ({ crumb, cookie } = await _yahooCrumb()); } catch (e) {}
  let data = null;
  if (crumb && !/Invalid|Unauthorized/i.test(crumb)) data = await fetchOptions(sym, crumb, cookie, date);
  return new Response(JSON.stringify(data || { error: "not found", sym: sym }), {
    headers: Object.assign({ "Cache-Control": "public, max-age=120" }, cors),
  });
}

// ── 今日盤中分時:Yahoo chart interval=5m range=1d → 今日收盤序列 + 昨收(持股表小走勢圖)──
async function fetchIntraday(sym) {
  try {
    const u = "https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(sym) + "?interval=5m&range=1d";
    const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0" }, cf: { cacheTtl: 120 } });
    if (!r.ok) return null;
    const j = await r.json();
    const res = j.chart && j.chart.result && j.chart.result[0];
    if (!res) return null;
    const closes = (((res.indicators || {}).quote || [])[0] || {}).close || [];
    const pts = closes.filter(v => v != null);
    const meta = res.meta || {};
    const prev = meta.chartPreviousClose != null ? meta.chartPreviousClose : (meta.previousClose != null ? meta.previousClose : null);
    if (!pts.length) return null;
    return { prev: prev, closes: pts };
  } catch (e) { return null; }
}
async function handleIntraday(request) {
  const url = new URL(request.url);
  const syms = (url.searchParams.get("syms") || "").split(",").map(s => s.trim()).filter(Boolean).slice(0, 40);
  const out = {};
  const arr = await Promise.all(syms.map(fetchIntraday));
  syms.forEach((s, i) => { if (arr[i]) out[s] = arr[i]; });
  return new Response(JSON.stringify({ intraday: out, ts: new Date().toISOString() }), {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=120", "Access-Control-Allow-Origin": "*" },
  });
}

// ── 任意代號完整詳情(預生 1700 檔以外):chart OHLCV + quoteSummary(估值+三表)──
async function fetchStockFull(sym, crumb, cookie) {
  const raw = o => (o && o.raw != null) ? o.raw : (typeof o === "number" ? o : null);
  // 1) K 線 OHLCV(2 年,公開)
  let candles = [];
  try {
    const cr = await fetch("https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(sym) + "?interval=1d&range=5y",
      { headers: { "User-Agent": "Mozilla/5.0" }, cf: { cacheTtl: 600 } });
    const cj = await cr.json();
    const res = cj.chart && cj.chart.result && cj.chart.result[0];
    if (res) {
      const ts = res.timestamp || [], q = ((res.indicators || {}).quote || [])[0] || {};
      for (let i = 0; i < ts.length; i++) {
        if (q.close && q.close[i] != null) {
          const d = new Date(ts[i] * 1000).toISOString().slice(0, 10);
          candles.push({ t: d, o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume ? q.volume[i] : null });
        }
      }
    }
  } catch (e) {}
  // 2) quoteSummary:估值指標
  let metrics = null;
  try {
    const u = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/" + encodeURIComponent(sym) +
      "?modules=defaultKeyStatistics,financialData,summaryDetail,price,summaryProfile&crumb=" + encodeURIComponent(crumb);
    const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0", "Cookie": cookie }, cf: { cacheTtl: 600 } });
    if (r.ok) {
      const j = await r.json();
      const res = j.quoteSummary && j.quoteSummary.result && j.quoteSummary.result[0];
      if (res) {
        const ks = res.defaultKeyStatistics || {}, fd = res.financialData || {}, sd = res.summaryDetail || {},
          pr = res.price || {}, sp = res.summaryProfile || {};
        metrics = {
          name: pr.longName || pr.shortName || sym, sector: sp.sector || null, industry: sp.industry || null,
          price: raw(fd.currentPrice) != null ? raw(fd.currentPrice) : raw(pr.regularMarketPrice),
          mktcap: raw(pr.marketCap), pe: raw(sd.trailingPE), forwardPe: raw(sd.forwardPE) != null ? raw(sd.forwardPE) : raw(ks.forwardPE),
          ps: raw(sd.priceToSalesTrailing12Months), pb: raw(ks.priceToBook),
          roe: raw(fd.returnOnEquity), profit_margin: raw(fd.profitMargins), rev_growth: raw(fd.revenueGrowth),
          high52: raw(sd.fiftyTwoWeekHigh), low52: raw(sd.fiftyTwoWeekLow), target: raw(fd.targetMeanPrice),
          fwdEps: raw(ks.forwardEps), fwdPe: raw(ks.forwardPE),
          peg: raw(ks.trailingPegRatio) != null ? raw(ks.trailingPegRatio) : raw(ks.pegRatio),
        };
      }
    }
  } catch (e) {}
  // 3) 財務三表:fundamentals-timeseries(最新季報,與 yfinance 同源)
  let statements = null;
  try {
    const now = Math.floor(Date.now() / 1000), p1 = now - 86400 * 800;
    const types = ["quarterlyTotalRevenue", "quarterlyGrossProfit", "quarterlyOperatingIncome", "quarterlyNetIncome",
      "quarterlyTotalAssets", "quarterlyTotalLiabilitiesNetMinorityInterest", "quarterlyStockholdersEquity", "quarterlyCashAndCashEquivalents",
      "quarterlyOperatingCashFlow", "quarterlyInvestingCashFlow", "quarterlyFinancingCashFlow", "quarterlyFreeCashFlow"];
    const tu = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/" + encodeURIComponent(sym) +
      "?symbol=" + encodeURIComponent(sym) + "&type=" + types.join(",") + "&period1=" + p1 + "&period2=" + now +
      "&merge=false&crumb=" + encodeURIComponent(crumb);
    const tr = await fetch(tu, { headers: { "User-Agent": "Mozilla/5.0", "Cookie": cookie }, cf: { cacheTtl: 600 } });
    if (tr.ok) {
      const tj = await tr.json();
      const tsmap = {};
      (((tj.timeseries || {}).result) || []).forEach(rr => {
        const ty = rr.meta && rr.meta.type && rr.meta.type[0]; if (!ty || !rr[ty]) return;
        tsmap[ty] = rr[ty].filter(Boolean).map(e => ({ date: (e.asOfDate || "").slice(0, 7), val: (e.reportedValue && e.reportedValue.raw != null) ? e.reportedValue.raw : null }));
      });
      const mk = mapping => {
        let periods = [];
        mapping.forEach(([, ty]) => { const a = tsmap[ty]; if (a && a.length > periods.length) periods = a.map(x => x.date); });
        if (!periods.length) return null;
        periods = periods.slice().reverse().slice(0, 6);   // 新→舊,最多 6 季
        const rows = mapping.map(([label, ty]) => {
          const byd = {}; (tsmap[ty] || []).forEach(x => { byd[x.date] = x.val; });
          const vals = periods.map(p => byd[p] != null ? byd[p] : null);
          const yoy = (vals[0] != null && vals[4] != null && vals[4] !== 0) ? (vals[0] - vals[4]) / Math.abs(vals[4]) * 100 : null;
          return { label, vals, yoy };
        }).filter(r => r.vals.some(v => v != null));
        return rows.length ? { periods, rows } : null;
      };
      statements = {
        period_type: "quarterly",
        income: mk([["Total Revenue", "quarterlyTotalRevenue"], ["Gross Profit", "quarterlyGrossProfit"],
          ["Operating Income", "quarterlyOperatingIncome"], ["Net Income", "quarterlyNetIncome"]]),
        balance: mk([["Total Assets", "quarterlyTotalAssets"], ["Total Liabilities Net Minority Interest", "quarterlyTotalLiabilitiesNetMinorityInterest"],
          ["Stockholders Equity", "quarterlyStockholdersEquity"], ["Cash And Cash Equivalents", "quarterlyCashAndCashEquivalents"]]),
        cashflow: mk([["Operating Cash Flow", "quarterlyOperatingCashFlow"], ["Investing Cash Flow", "quarterlyInvestingCashFlow"],
          ["Financing Cash Flow", "quarterlyFinancingCashFlow"], ["Free Cash Flow", "quarterlyFreeCashFlow"]]),
      };
    }
  } catch (e) {}
  return { sym, candles, metrics, statements };
}
async function handleStockFull(request) {
  const url = new URL(request.url);
  const sym = (url.searchParams.get("sym") || "").trim();
  if (!sym) return new Response(JSON.stringify({ error: "no sym" }), { status: 400, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } });
  const cache = caches.default;
  const ckey = new Request("https://stockfull.cache/api/stockfull?sym=" + sym);
  const hit = await cache.match(ckey);
  if (hit) return hit;
  let crumb = "", cookie = "";
  try { ({ crumb, cookie } = await _yahooCrumb()); } catch (e) {}
  const data = await fetchStockFull(sym, crumb, cookie);
  const resp = new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=900", "Access-Control-Allow-Origin": "*" },
  });
  if (data.candles && data.candles.length) { try { await cache.put(ckey, resp.clone()); } catch (e) {} }
  return resp;
}

// ── Web Push 訂閱:存入 KV(env.PUSH_SUBS);寫入靠綁定,不需 API token ──
async function _sha256hex(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}
function _pjson(o, status) {
  return new Response(JSON.stringify(o), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" },
  });
}
async function handlePush(request, env, action) {
  if (request.method === "OPTIONS")
    return new Response(null, { headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST,OPTIONS", "Access-Control-Allow-Headers": "Content-Type" } });
  if (request.method !== "POST") return _pjson({ error: "POST only" }, 405);
  if (!env || !env.PUSH_SUBS) return _pjson({ error: "push_not_configured", hint: "尚未綁定 PUSH_SUBS KV" }, 503);
  let body; try { body = await request.json(); } catch (e) { return _pjson({ error: "bad_json" }, 400); }
  const sub = body && body.subscription;
  if (!sub || !sub.endpoint) return _pjson({ error: "no_subscription" }, 400);
  const key = "sub:" + (await _sha256hex(sub.endpoint));
  if (action === "unsubscribe") { await env.PUSH_SUBS.delete(key); return _pjson({ ok: true, removed: true }); }
  const watchlist = Array.isArray(body.watchlist) ? [...new Set(body.watchlist.map(String))].slice(0, 500) : [];
  const ua = (typeof body.ua === "string" ? body.ua : "").slice(0, 300);
  const scope = (body.scope === "custom" || body.scope === "strong") ? body.scope : "all";   // custom=只我的股池、strong=強勢股、all=全部池
  await env.PUSH_SUBS.put(key, JSON.stringify({ subscription: sub, watchlist, ua, scope, ts: new Date().toISOString() }));
  return _pjson({ ok: true, n: watchlist.length });
}

// ── 估值(/股價估價 自動化):靜態全表 + KV 新估值;下單佇列複用 PUSH_SUBS KV(req: 前綴) ──
async function _valAll(request, env) {
  let out;
  try { const r = await env.ASSETS.fetch(new URL("/data/valuations.json", request.url)); out = await r.json(); }
  catch (e) { out = { stocks: [] }; }
  if (!env || !env.PUSH_SUBS) return out;
  const byTicker = new Map((out.stocks || []).map(s => [String(s.ticker || "").toUpperCase(), s]));
  const lst = await env.PUSH_SUBS.list({ prefix: "req:" });
  const kvRows = await Promise.all(lst.keys.map(async k => {
    const raw = await env.PUSH_SUBS.get(k.name);
    if (!raw) return null;
    let rec; try { rec = JSON.parse(raw); } catch (e) { return null; }
    if (rec.status !== "done" || !rec.data) return null;
    const t = String(rec.data.ticker || k.name.slice(4)).toUpperCase();
    return [t, rec.data];
  }));
  for (const row of kvRows) {
    if (row) byTicker.set(row[0], row[1]);
  }
  out.stocks = Array.from(byTicker.values());
  out.count = out.stocks.length;
  out.updated = out.updated || new Date().toISOString();
  return out;
}
async function handleValRequest(request, env) {
  if (request.method === "OPTIONS") return new Response(null, { headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST,OPTIONS", "Access-Control-Allow-Headers": "Content-Type" } });
  if (request.method !== "POST") return _pjson({ error: "POST only" }, 405);
  let body; try { body = await request.json(); } catch (e) { return _pjson({ error: "bad_json" }, 400); }
  const t = String((body && body.ticker) || "").trim().toUpperCase();
  if (!/^[A-Z0-9.\-]{1,8}$/.test(t)) return _pjson({ error: "代號格式不符" }, 400);
  const all = await _valAll(request, env);
  const hit = (all.stocks || []).find(s => s.ticker === t);
  if (hit) return _pjson({ status: "done", cached: true, data: hit });
  if (!env || !env.PUSH_SUBS) return _pjson({ status: "no_queue", msg: "未綁定 KV,僅能查已估的" }, 503);
  const lst = await env.PUSH_SUBS.list({ prefix: "req:" });
  let pending = 0;
  for (const k of lst.keys) { const v = await env.PUSH_SUBS.get(k.name); if (v && JSON.parse(v).status === "pending") pending++; }
  if (pending >= 5) return _pjson({ status: "busy", msg: "估價佇列已滿,稍後再試" }, 429);
  await env.PUSH_SUBS.put("req:" + t, JSON.stringify({ status: "pending", ts: Date.now() }), { expirationTtl: 1800 });
  return _pjson({ status: "queued", ticker: t });
}
async function handleValStatus(request, env) {
  const t = String(new URL(request.url).searchParams.get("ticker") || "").trim().toUpperCase();
  if (!env || !env.PUSH_SUBS) return _pjson({ status: "unknown" });
  const v = await env.PUSH_SUBS.get("req:" + t);
  return v ? new Response(v, { headers: { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" } }) : _pjson({ status: "unknown" });
}
async function handleValPending(request, env) {   // PC poller 取待辦(token 保護)
  if (request.headers.get("x-poller-token") !== env.POLLER_TOKEN) return _pjson({ error: "unauthorized" }, 401);
  if (!env || !env.PUSH_SUBS) return _pjson({ tickers: [] });
  const lst = await env.PUSH_SUBS.list({ prefix: "req:" });
  const out = [];
  for (const k of lst.keys) { const v = await env.PUSH_SUBS.get(k.name); if (v && JSON.parse(v).status === "pending") out.push(k.name.slice(4)); }
  return _pjson({ tickers: out });
}
async function handleValResult(request, env) {
  if (request.method !== "POST") return _pjson({ error: "POST only" }, 405);
  if (!env || !env.PUSH_SUBS) return _pjson({ error: "no_queue" }, 503);
  if (request.headers.get("x-poller-token") !== env.POLLER_TOKEN) return _pjson({ error: "unauthorized" }, 401);
  let body; try { body = await request.json(); } catch (e) { return _pjson({ error: "bad_json" }, 400); }
  const t = String(body.ticker || "").trim().toUpperCase();
  await env.PUSH_SUBS.put("req:" + t, JSON.stringify({ status: "done", data: body.data, ts: Date.now() }));
  return _pjson({ ok: true });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/news") return handleNews(request, env);
    if (url.pathname === "/api/news/ingest") return handleNewsIngest(request, env);
    if (url.pathname === "/api/news/digest") return handleNewsDigest(request, env);
    if (url.pathname === "/api/quotes") return handleQuotes(request);
    if (url.pathname === "/api/fundamentals") return handleFundamentals(request);
    if (url.pathname === "/api/options") return handleOptions(request);
    if (url.pathname === "/api/intraday") return handleIntraday(request);
    if (url.pathname === "/api/stockfull") return handleStockFull(request);
    if (url.pathname === "/api/push/subscribe") return handlePush(request, env, "subscribe");
    if (url.pathname === "/api/push/unsubscribe") return handlePush(request, env, "unsubscribe");
    if (url.pathname === "/api/val/all") return _pjson(await _valAll(request, env));
    if (url.pathname === "/api/val/request") return handleValRequest(request, env);
    if (url.pathname === "/api/val/status") return handleValStatus(request, env);
    if (url.pathname === "/api/val/pending") return handleValPending(request, env);
    if (url.pathname === "/api/val/result") return handleValResult(request, env);
    return env.ASSETS.fetch(request);   // 其餘交給靜態資產(index.html、data/* 等)
  },
};

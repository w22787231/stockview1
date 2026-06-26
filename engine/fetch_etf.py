# -*- coding: utf-8 -*-
"""抓取 9 檔台股主動式ETF每日持股,輸出統一格式 list[dict]:
   {etf, etf_name, code, name, weight, qty}
   來源(已驗證 2026-06-26):統一 ezmoney / 群益 capitalfund / 元大 yuantaetfs /
   富邦 fsit Assets.aspx / 聯博 webapi /holdings / 凱基 kgifund Detail / 安聯 allianzgi POST。野村已取消。"""
import ssl, gzip, re, json, http.cookiejar, html
import urllib.request as U

_CTX = ssl.create_default_context(); _CTX.check_hostname=False; _CTX.verify_mode=ssl.CERT_NONE
class _H(U.HTTPSHandler):
    def __init__(s): super().__init__(context=_CTX)
_UA=[("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"),("Accept-Language","zh-TW")]

ETFS = {
    "00981A": {"name":"統一台股增長",      "src":"tongyi", "fundCode":"49YTW"},
    "00988A": {"name":"統一全球創新",      "src":"tongyi", "fundCode":"61YTW"},
    "00403A": {"name":"統一台股升級50",    "src":"tongyi", "fundCode":"63YTW"},
    "00982A": {"name":"群益台灣精選強棒",  "src":"capital","path":"399"},
    "00990A": {"name":"元大全球AI新經濟",  "src":"yuanta"},
    "00405A": {"name":"富邦台灣龍耀",      "src":"fubon"},
    "00404A": {"name":"聯博動能50",        "src":"ab",     "isin":"TW00000404A5"},
    "00407A": {"name":"凱基台灣",          "src":"kgi",    "fundID":"J024"},
    "00402A": {"name":"安聯美國科技領航",  "src":"allianz","fund_no":"E0003"},
}

def _get(opener, url):
    r=opener.open(U.Request(url), timeout=45); d=r.read()
    if d[:2]==b'\x1f\x8b': d=gzip.decompress(d)
    return d.decode("utf-8","replace")

def _clean(s): return re.sub(r'<[^>]+>','',s).strip()

def _clean_name(name, code):
    n=str(name).strip()
    # 統一海外股名稱常混入 ".amd us(超微半導體公司)" 之類殘留 → 砍掉第一個 '.' 起的尾巴
    if " " in str(code):
        cut=n.find(".")
        if cut>0: n=n[:cut].strip()
    return n or str(name).strip()

def _rec(etf,info,code,name,w,q):
    return {"etf":etf,"etf_name":info["name"],"code":str(code).strip(),"name":_clean_name(name,code),
            "weight":str(w).replace("%","").strip(),"qty":str(q).replace(",","").strip()}

def fetch_tongyi(etf, info):
    """統一 ezmoney:先拿 cookie 再訪。持股是內嵌 HTML-escaped JSON,
       欄位 DetailCode/DetailName/Share(股數)/NavRate(權重%)/AssetCode。"""
    cj=http.cookiejar.CookieJar()
    op=U.build_opener(U.HTTPCookieProcessor(cj), _H()); op.addheaders=_UA
    op.open("https://www.ezmoney.com.tw/", timeout=30)
    t=_get(op, f"https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode={info['fundCode']}")
    t=t.replace("&quot;",'"')
    rows=[]; seen=set()
    for m in re.finditer(
        r'"AssetCode":"([^"]*)"[^{}]*?"DetailCode":"([^"]*)"[^{}]*?"DetailName":"([^"]*)"'
        r'[^{}]*?"Share":([0-9.]+)[^{}]*?"NavRate":([0-9.\-]+)', t):
        asset,code,name,share,nav=m.groups()
        # 接受台股(4-6碼)與海外股(含交易所後綴,如 "MU US"/"285A JP")
        if asset!="ST" or code in seen: continue
        if not re.match(r'^[0-9A-Z]{3,6}( [A-Z]{2,3})?$', code): continue
        seen.add(code)
        qty=str(int(float(share)//1000)) if share else ""
        rows.append(_rec(etf,info,code,name,nav,qty))
    return rows

def fetch_capital(etf, info):
    """群益 capitalfund:Angular SPA + Incapsula → Playwright 渲染後攔截 API JSON。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  {etf}: playwright 未安裝,跳過")
        return []

    json_resps = []  # (url, body)

    def _on_resp(resp):
        if resp.status != 200:
            return
        if "json" not in resp.headers.get("content-type", ""):
            return
        try:
            body = resp.json()
            if isinstance(body, (list, dict)):
                json_resps.append((resp.url, body))
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9"},
        )
        page = ctx.new_page()
        page.on("response", _on_resp)
        try:
            page.goto(
                f"https://www.capitalfund.com.tw/etf/product/detail/{info['path']}/buyback",
                wait_until="networkidle",
                timeout=60000,
            )
            page.wait_for_timeout(3000)  # 額外等 Angular 初始化
        except Exception as e:
            print(f"  {etf}: PW err {type(e).__name__}: {str(e)[:80]}")
        browser.close()

    # 從攔截到的 /CFWeb/api/etf/buyback 中解析持股
    # 結構: body["data"]["pcf"]["stocks"][]{stocNo, stocName, weight, share}
    rows = []; seen = set()
    for url, body in json_resps:
        if not isinstance(body, dict) or body.get("code") != 200:
            continue
        data = body.get("data", {})
        if not isinstance(data, dict):
            continue
        stocks = data.get("stocks", [])
        if not stocks:
            continue
        for item in stocks:
            code = str(item.get("stocNo", "")).strip()
            name = str(item.get("stocName", "")).strip()
            w = str(item.get("weight", "")).strip()
            share = item.get("share") or 0
            q = str(int(float(share) // 1000)) if share else ""
            if not code or code in seen:
                continue
            if not re.match(r"^[0-9A-Z]{4,6}$", code):
                continue
            seen.add(code)
            rows.append(_rec(etf, info, code, name, w, q))
        if rows:
            break
    return rows

def fetch_yuanta(etf, info):
    """元大 yuantaetfs:內嵌 JS 物件。weights 可能是 minify 變數(多字母)→ 標未知。
       排除現金科目(12xx應收/33xx應付)。"""
    op=U.build_opener(_H()); op.addheaders=_UA
    t=_get(op, f"https://www.yuantaetfs.com/product/detail/{etf}/ratio")
    rows=[]; seen=set()
    for m in re.finditer(
        r'\{code:"([^"]+)",(?:ym:[a-z_]+,)?name:("[^"]*"|[a-z_]+),'
        r'(?:ename:[^,]*,)?(?:crncy:[^,]*,)?(?:exrate:[^,]*,)?(?:rto:[^,]*,)?'
        r'weights:([0-9.]+|[a-z]{1,3}),qty:(\d+)\}', t):
        code,name,w,q=m.groups()
        name=name.strip('"')
        if code in seen: continue
        # 排除現金/應收應付科目
        if re.match(r'^(12|33)\d\d$', code) and any(k in name for k in ("應收","應付","預收","現金")):
            continue
        if name in ("ni","",) or re.match(r'^[a-z_]+$', name): name=code  # 變數名 fallback
        seen.add(code)
        wv = w if re.match(r'^[0-9.]+$', w) else ""   # 變數權重→留空(未知)
        rows.append(_rec(etf,info,code,name,wv,q))
    return rows

def fetch_fubon(etf, info):
    """富邦投信 Assets.aspx(純 GET HTML):持股表欄序 代號/名稱/股數/金額/權重%。
       注意:Pcf.aspx 對主動式 ETF 不揭露個股,要用 Assets.aspx。qty 原始股數→張(//1000)。"""
    op=U.build_opener(_H()); op.addheaders=_UA
    t=_get(op, f"https://websys.fsit.com.tw/FubonETF/Trade/Assets.aspx?stkId={etf}&lan=TW")
    rows=[]; seen=set()
    for tab in re.findall(r'<table.*?</table>', t, re.S):
        if "股票代號" not in tab and "股數" not in tab: continue
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tab, re.S):
            cells=re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
            if len(cells)<5: continue
            vals=[html.unescape(re.sub(r'<[^>]+>',' ',c)).strip() for c in cells]
            code=vals[0].rstrip("*").strip()
            if not re.match(r'^[0-9]{4,6}[A-Z]?$', code) or code in seen: continue
            seen.add(code)
            qs=vals[2].replace(",","")
            q=str(int(float(qs))//1000) if re.match(r'^[0-9.]+$', qs) else ""
            rows.append(_rec(etf,info,code,vals[1].rstrip("*"),vals[4],q))
    return rows

def fetch_ab(etf, info):
    """聯博 AB webapi /holdings(純 GET JSON):取 holdingCategory==holdings-section-equity 段。
       info['isin'] 必填(如 TW00000404A5)。qty 股數→張;weight=holdingPerc(%)。"""
    op=U.build_opener(_H()); op.addheaders=_UA
    isin=info.get("isin") or f"TW00000{etf}5"
    data=json.loads(_get(op, f"https://webapi.alliancebernstein.com/v2/funds/tw/zh-tw/investor/{isin}/holdings"))
    rows=[]; seen=set()
    for sec in data.get("domesticHoldings",[]) or []:
        if sec.get("holdingCategory")!="holdings-section-equity": continue
        for h in sec.get("holdings",[]) or []:
            code=(h.get("holdingCode") or "").strip()
            if not (code and code[:4].isdigit()) or code in seen: continue   # 排現金/選擇權/期貨(無代號)
            seen.add(code)
            q=str(int(float(h.get("holdingShares") or 0))//1000)
            w=h.get("holdingPerc"); w="" if w in (None,"") else str(w)
            rows.append(_rec(etf,info,code,h.get("holding") or "",w,q))
    return rows

def fetch_kgi(etf, info):
    """凱基投信 Fund/Detail?fundID=(純 GET HTML):<tr name=content> 4td 代號/名稱/股數/權重%。
       踩雷:持股表在頁面出現兩次→用 code 去重;名稱是 HTML entity→unescape。qty 股數→張。"""
    op=U.build_opener(_H()); op.addheaders=_UA
    t=_get(op, f"https://www.kgifund.com.tw/Fund/Detail?fundID={info['fundID']}")
    rows=[]; seen=set()
    for tr in re.findall(r'<tr name="content"[^>]*>(.*?)</tr>', t, re.S):
        tds=re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds)<4: continue
        cells=[html.unescape(re.sub(r'<[^>]+>','',c)).strip() for c in tds]
        code=cells[0].rstrip("*").strip()
        if not re.match(r'^[0-9]{4,6}[A-Z]?$', code) or code in seen: continue
        seen.add(code)
        qs=cells[2].replace(",","")
        q=str(int(qs)//1000) if qs.isdigit() else ""
        rows.append(_rec(etf,info,code,cells[1].rstrip("*"),cells[3],q))
    return rows

def fetch_allianz(etf, info):
    """安聯 ETF(美股持股):3 步 cookie(WAF→antiforgery→POST GetFundAssets)。
       code 為「NVDA US」、name 可能含「.」(Amazon.com Inc)→繞過 _clean_name 直接建 record。
       qty 原始股數→張(//1000,與統一全球創新海外同口徑)。info['fund_no']=E0003。"""
    fund_no=info.get("fund_no","E0003")
    base="https://etf.allianzgi.com.tw"; api=base+"/webapi/api"
    cj=http.cookiejar.CookieJar()
    op=U.build_opener(U.HTTPCookieProcessor(cj), _H()); op.addheaders=_UA
    try: op.open(base+"/", timeout=30).read()
    except Exception: pass
    op.open(api+"/AntiForgery/GetAntiForgeryToken", timeout=30).read()
    xsrf=next((c.value for c in cj if c.name=="X-XSRF-TOKEN"), "")
    req=U.Request(api+"/Fund/GetFundAssets", data=json.dumps({"FundID":fund_no}).encode(),
                  headers={"Content-Type":"application/json","x-xsrf-token":xsrf or "",
                           "Origin":base,"Referer":base+"/etf-info/"+fund_no})
    d=op.open(req, timeout=40).read()
    if d[:2]==b'\x1f\x8b': d=gzip.decompress(d)
    j=json.loads(d.decode("utf-8","replace"))
    rows=[]; seen=set()
    for tbl in (j.get("Entries",{}) or {}).get("Data",{}).get("Table",[]) or []:
        cols=[c.get("Name") for c in tbl.get("Columns",[]) or []]
        if "股票代號" not in cols: continue
        ic=cols.index("股票代號"); inm=cols.index("股票名稱")
        iq=cols.index("股數") if "股數" in cols else None
        iw=cols.index("權重(%)") if "權重(%)" in cols else None
        for row in tbl.get("Rows",[]) or []:
            code=(row[ic] or "").strip(); name=(row[inm] or "").strip()
            if not code or not name or code in seen: continue
            if any(k in name for k in ("現金","應收","應付","存款")): continue
            seen.add(code)
            qs=(row[iq] or "").replace(",","").strip() if iq is not None else ""
            q=str(int(float(qs))//1000) if re.match(r'^[0-9.]+$', qs) else ""
            w=(row[iw] or "").replace("%","").strip() if iw is not None else ""
            rows.append({"etf":etf,"etf_name":info["name"],"code":code,"name":name,"weight":w,"qty":q})
    return rows

_FETCH={"tongyi":fetch_tongyi,"capital":fetch_capital,"yuanta":fetch_yuanta,
        "fubon":fetch_fubon,"ab":fetch_ab,"kgi":fetch_kgi,"allianz":fetch_allianz}

def fetch_all():
    out={}
    for etf,info in ETFS.items():
        try:
            rows=_FETCH[info["src"]](etf,info); out[etf]=rows
            print(f"  {etf} {info['name']}: {len(rows)} 檔")
        except Exception as e:
            out[etf]=[]; print(f"  {etf} {info['name']}: ERR {type(e).__name__} {str(e)[:60]}")
    return out

if __name__=="__main__":
    print("=== 抓取 5 檔持股 ===")
    data=fetch_all()
    for etf,rows in data.items():
        print(f"\n[{etf}] {len(rows)}檔 前4:")
        for r in rows[:4]: print("   ", {k:r[k] for k in ('code','name','weight','qty')})

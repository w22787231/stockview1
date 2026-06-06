# -*- coding: utf-8 -*-
"""抓取 5 檔台股主動式ETF每日持股,輸出統一格式 list[dict]:
   {etf, etf_name, code, name, weight, qty}
   來源(已驗證 2026-06-04):統一 ezmoney / 群益 capitalfund / 元大 yuantaetfs。野村已取消。"""
import ssl, gzip, re, json, http.cookiejar
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
    """群益 capitalfund buyback:SSR HTML div.tr,欄序=代碼/名稱/權重%/張數。"""
    op=U.build_opener(_H()); op.addheaders=_UA
    t=_get(op, f"https://www.capitalfund.com.tw/etf/product/detail/{info['path']}/buyback")
    rows=[]; seen=set()
    for tr in re.findall(r'class="tr show-for-medium">(.*?)(?=<div[^>]*class="tr|$)', t, re.S):
        cells=[_clean(c) for c in re.findall(r'class="t[hd][^"]*">(.*?)</div>', tr, re.S)]
        cells=[c for c in cells if c]
        if len(cells)>=4 and re.match(r'^[0-9A-Z]{4,6}$', cells[0]) and cells[0] not in seen:
            seen.add(cells[0])
            code,name=cells[0],cells[1]
            w=next((c for c in cells[2:] if '%' in c), "")
            # 張數=不含%的純數字(排除代碼本身)
            q=next((c for c in cells[2:] if re.match(r'^[\d,]+$', c) and '%' not in c), "")
            rows.append(_rec(etf,info,code,name,w,q))
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

_FETCH={"tongyi":fetch_tongyi,"capital":fetch_capital,"yuanta":fetch_yuanta}

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

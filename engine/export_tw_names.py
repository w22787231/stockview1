# -*- coding: utf-8 -*-
"""產生「全台股代號→繁中名」對照表 engine/universe/tw_names.json。
主來源:TWSE ISIN 公開清單(上市 strMode=2 → .TW、上櫃 strMode=4 → .TWO,Big5,涵蓋最全)。
輔來源:TWSE / TPEX OpenAPI(ISIN 被擋時補上市;OpenAPI 之 TPEX 在雲端常失敗,故上櫃主靠 ISIN)。
只收 4 碼數字代號(排除權證/ETN);合併現有 curated 檔(人工標籤優先)。CI 每次產生不回 commit;全失敗則保留 curated。"""
import io
import json
import os
import re
import ssl
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FP = os.path.join(HERE, "universe", "tw_names.json")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url, timeout=30, raw=False, ctx=None):
    b = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout, context=ctx).read()
    return b if raw else b.decode("utf-8", "ignore")


def _ok_code(c):
    return c.isdigit() and len(c) == 4


def _isin(mode, suffix, out):
    """TWSE ISIN 公開清單:每列 <td ...>代號　名稱</td>(全形空格分隔),Big5。"""
    html = _get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=%d" % mode,
                timeout=40, raw=True, ctx=_CTX).decode("big5", "ignore")
    n = 0
    for code, name in re.findall(r"<td[^>]*>(\d{4})　([^<]+)</td>", html):
        name = name.strip()
        if name:
            out.setdefault(code + suffix, name)
            n += 1
    return n


def fetch_all():
    out = {}
    for mode, suf, lab in ((2, ".TW", "上市"), (4, ".TWO", "上櫃")):   # 主來源 ISIN
        try:
            print("[tw_names] ISIN %s: %d 檔" % (lab, _isin(mode, suf, out)))
        except Exception as e:
            print("[tw_names] ISIN %s err: %s" % (lab, e))
    try:                                                   # 輔:TWSE OpenAPI 補上市(ISIN 失敗時)
        for r in json.loads(_get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")):
            c, nm = str(r.get("Code", "")).strip(), str(r.get("Name", "")).strip()
            if _ok_code(c) and nm:
                out.setdefault(c + ".TW", nm)
    except Exception as e:
        print("[tw_names] TWSE OpenAPI err:", e)
    try:                                                   # 輔:TPEX OpenAPI 補上櫃(雲端常失敗)
        for r in json.loads(_get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")):
            c = str(r.get("SecuritiesCompanyCode") or "").strip()
            nm = str(r.get("CompanyName") or "").strip()
            if _ok_code(c) and nm:
                out.setdefault(c + ".TWO", nm)
    except Exception as e:
        print("[tw_names] TPEX OpenAPI err:", e)
    return out


def build():
    cur = {}
    try:
        cur = json.load(io.open(FP, encoding="utf-8"))
    except Exception:
        pass
    full = fetch_all()
    full.update(cur)                                       # curated 優先(保留人工標籤,如 -KY/-DR)
    if len(full) > len(cur):
        os.makedirs(os.path.dirname(FP), exist_ok=True)
        with io.open(FP, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False)
        print("[tw_names] %d -> %d (上市+上櫃合併)" % (len(cur), len(full)))
    else:
        print("[tw_names] 抓取為空,保留 curated %d 檔" % len(cur))


if __name__ == "__main__":
    build()

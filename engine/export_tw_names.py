# -*- coding: utf-8 -*-
"""產生「全台股代號→繁中名」對照表 engine/universe/tw_names.json。
來源:TWSE OpenAPI(上市 .TW)+ TPEX OpenAPI(上櫃 .TWO),只收 4 碼數字代號(排除權證/ETN 等)。
合併現有 curated 檔(人工標籤優先保留)。供前端持股分析顯示繁中名、adr_screen.disp() 對照。
CI 每次產生,不回 commit;抓取失敗則保留原 curated 檔不動。"""
import io
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FP = os.path.join(HERE, "universe", "tw_names.json")


def _get(url, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout).read().decode("utf-8", "ignore")


def _ok_code(c):
    return c.isdigit() and len(c) == 4


def fetch_all():
    out = {}
    try:                                                   # 上市
        for r in json.loads(_get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")):
            c, n = str(r.get("Code", "")).strip(), str(r.get("Name", "")).strip()
            if _ok_code(c) and n:
                out[c + ".TW"] = n
    except Exception as e:
        print("[tw_names] TWSE err:", e)
    try:                                                   # 上櫃
        for r in json.loads(_get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")):
            c = str(r.get("SecuritiesCompanyCode") or "").strip()
            n = str(r.get("CompanyName") or "").strip()
            if _ok_code(c) and n:
                out[c + ".TWO"] = n
    except Exception as e:
        print("[tw_names] TPEX err:", e)
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

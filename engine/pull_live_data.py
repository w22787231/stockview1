# -*- coding: utf-8 -*-
"""純前端部署用(web_only):不重算任何資料,直接從線上把整個 data 樹抓回來,
這樣只改 index.html / _worker.js 時也能部署,且不會讓站上資料消失。
頂層 JSON + 5 池 + 中文名 + ~1700 檔個股詳情,全部沿用線上既有版本。"""
import io
import os
import json
import urllib.request
import concurrent.futures

BASE = "https://stockview1.pages.dev"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STOCK = os.path.join(DATA, "stock")
UNIV = os.path.join(HERE, "universe")

# 前端會抓的頂層資料檔 + 5 個池(supply_chain 在 repo 內,不需抓)
TOP = ["macro", "capital", "calendar", "etf", "sentiment", "industry_pe",
       "tw_chain", "tw_themes", "index", "tw150", "ndx100", "sp500", "sp400", "sp600",
       "us5000", "tw_all", "strong"]


def _get(path, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(
        BASE + path, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout).read()


def _save(path, b):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "wb") as f:
        f.write(b)


def main():
    os.makedirs(DATA, exist_ok=True)
    ok = 0
    for name in TOP:
        try:
            _save(os.path.join(DATA, name + ".json"), _get("/data/" + name + ".json"))
            ok += 1
        except Exception as e:
            print("[pull] 略過 %s:%s" % (name, e))
    # 中文名:stage 步驟從 engine/universe/ 複製 → 兩處都存
    try:
        b = _get("/data/tw_names.json")
        _save(os.path.join(UNIV, "tw_names.json"), b)
        _save(os.path.join(DATA, "tw_names.json"), b)
        ok += 1
    except Exception as e:
        print("[pull] tw_names 失敗:", e)
    print("[pull] 頂層+池 %d 檔" % ok)
    # 個股詳情 stock/*(沿用線上)
    try:
        idx = _get("/data/stock/_index.json")
        _save(os.path.join(STOCK, "_index.json"), idx)
        syms = (json.loads(idx.decode("utf-8", "ignore")).get("syms")) or []

        def dl(s):
            fn = s.replace(".", "_").upper() + ".json"
            try:
                _save(os.path.join(STOCK, fn), _get("/data/stock/" + fn))
                return 1
            except Exception:
                return 0
        n = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            for r in ex.map(dl, syms):
                n += r
        print("[pull] 個股詳情 %d/%d 檔" % (n, len(syms)))
    except Exception as e:
        print("[pull] 個股 _index 失敗:", e)


if __name__ == "__main__":
    main()

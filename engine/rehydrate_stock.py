# -*- coding: utf-8 -*-
"""快速部署用:從線上沿用既有個股詳情 data/stock/*.json,免重跑 ~1700 檔 yfinance(那步約 40 分)。
讀線上 _index.json 取代號清單,平行下載各檔到本地 data/stock/。供 workflow 的 skip_stocks 模式。
失敗的檔略過(該股詳情頁暫缺,不影響整體部署)。"""
import concurrent.futures
import io
import json
import os
import urllib.request

BASE = "https://stockview1.pages.dev"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "stock")


def _get(path, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(
        BASE + path, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout).read()


def main():
    os.makedirs(OUT, exist_ok=True)
    try:
        idx_raw = _get("/data/stock/_index.json")
    except Exception as e:
        print("[rehydrate] 取 _index.json 失敗,放棄沿用:", e)
        return
    with io.open(os.path.join(OUT, "_index.json"), "wb") as f:
        f.write(idx_raw)
    syms = (json.loads(idx_raw.decode("utf-8", "ignore")).get("syms")) or []

    def dl(sym):
        fn = sym.replace(".", "_").upper() + ".json"
        try:
            b = _get("/data/stock/" + fn)
            with io.open(os.path.join(OUT, fn), "wb") as f:
                f.write(b)
            return True
        except Exception:
            return False

    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(dl, syms):
            ok += 1 if r else 0
    print("[rehydrate] 從線上沿用 %d/%d 檔個股詳情" % (ok, len(syms)))


if __name__ == "__main__":
    main()

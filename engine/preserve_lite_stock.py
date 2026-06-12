# -*- coding: utf-8 -*-
"""主流程全快照部署時,從 live 沿用 us5000/tw_all 的 Buy 股個股詳情 + 併入 _index。
這兩池的詳情由各自 lite workflow 產生;主流程不重產,只沿用,避免搜尋/點擊壞掉。
用法: cd engine && python preserve_lite_stock.py
"""
import json, io, os, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "stock")
BASE = "https://stockview1.pages.dev/data/stock/"

def _get(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()

def main():
    os.makedirs(OUT, exist_ok=True)
    syms = set()
    for pool in ("us5000", "tw_all"):
        fp = os.path.join(DATA, pool + ".json")
        try:
            cs = json.load(io.open(fp, encoding="utf-8"))["cross_signals"]
            syms |= {r["sym"] for r in cs["golden"] + cs["death"]}
        except Exception as e:
            print(f"[lite-stock] skip {pool}: {e}")
    got = []
    for s in syms:
        fn = s.replace(".", "_").upper() + ".json"
        try:
            open(os.path.join(OUT, fn), "wb").write(_get(BASE + fn))
            got.append(s.upper())
        except Exception:
            pass
    ip = os.path.join(OUT, "_index.json")
    ex = []
    if os.path.exists(ip):
        try:
            ex = json.load(io.open(ip, encoding="utf-8")).get("syms", [])
        except Exception:
            ex = []
    json.dump({"syms": sorted(set(ex) | set(got))},
              io.open(ip, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[lite-stock] preserved {len(got)} details, index={len(set(ex) | set(got))}")

if __name__ == "__main__":
    main()

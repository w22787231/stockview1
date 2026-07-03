# -*- coding: utf-8 -*-
"""SPX 0DTE 占比(自算 proxy)→ data/0dte.json(每日自累積)。
抓取失敗 → 不覆寫(沿用線上)。CI 乾淨 checkout 從線上回讀當基準,才能跨日累積。
用法:cd engine && python export_0dte.py"""
import os, json, datetime, urllib.request
import fetch_0dte as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "0dte.json")
LIVE = "https://stockview1.pages.dev/data/0dte.json"


def _load_old():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:  # CI 乾淨 checkout:從線上回讀,才能跨日累積
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0 Chrome/124"})
        old = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        print("[0dte] 本機無檔,改用線上 0dte.json 當基準(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[0dte] 線上回讀失敗,視為首次:", e)
        return None


def main():
    today = datetime.date.today().isoformat()
    print("=== 抓取 SPX 0DTE 占比(自算) ===", flush=True)
    r = F.build_live(today)
    if not r:
        print("[!] 抓取失敗/無量(可能休市)→ 不覆寫 0dte.json,保留上次資料")
        return
    old = _load_old()
    j = F.build_0dte_json(old, today, r)
    if j.get("current_pct") is None:
        print("[!] 無當前值 → 不覆寫")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    print("✓ 0dte.json 已更新:as_of %s 近端到期 %s(dte=%s)0DTE 占比(自算)=%s%%,序列 %d 點"
          % (j["as_of"], j["nearest_exp"], j["dte"], j["current_pct"],
             len(j["series"]["dates"])))


if __name__ == "__main__":
    main()

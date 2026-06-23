# engine/export_spec.py
# -*- coding: utf-8 -*-
"""投機交易指標 + 投機溫度 → data/spec.json。全失敗則沿用線上(不覆寫成壞檔)。
用法:cd engine && PYTHONUTF8=1 python export_spec.py"""
import os, io, sys, json, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_spec as S

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "spec.json")
WEIGHTS = {k: 1.0 for k in S.SOURCE_KEYS}

def _preserve():
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            "https://stockview1.pages.dev/data/spec.json", headers={"User-Agent":"Mozilla/5.0"}), timeout=20).read()
        obj = json.loads(b.decode("utf-8-sig", "ignore"))
        if not isinstance(obj, dict) or "temperature" not in obj:
            raise ValueError("非預期 spec.json")
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with io.open(OUT, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print("[spec] 沿用線上 spec.json")
    except Exception as e:
        print("[spec] 線上沿用也失敗(首次?):", e)

def main():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (datetime.date.today() - datetime.timedelta(days=365*12)).isoformat()
    try:
        res = S.assemble_spec_raw(start)
    except Exception as e:
        print("[spec] assemble 例外:", e); res = None
    if res is None:
        print("[!] 投機資料不足 → 不覆寫"); _preserve(); return
    sources, cards, context, sp500 = res
    try:
        j = S.build_spec_json(sources, cards, context, WEIGHTS, today, sp500=sp500)
    except Exception as e:
        print("[!] 計算失敗:", e); _preserve(); return
    if not j["temperature"]["series"]["dates"]:
        print("[!] 無有效序列 → 不覆寫"); _preserve(); return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, separators=(",", ":"))
    byw = j["temperature"].get("by_window", {})
    dfw = j["temperature"].get("default_window", "5y")
    cur = (byw.get(dfw) or {}).get("current")
    zbw = j["temperature"]["series"].get("z_by_window", {})
    win_lens = {w: len(v) for w, v in zbw.items()}
    print("✓ spec.json:溫度(%s)=%s,%d 週點,%d 卡,各窗長度=%s" % (
        dfw, cur, len(j["temperature"]["series"]["dates"]), len(j["indicators"]), win_lens))

if __name__ == "__main__":
    main()

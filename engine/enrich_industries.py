# -*- coding: utf-8 -*-
"""本地補抓 strong.json / strong_tw.json 的 sector_zh + industry_zh。
yfinance 在本機比 CI 可靠得多。跑完直接存回 data/ 目錄,再 trigger web deploy。
用法: cd engine && python enrich_industries.py
"""
import sys, os, io, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
sys.path.insert(0, HERE)

from patch_lite_sector import SECTOR_ZH, INDUSTRY_ZH

import warnings; warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("pip install yfinance")

from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_one(sym):
    try:
        info = yf.Ticker(sym).info or {}
        sec = info.get("sector"); ind = info.get("industry")
        return sym, {
            "sector_zh": SECTOR_ZH.get(sec, sec) if sec else None,
            "industry_zh": INDUSTRY_ZH.get(ind, ind) if ind else None,
        }
    except Exception:
        return sym, {}

def enrich(fname):
    fp = os.path.join(DATA, fname)
    if not os.path.exists(fp):
        print(f"[skip] {fname} 不存在"); return
    d = json.load(io.open(fp, encoding="utf-8"))
    rows = d.get("rows", [])
    need = [r["sym"] for r in rows if not r.get("industry_zh")]
    print(f"{fname}: {len(rows)} 檔候選, {len(need)} 缺 industry_zh -> 開始抓...")
    if not need:
        print("  全部已有 industry_zh"); return
    done = 0
    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, s): s for s in need}
        for fut in as_completed(futs):
            sym, info = fut.result()
            if info.get("sector_zh") or info.get("industry_zh"):
                results[sym] = info
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(need)} ({len(results)} 有資料)...", flush=True)
    n_sec = n_ind = 0
    for r in rows:
        if r["sym"] in results:
            if not r.get("sector_zh") and results[r["sym"]].get("sector_zh"):
                r["sector_zh"] = results[r["sym"]]["sector_zh"]; n_sec += 1
            if not r.get("industry_zh") and results[r["sym"]].get("industry_zh"):
                r["industry_zh"] = results[r["sym"]]["industry_zh"]; n_ind += 1
    json.dump(d, io.open(fp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"  -> 完成: sector +{n_sec}, industry +{n_ind}, 總 {sum(1 for r in rows if r.get('industry_zh'))}/{len(rows)} 有 industry_zh")

if __name__ == "__main__":
    enrich("strong.json")
    enrich("strong_tw.json")
    print("Done.")

# -*- coding: utf-8 -*-
"""同業 PE 中位數匯出 → ../data/industry_pe.json。
讀已生成的 data/stock/*.json,依 metrics.industry 分組,算每產業 forwardPe(無則 pe)中位數。
持股分析的「同業PE」欄=該股 industry 對應的中位數。需在 export_stock 之後跑。
"""
import os, io, json, glob, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_DIR = os.path.join(HERE, "..", "data", "stock")
OUT = os.path.join(HERE, "..", "data", "industry_pe.json")
MIN_N = 3            # 一個產業至少 3 檔才採計中位數


def _num(x):
    try:
        f = float(x)
        return f if (f == f and 0 < f < 1000) else None    # 濾掉 NaN / 負 / 離譜值
    except Exception:
        return None


def build():
    groups = {}
    for fp in glob.glob(os.path.join(STOCK_DIR, "*.json")):
        try:
            m = (json.load(io.open(fp, encoding="utf-8")) or {}).get("metrics") or {}
        except Exception:
            continue
        ind = m.get("industry")
        pe = _num(m.get("forwardPe"))
        if pe is None:
            pe = _num(m.get("pe"))
        if ind and pe is not None:
            groups.setdefault(ind, []).append(pe)
    out = {}
    for ind, vals in groups.items():
        if len(vals) >= MIN_N:
            out[ind] = {"pe_med": round(statistics.median(vals), 1), "n": len(vals)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump({"industries": out}, f, ensure_ascii=False, separators=(",", ":"))
    print("[industry_pe] -> data/industry_pe.json  產業數 %d(來源 %d 檔)"
          % (len(out), sum(len(v) for v in groups.values())))


if __name__ == "__main__":
    build()

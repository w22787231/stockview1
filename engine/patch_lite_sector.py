# -*- coding: utf-8 -*-
"""把 lite 池 Buy 股的業務類別(中文 sector)寫進 data/<pool>.json 的 cross_signals 列。
讀各股已產生的 data/stock/<sym>.json 的 metrics.sector(英文)→中文,免重抓。
用法: cd engine && python patch_lite_sector.py <us5000|tw_all>
"""
import sys, json, io, os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STOCK = os.path.join(DATA, "stock")

SECTOR_ZH = {
    "Technology": "科技", "Information Technology": "科技",
    "Financial Services": "金融", "Financials": "金融",
    "Healthcare": "醫療保健", "Health Care": "醫療保健",
    "Consumer Cyclical": "非必需消費", "Consumer Discretionary": "非必需消費",
    "Consumer Defensive": "必需消費", "Consumer Staples": "必需消費",
    "Industrials": "工業",
    "Energy": "能源",
    "Basic Materials": "原物料", "Materials": "原物料",
    "Real Estate": "房地產",
    "Utilities": "公用事業",
    "Communication Services": "通訊服務",
}

def _sector_zh(sym):
    fp = os.path.join(STOCK, sym.replace(".", "_").upper() + ".json")
    try:
        sec = json.load(io.open(fp, encoding="utf-8")).get("metrics", {}).get("sector")
        return SECTOR_ZH.get(sec, sec) if sec else None
    except Exception:
        return None

def main():
    if len(sys.argv) < 2:
        print("用法: python patch_lite_sector.py <us5000|tw_all>"); raise SystemExit(1)
    pool = sys.argv[1]
    fp = os.path.join(DATA, pool + ".json")
    d = json.load(io.open(fp, encoding="utf-8"))
    cs = d.get("cross_signals", {})
    n = 0
    for r in cs.get("golden", []) + cs.get("death", []):
        z = _sector_zh(r["sym"])
        if z:
            r["sector_zh"] = z; n += 1
    json.dump(d, io.open(fp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"[sector] {pool}: 標了 {n} 檔業務類別")

    # us5000 順便補 strong.json:從個股詳情 metrics.sector 補上還沒有產業的強勢股(可靠來源)
    if pool == "us5000":
        sp = os.path.join(DATA, "strong.json")
        try:
            sd = json.load(io.open(sp, encoding="utf-8"))
            m = 0
            for r in sd.get("rows", []):
                if not r.get("sector_zh"):
                    z = _sector_zh(r["sym"])
                    if z:
                        r["sector_zh"] = z; m += 1
            json.dump(sd, io.open(sp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            print(f"[sector] strong.json: 補了 {m} 檔")
        except Exception as e:
            print("[sector] strong.json 略過:", e)

if __name__ == "__main__":
    main()

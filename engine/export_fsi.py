# -*- coding: utf-8 -*-
"""OFR 金融壓力指數 → data/fsi.json。
抓取全失敗 → 不覆寫(沿用線上,擋 Cloudflare HTML fallback)。
用法:cd engine && python export_fsi.py"""
import os, json, datetime
import fetch_fsi as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "fsi.json")


def main():
    today = datetime.date.today().isoformat()
    print("=== 抓取 OFR 金融壓力指數 ===", flush=True)
    j = None
    try:
        j = F.build_live(today)
    except Exception as e:
        print("[fsi] 抓取失敗:", e)
    # 驗證:必須是 dict 且 series.fsi 非空,才落盤(否則沿用線上)
    if not (isinstance(j, dict) and (j.get("series") or {}).get("fsi")):
        print("[!] FSI 抓取失敗或資料不足 → 不覆寫 fsi.json,保留上次資料")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    s = j["series"]
    print("✓ fsi.json 已更新:as_of %s FSI=%s(20MA=%s 50MA=%s)，序列 %d 點，末 S&P500=%s"
          % (j["as_of"], j["current"], j["ma20_last"], j["ma50_last"], len(s["dates"]), s["sp500"][-1]))


if __name__ == "__main__":
    main()

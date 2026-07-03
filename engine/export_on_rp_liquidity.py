# -*- coding: utf-8 -*-
"""Fed ON RP → data/on_rp_liquidity.json."""
import json
import os

import fetch_on_rp_liquidity as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "on_rp_liquidity.json")


def main():
    print("=== 抓取 Fed ON RP ===", flush=True)
    try:
        j = F.build_live()
    except Exception as e:
        print("[on-rp-liquidity] 抓取失敗:", e)
        raise SystemExit(1)
    s = j.get("series") or {}
    if not (s.get("dates") and s.get("value") and s.get("ma20") and s.get("ma60")):
        print("[on-rp-liquidity] 資料不足 → 不覆寫 on_rp_liquidity.json")
        raise SystemExit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, separators=(",", ":"))
    print("[on-rp-liquidity] -> data/on_rp_liquidity.json as_of=%s value=%s points=%d"
          % (j.get("as_of"), j.get("current"), len(s.get("dates") or [])))


if __name__ == "__main__":
    main()

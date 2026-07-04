# -*- coding: utf-8 -*-
"""Chicago Fed NFCI + S&P 500 → data/chicago_fci.json."""
import json
import os

import fetch_chicago_fci as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "chicago_fci.json")


def main():
    print("=== 抓取 Chicago Fed NFCI + S&P 500 ===", flush=True)
    try:
        j = F.build_live()
    except Exception as e:
        print("[chicago-fci] 抓取失敗:", e)
        raise SystemExit(1)
    s = j.get("series") or {}
    if not (s.get("dates") and s.get("nfci") and s.get("sp500") and any(v is not None for v in s.get("sp500"))):
        print("[chicago-fci] 資料不足 → 不覆寫 chicago_fci.json")
        raise SystemExit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, separators=(",", ":"))
    print("[chicago-fci] -> data/chicago_fci.json as_of=%s NFCI=%s points=%d"
          % (j.get("as_of"), j.get("current"), len(s.get("dates") or [])))


if __name__ == "__main__":
    main()

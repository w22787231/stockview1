# -*- coding: utf-8 -*-
"""聰明錢主程式：呼叫四個 fetch_*，彙整後寫 data/smartmoney.json。

執行方式（Windows）：
    cd engine
    set PYTHONUTF8=1
    set SEC_UA=stockview research test@example.com
    python export_smartmoney.py

全部來源失敗時，保留現有 JSON 不覆寫（印出提示訊息）。
"""
import json
import os
import sys
from datetime import datetime, timezone

# 確保同層的 fetch_smartmoney 可被 import（無論從哪個目錄執行）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from fetch_smartmoney import (
    fetch_openinsider,
    fetch_congress,
    fetch_edgar,
    fetch_finra,
    build_json,
)

# data/ 目錄在 engine/ 的上一層
_DATA_DIR = os.path.join(_HERE, "..", "data")
_OUTPUT = os.path.join(_DATA_DIR, "smartmoney.json")


def main():
    print("=== export_smartmoney start ===")

    # ── 抓取四個來源（各自獨立，失敗回 None）──
    insider = fetch_openinsider()
    congress = fetch_congress()
    dgfilings = fetch_edgar()
    darkpool = fetch_finra()

    # ── 判斷是否全部失敗 ──
    all_failed = all(x is None for x in (insider, congress, dgfilings, darkpool))
    if all_failed:
        print("[export_smartmoney] 所有來源均失敗，保留現有 data/smartmoney.json 不覆寫")
        return

    # ── 成功來源統計 ──
    ok_sources = [
        name for name, val in [
            ("openinsider", insider),
            ("congress", congress),
            ("edgar", dgfilings),
            ("finra", darkpool),
        ]
        if val is not None
    ]
    print(f"[export_smartmoney] 成功來源: {', '.join(ok_sources)}")

    # ── 聚合 ──
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output = build_json(
        insider or [],
        congress or [],
        dgfilings or [],
        darkpool or {},
        updated,
    )

    # ── 寫出 JSON ──
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    stock_count = len(output.get("stocks", []))
    print(f"[export_smartmoney] 寫出 {_OUTPUT}")
    print(f"[export_smartmoney] updated={updated}, stocks={stock_count}")
    print("=== export_smartmoney done ===")


if __name__ == "__main__":
    main()

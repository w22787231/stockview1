# -*- coding: utf-8 -*-
import math
import sys

import export_daily_checklist as D

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def eq(actual, expected, label):
    if isinstance(expected, float):
        assert actual is not None and math.isclose(actual, expected, abs_tol=1e-9), label
    else:
        assert actual == expected, label


# 交易日中間缺值必須跳過，取上一筆有效觀測值，而不是把缺值當 0。
eq(D.change([1.0, None, 1.3, 1.5], 1), 0.2, "1D 應使用上一筆有效交易日")
eq(D.change([1.0, None, 1.3, 1.5], 5), None, "20D 前資料不足必須為 None")

# 相對強弱 = 資產報酬 - SPY 報酬，單位為百分點。
eq(D.relative_return([100, 110], [100, 105], 1), 5.0, "RSP/SPY 相對報酬計算錯誤")
eq(D.relative_return([100, None], [100, 105], 1), None, "缺最新資產價格不可產生相對強弱")

# bp 與比值口徑必須明確。
eq(D.to_bps(0.12), 12.0, "殖利率 0.12% 應轉 12bps")
eq(D.ratio(18.0, 20.0), 0.9, "VIX9D/VIX 比值計算錯誤")
eq(D.ratio(None, 20.0), None, "缺資料不可產生比值")

print("✅ test_daily_checklist 通過：交易日差、相對強弱、bps 與比值口徑")

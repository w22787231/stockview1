# -*- coding: utf-8 -*-
"""台股大盤融資維持率(上市)純計算/合併工具。
無網路、無重相依,供 export_sentiment.py 與 backfill_tw_margin_ratio.py 共用。
口徑:維持率% = Σ(融資餘額張 × 1000 × 收盤) / 上市融資金額(元) × 100,分子排除 ETF(00 開頭)。"""


def _to_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def compute_ratio(loan_yuan, lots_by_code, price_by_code, exclude_etf=True):
    """loan_yuan: 上市融資金額總額(元)。lots_by_code: {code: 融資餘額張}. price_by_code: {code: 收盤}."""
    loan = _to_float(loan_yuan)
    if not loan or loan <= 0:
        return None
    mv = 0.0
    for code, lots in lots_by_code.items():
        code = str(code).strip()
        if exclude_etf and code.startswith("00"):
            continue
        p = price_by_code.get(code)
        l = _to_float(lots)
        pf = _to_float(p)
        if pf and l:
            mv += l * 1000 * pf
    if mv <= 0:
        return None
    return round(mv / loan * 100, 2)


def merge_history(seed, prev, point, cap=750):
    """合併 種子 + 前版累積 + 今日點,以 YYYYMMDD 去重(後者覆蓋),排序,尾端裁 cap。
    seed/prev: {'dates':[],'ratio':[],'twii':[]} 或 None。point: {'date','ratio','twii'} 或 None。"""
    m = {}

    def _absorb(src):
        if not src:
            return
        ds = src.get("dates") or []
        rs = src.get("ratio") or []
        ts = src.get("twii") or []
        for i, d in enumerate(ds):
            cur = m.get(d, {})
            r = rs[i] if i < len(rs) else None
            t = ts[i] if i < len(ts) else None
            if r is not None:
                cur["ratio"] = r
            if t is not None:
                cur["twii"] = t
            m[d] = cur

    _absorb(seed)
    _absorb(prev)
    if point and point.get("date") and point.get("ratio") is not None:
        cur = m.get(point["date"], {})
        cur["ratio"] = point["ratio"]
        if point.get("twii") is not None:
            cur["twii"] = point["twii"]
        m[point["date"]] = cur

    dates = sorted(m.keys())[-cap:]
    ratio = [m[d].get("ratio") for d in dates]
    twii = [m[d].get("twii") for d in dates]
    return dates, ratio, twii

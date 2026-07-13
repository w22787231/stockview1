# -*- coding: utf-8 -*-
"""股票風險溢酬(ERP)純計算工具。無網路、無重相依。

ERP % = S&P500 盈餘殖利率(100 / Forward P/E) − 10年公債殖利率(DGS10,%)。
越高 = 股票相對債券越便宜(偏多股市);越低甚至轉負 = 股票相對債券越貴(偏空,常見於估值泡沫)。
"""


def value_at(day, dates, vals):
    """回傳「不晚於 day」的最近一筆值;day 早於序列最早日期 → None。"""
    out = None
    for d, v in zip(dates, vals):
        if d <= day:
            out = v
        else:
            break
    return out


def compute_erp(fwd_pe, dgs10):
    if not fwd_pe or fwd_pe <= 0 or dgs10 is None:
        return None
    return round(100.0 / fwd_pe - dgs10, 2)


def pick_by_date(dates, source_dates, source_vals):
    """依日期精確比對(非最近前值),把 source 序列重排成 dates 的順序;找不到 → None。
    用於已經同一批日期索引產生的資料(如 fwd_pe 的 dates/spy 本就同源對齊)。"""
    m = dict(zip(source_dates, source_vals))
    return [m.get(d) for d in dates]


def build_series(pe_dates, pe, yc_dates, yc_10y):
    """把(通常週頻的)fwd PE 序列對齊到(日頻的)10Y 殖利率序列,逐點算 ERP。
    yc_dates/yc_10y 需已按日期遞增排序。pe 日期早於 yc 最早日期的點會被跳過。"""
    dates, erp = [], []
    for d, p in zip(pe_dates, pe):
        y = value_at(d, yc_dates, yc_10y)
        if y is None:
            continue
        dates.append(d)
        erp.append(compute_erp(p, y))
    return dates, erp

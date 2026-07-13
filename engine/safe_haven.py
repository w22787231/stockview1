# -*- coding: utf-8 -*-
"""Safe Haven Demand(CNN Fear & Greed 子指標)純計算/對齊工具。無網路。

CNN 原始值 y = 股票(S&P500)相對公債(Treasury)的 20 日滾動報酬差(百分點)。
越高＝股票跑贏債券越多(風險偏好升溫/貪婪);越低甚至轉負＝資金湧向公債避險(恐懼)。
"""
import datetime


def value_at(day, dates, vals):
    """回傳「不晚於 day」的最近一筆值;day 早於序列最早日期 → None。"""
    out = None
    for d, v in zip(dates, vals):
        if d <= day:
            out = v
        else:
            break
    return out


def to_ymd(ms):
    """CNN 時間戳記(毫秒,UTC)→ 'YYYY-MM-DD'。"""
    return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def build_series(raw_points, gspc_dates, gspc_close):
    """raw_points: CNN safe_haven_demand.data 原始 [{'x':ms,'y':val}, ...]。
    CNN 當日常出現兩筆(收盤快照 + 尾盤即時值),日期截斷後依日期去重、後者覆蓋。
    回 (dates, y, sp500):sp500 對齊到 gspc 收盤(不晚於當日最近一筆,缺歷史 → None)。"""
    m = {}
    for p in raw_points or []:
        x, v = p.get("x"), p.get("y")
        if x is None or v is None:
            continue
        m[to_ymd(x)] = round(float(v), 2)
    dates = sorted(m.keys())
    y = [m[d] for d in dates]
    sp500 = [value_at(d, gspc_dates, gspc_close) for d in dates]
    return dates, y, sp500

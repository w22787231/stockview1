# -*- coding: utf-8 -*-
"""台股產業鏈漲跌與資金流向匯出。
讀 universe/tw_chain.json（純分類結構），抓每檔 1/5/20 日漲跌、量比，
判定資金流向，輸出 ../data/tw_chain.json（並同步 ../web/data/ 供本機預覽）。

資金流向 flow（與爆量榜 volrCls 同口徑，門檻 1.5/0.7）：
  volr>=1.5 且 r1>0  -> inflow  (🟢 資金流入)
  volr>=1.5 且 r1<0  -> outflow (🔴 爆量出貨)
  volr<0.7           -> quiet   (⚪ 縮量觀望)
  其餘               -> neutral (◯ 量平)
  volr 或 r1 為 None -> None

用法: python export_chain.py
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")

CHAIN_DEF = os.path.join(HERE, "universe", "tw_chain.json")
DATA_DIR = os.path.join(HERE, "..", "data")
WEB_DATA_DIR = os.path.join(HERE, "..", "web", "data")


def _safe(x):
    try:
        f = float(x)
        return None if (f != f) else f
    except Exception:
        return None


def _round(x, n=2):
    v = _safe(x)
    return round(v, n) if v is not None else None


def ret_n(closes, n):
    """近 n 日報酬% = (最後 / 第 n+1 個前) - 1。"""
    if len(closes) < n + 1:
        return None
    a, b = closes[-1], closes[-1 - n]
    if b in (0, None):
        return None
    return (a / b - 1.0) * 100.0


def flow_of(volr, r1):
    """資金流向判定。volr=量比, r1=當日漲跌%。回傳 inflow/outflow/quiet/neutral 或 None。"""
    if volr is None or r1 is None:
        return None
    if volr >= 1.5 and r1 > 0:
        return "inflow"
    if volr >= 1.5 and r1 < 0:
        return "outflow"
    if volr < 0.7:
        return "quiet"
    return "neutral"


def merge_quotes(member, q):
    """把行情 dict q 併入 member（保留 sym/name/tags/note），回傳新 dict。
    q 為 None（抓取失敗）時所有行情欄位填 None。"""
    out = {"sym": member.get("sym"), "name": member.get("name", "")}
    if member.get("tags"):
        out["tags"] = member["tags"]
    if member.get("note"):
        out["note"] = member["note"]
    if q:
        out["last"] = _round(q.get("last"), 2)
        out["r1"] = _round(q.get("r1"), 2)
        out["r5"] = _round(q.get("r5"), 2)
        out["r20"] = _round(q.get("r20"), 2)
        out["volr"] = _round(q.get("volr"), 2)
        out["flow"] = flow_of(q.get("volr"), q.get("r1"))
    else:
        out["last"] = out["r1"] = out["r5"] = out["r20"] = out["volr"] = out["flow"] = None
    return out

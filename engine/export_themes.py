# -*- coding: utf-8 -*-
"""台股主題漲跌匯出。
讀 universe/tw_themes.json，抓每檔成分股的 1/5/20 日漲跌幅，
主題層級取成分股平均，輸出 ../data/tw_themes.json。

用法: python export_themes.py
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf

THEMES_FILE = os.path.join(HERE, "universe", "tw_themes.json")
DATA_DIR = os.path.join(HERE, "..", "data")


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


def fetch(symbols):
    df = yf.download(symbols, period="2mo", interval="1d",
                     group_by="ticker", progress=False, auto_adjust=False)
    out = {}
    for s in symbols:
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            closes = list(sub["Close"])
            vols = list(sub["Close"] * sub["Volume"])
            if len(closes) < 2:
                out[s] = None
                continue
            out[s] = {
                "last": _safe(closes[-1]),
                "r1": ret_n(closes, 1), "r5": ret_n(closes, 5), "r20": ret_n(closes, 20),
                "dv": _safe(sum(vols[-20:]) / min(20, len(vols))) if vols else None,
            }
        except Exception:
            out[s] = None
    return out


def avg(vals):
    xs = [v for v in vals if v is not None]
    return (sum(xs) / len(xs)) if xs else None


def build():
    spec = json.load(io.open(THEMES_FILE, encoding="utf-8"))
    all_syms = []
    for grp in spec["groups"]:
        for th in grp["themes"]:
            for m in th["members"]:
                if m.get("sym"):
                    all_syms.append(m["sym"])
    all_syms = sorted(set(all_syms))
    px = fetch(all_syms)

    groups_out, failed = [], []
    for grp in spec["groups"]:
        themes_out = []
        for th in grp["themes"]:
            members = []
            for m in th["members"]:
                s = m.get("sym")
                d = px.get(s) if s else None
                if not d:
                    if s:
                        failed.append(s)
                    continue
                members.append({
                    "sym": s, "name": m.get("name", ""),
                    "last": _round(d["last"], 2),
                    "r1": _round(d["r1"], 2), "r5": _round(d["r5"], 2), "r20": _round(d["r20"], 2),
                })
            # 主題層級 = 成分股平均
            themes_out.append({
                "name": th["name"], "desc": th.get("desc", ""),
                "n": len(members),
                "r1": _round(avg([x["r1"] for x in members]), 2),
                "r5": _round(avg([x["r5"] for x in members]), 2),
                "r20": _round(avg([x["r20"] for x in members]), 2),
                "members": members,
            })
        # 主題依今日平均漲跌排序
        themes_out.sort(key=lambda t: (t["r1"] if t["r1"] is not None else -999), reverse=True)
        groups_out.append({"group": grp["group"], "themes": themes_out})

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily)",
        "updated_list": spec.get("_updated", ""),
        "groups": groups_out,
        "failed": sorted(set(failed)),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(os.path.join(DATA_DIR, "tw_themes.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    nth = sum(len(g["themes"]) for g in groups_out)
    print(f"[themes] -> data/tw_themes.json  ({len(groups_out)} 大類, {nth} 主題, 失敗 {len(set(failed))})")
    if failed:
        print("[themes] 失敗:", ", ".join(sorted(set(failed))))


if __name__ == "__main__":
    build()

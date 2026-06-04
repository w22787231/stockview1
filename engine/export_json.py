# -*- coding: utf-8 -*-
"""trend 模式 JSON 匯出器。
重用 adr_screen.py 的 compute_trend()（同一份計算引擎，口徑完全一致），
把五段結果序列化成 JSON 給網頁讀。不改動 adr_screen.py。

用法:
  python export_json.py <pool> [TopN]      單池
  python export_json.py all [TopN]         全部 5 池，各輸出一檔

輸出: ../data/<pool>.json  與彙整 ../data/index.json
"""
import sys, os, io, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import adr_screen as eng  # 同資料夾的引擎

DATA_DIR = os.path.join(HERE, "..", "data")
POOLS = ["tw150", "ndx100", "sp500", "sp400", "sp600"]


def _round(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return None


def _name(sym):
    """台股回中文名，美股回 None。"""
    return eng._TW_NAMES.get(sym)


def build_rankings(rows, topn):
    """複刻 render_turn_strong 的 A/B/E3 排序 + 差異判讀，輸出結構化資料。"""
    if not rows:
        return {}
    K = min(20, len(rows))
    A = sorted(rows, key=lambda r: r["e5"] - r["e20"], reverse=True)[:K]
    B = sorted(rows, key=lambda r: 2*(r["e5"]-r["e10"]) + (r["e10"]-r["e20"]),
               reverse=True)[:K]
    E3 = sorted(rows, key=lambda r: r["e3"], reverse=True)[:K]

    sa = [r["sym"] for r in A]
    sb = [r["sym"] for r in B]
    both = [s for s in sa if s in sb]
    only_a = [s for s in sa if s not in sb]
    only_b = [s for s in sb if s not in sa]

    def row_a(r):
        return {"sym": r["sym"], "name": _name(r["sym"]),
                "e5": _round(r["e5"], 2), "e20": _round(r["e20"], 2),
                "A": _round(r["e5"] - r["e20"], 2)}

    def row_b(r):
        b = 2*(r["e5"]-r["e10"]) + (r["e10"]-r["e20"])
        return {"sym": r["sym"], "name": _name(r["sym"]),
                "e5": _round(r["e5"], 2), "e10": _round(r["e10"], 2),
                "e20": _round(r["e20"], 2), "B": _round(b, 2)}

    def row_e3(r):
        f5 = "up" if r["e3"] > r["e5"] else ("down" if r["e3"] < r["e5"] else "flat")
        f10 = "up" if r["e3"] > r["e10"] else ("down" if r["e3"] < r["e10"] else "flat")
        return {"sym": r["sym"], "name": _name(r["sym"]),
                "e3": _round(r["e3"], 2), "e5": _round(r["e5"], 2),
                "e10": _round(r["e10"], 2), "e20": _round(r["e20"], 2),
                "flag_3v5": f5, "flag_3v10": f10}

    return {
        "turn_strong_A": [row_a(r) for r in A],
        "turn_strong_B": [row_b(r) for r in B],
        "earliest_ignition": [row_e3(r) for r in E3],
        "diff": {"both": both, "only_a": only_a, "only_b": only_b},
    }


def build_main(rows, topn):
    """主表：依 Score 排序（與 render_trend has_full 分支一致）。"""
    main_rows = sorted(rows, key=lambda r: r["score"], reverse=True)[:topn]
    out = []
    for i, r in enumerate(main_rows, 1):
        out.append({
            "rank": i, "sym": r["sym"], "name": _name(r["sym"]),
            "e3": _round(r["e3"], 2), "e5": _round(r["e5"], 2),
            "e10": _round(r["e10"], 2), "e20": _round(r["e20"], 2),
            "r5": _round(r["r5"], 1), "sc5": _round(r["sc5"], 0),
            "a5": _round(r["a5"], 1), "a10": _round(r["a10"], 1),
            "a20": _round(r["a20"], 1), "ad520": _round(r["ad520"], 1),
            "dv": _round(r["dv"], 0), "score": _round(r["score"], 0),
            "trend": eng._eff_trend(r["e5"], r["e10"], r["e20"]),
            "cur": r["cur"],
        })
    return main_rows, out


def build_cross_filter(rows, main_rows, topn):
    """交叉過濾：全池 5日評分>=80 依 Score 排序，標 [Top內]/[補進]。"""
    top_syms = set(r["sym"] for r in main_rows)
    strong = sorted([r for r in rows if r["sc5"] >= 80],
                    key=lambda r: r["score"], reverse=True)
    out = []
    for i, r in enumerate(strong, 1):
        out.append({
            "rank": i, "sym": r["sym"], "name": _name(r["sym"]),
            "sc5": _round(r["sc5"], 0), "r5": _round(r["r5"], 1),
            "e5": _round(r["e5"], 2), "e20": _round(r["e20"], 2),
            "a20": _round(r["a20"], 1), "dv": _round(r["dv"], 0),
            "score": _round(r["score"], 0),
            "scope": "in_top" if r["sym"] in top_syms else "added",
            "trend": eng._eff_trend(r["e5"], r["e10"], r["e20"]),
            "cur": r["cur"],
        })
    return out


def run_pool(pool, topn):
    symbols = eng.load_pool(pool)
    if symbols is None:
        raise SystemExit(f"找不到池清單: {pool}")
    rows, failed = eng.compute_trend(symbols)
    main_rows, main = build_main(rows, topn)
    payload = {
        "pool": pool,
        "pool_label": pool.upper(),
        "topn": topn,
        "n_list": len(symbols),
        "n_ok": len(rows),
        "currencies": sorted(set(r["cur"] for r in rows)),
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily)",
        "main": main,
        "cross_filter": build_cross_filter(rows, main_rows, topn),
        "rankings": build_rankings(rows, topn),
        "failed": [{"sym": s, "why": why} for s, why in failed],
    }
    return payload


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python export_json.py <pool|all> [TopN]")
        raise SystemExit(1)
    target = args[0].lower()
    topn = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50

    os.makedirs(DATA_DIR, exist_ok=True)
    pools = POOLS if target == "all" else [target]

    index = {"pools": [], "topn": topn,
             "generated_at": datetime.datetime.now(datetime.timezone.utc)
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}

    for p in pools:
        print(f"[export] {p} ...", flush=True)
        try:
            payload = run_pool(p, topn)
        except Exception as e:
            print(f"[export] {p} FAILED: {e!r}", flush=True)
            continue
        fp = os.path.join(DATA_DIR, f"{p}.json")
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        print(f"[export] -> data/{p}.json  ({payload['n_ok']}/{payload['n_list']} ok, "
              f"{len(payload['failed'])} failed)", flush=True)
        index["pools"].append({
            "pool": p, "label": p.upper(),
            "n_ok": payload["n_ok"], "n_list": payload["n_list"],
            "currencies": payload["currencies"],
            "generated_at": payload["generated_at"],
        })

    with io.open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[export] -> data/index.json  ({len(index['pools'])} pools)", flush=True)


if __name__ == "__main__":
    main()

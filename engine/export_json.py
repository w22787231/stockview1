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
import warnings
warnings.filterwarnings("ignore")
import adr_screen as eng  # 同資料夾的引擎
import yfinance as yf

DATA_DIR = os.path.join(HERE, "..", "data")
POOLS = ["tw150", "ndx100", "sp500", "sp400", "sp600"]
MA_SHORT, MA_LONG = 20, 60   # 與技術線圖 ChartArt MA交叉指標一致(EMA20/60)


def _ema_arr(closes, n):
    out = [None] * len(closes)
    if len(closes) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(closes[:n]) / n
    out[n - 1] = e
    for i in range(n, len(closes)):
        e = closes[i] * k + e * (1 - k)
        out[i] = e
    return out


def _golden_backtest_swing(closes):
    """EMA20×EMA60 黃金交叉(Buy)進、死亡交叉(Sell)出的完整波段回測。回傳統計 dict 或 None。
    口徑：交叉隔日進場、下次反向交叉隔日出場(避免未來函數)；未平倉那筆另記。"""
    n = len(closes)
    if n < MA_LONG + 25:
        return None
    se = _ema_arr(closes, MA_SHORT); le = _ema_arr(closes, MA_LONG)

    def ma(i, w):
        return se[i] if w == MA_SHORT else le[i]

    crosses = []
    for i in range(1, n):
        ps, pl, cs, cl = ma(i-1, MA_SHORT), ma(i-1, MA_LONG), ma(i, MA_SHORT), ma(i, MA_LONG)
        if None in (ps, pl, cs, cl):
            continue
        if (ps - pl) <= 0 and (cs - cl) > 0:
            crosses.append((i, "g"))
        elif (ps - pl) >= 0 and (cs - cl) < 0:
            crosses.append((i, "d"))

    rets, hold = [], []
    in_pos, entry_i, open_ret = False, None, None
    for (idx, typ) in crosses:
        if typ == "g" and not in_pos:
            entry_i = idx + 1
            if entry_i < n:
                in_pos = True
        elif typ == "d" and in_pos:
            x = idx + 1
            if x < n:
                e, xc = closes[entry_i], closes[x]
                if e and xc and e == e and xc == xc:
                    rets.append((xc / e - 1.0) * 100.0)
                    hold.append(x - entry_i)
            in_pos, entry_i = False, None
    if in_pos and entry_i is not None and entry_i < n:
        e = closes[entry_i]
        last = None
        for j in range(n-1, entry_i-1, -1):
            if closes[j] and closes[j] == closes[j]:
                last = closes[j]; break
        if e and e == e and last:
            open_ret = (last / e - 1.0) * 100.0

    if len(rets) < 3:
        return None
    rs = sorted(rets)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    avg_win = (sum(wins)/len(wins)) if wins else None
    avg_loss = (sum(losses)/len(losses)) if losses else None
    pl_ratio = (avg_win/abs(avg_loss)) if (avg_win is not None and avg_loss) else None
    return {"n": len(rets),
            "win_rate": round(len(wins)/len(rets)*100, 0),
            "avg": round(sum(rets)/len(rets), 1),
            "median": round(rs[len(rs)//2], 1),
            "best": round(max(rets), 1),
            "worst": round(min(rets), 1),
            "avg_win": round(avg_win, 1) if avg_win is not None else None,
            "avg_loss": round(avg_loss, 1) if avg_loss is not None else None,
            "pl_ratio": round(pl_ratio, 2) if pl_ratio is not None else None,
            "avg_hold": round(sum(hold)/len(hold), 0) if hold else None,
            "open_ret": round(open_ret, 1) if open_ret is not None else None}


def build_backtest_rankings(main_rows):
    """對主表股抓5年收盤、跑 MA10×MA50 金叉進死叉出的完整波段回測，回勝率前10 + 中位前10 + 平均前10。"""
    syms = [r["sym"] for r in main_rows]
    if not syms:
        return {}
    name = {r["sym"]: _name(r["sym"]) for r in main_rows}
    try:
        df = yf.download(syms, period="5y", interval="1d",
                         group_by="ticker", progress=False, auto_adjust=False)
    except Exception:
        return {}
    stats = []
    for s in syms:
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            closes = list(sub["Close"])
            bt = _golden_backtest_swing(closes)
            if bt:
                bt["sym"] = s
                bt["name"] = name.get(s)
                stats.append(bt)
        except Exception:
            continue
    if not stats:
        return {}
    by_win = sorted(stats, key=lambda x: (x["win_rate"], x["avg"]), reverse=True)[:10]
    by_med = sorted(stats, key=lambda x: (x["median"], x["win_rate"]), reverse=True)[:10]
    by_avg = sorted(stats, key=lambda x: (x["avg"], x["win_rate"]), reverse=True)[:10]
    return {"n_tested": len(stats), "by_win_rate": by_win,
            "by_median": by_med, "by_avg": by_avg}


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
            "dv": _round(r["dv"], 0), "volr": _round(r.get("volr"), 2),
            "score": _round(r["score"], 0),
            "cross_state": r.get("cross_state"), "cross_days": r.get("cross_days"),
            "trend": eng._eff_trend(r["e5"], r["e10"], r["e20"]),
            "cur": r["cur"],
        })
    return main_rows, out


def build_volume_surge(rows, topn):
    """今日爆量榜：依量比 volr(當日$Vol/20日均$Vol) 由高到低。
    超短期資金流向——抓今天突然放量的標的。附 5日漲%/效率5 看量價是否同向。"""
    surge = sorted([r for r in rows if r.get("volr") is not None],
                   key=lambda r: r["volr"], reverse=True)[:min(20, len(rows))]
    out = []
    for i, r in enumerate(surge, 1):
        out.append({
            "rank": i, "sym": r["sym"], "name": _name(r["sym"]),
            "volr": _round(r["volr"], 2),
            "dv1": _round(r.get("dv1"), 0), "dv": _round(r["dv"], 0),
            "r5": _round(r["r5"], 1), "e5": _round(r["e5"], 2),
            "sc5": _round(r["sc5"], 0), "cur": r["cur"],
        })
    return out


def _disp(sym):
    """美股回代號，台股回『代號 中文名』。"""
    nm = _name(sym)
    return f"{sym} {nm}" if nm else sym


def build_highlights(rows, main_rows, topn):
    """由數據自動歸納『快速重點』(複刻對話版邏輯，純規則、不靠 AI)。
    回傳 list of {type, label, syms, note}。前端依序顯示成卡片。"""
    if not rows:
        return []
    K = min(20, len(rows))
    top_syms = set(r["sym"] for r in main_rows)
    A = sorted(rows, key=lambda r: r["e5"] - r["e20"], reverse=True)[:K]
    B = sorted(rows, key=lambda r: 2*(r["e5"]-r["e10"]) + (r["e10"]-r["e20"]), reverse=True)[:K]
    sa = [r["sym"] for r in A]; sb = [r["sym"] for r in B]
    both = [s for s in sa if s in sb]
    E3 = sorted(rows, key=lambda r: r["e3"], reverse=True)[:K]
    by_sym = {r["sym"]: r for r in rows}

    out = []

    # ① 量大又方向最確定：交叉過濾(5日評分>=80) 且在主表 Top 內(量最大)
    strong = sorted([r for r in rows if r["sc5"] >= 80 and r["sym"] in top_syms],
                    key=lambda r: r["score"], reverse=True)
    if strong:
        out.append({
            "type": "strong", "label": "量大又方向最確定",
            "syms": [_disp(r["sym"]) for r in strong[:8]],
            "note": "交叉過濾 Top內、5日評分≥80 且 Score 最高——又強又有量。",
        })

    # ② 最確定剛轉強 A∩B
    if both:
        out.append({
            "type": "turn", "label": "最確定剛轉強 (A∩B)",
            "syms": [_disp(s) for s in both[:10]],
            "note": "A、B 兩定義都入榜＝又乾淨又剛加速，訊號最完整。",
        })

    # ③ 最早期點火：效率3 全榜中 3vs5 與 3vs10 皆▲(延續性最強)
    ign = []
    for r in E3:
        f5 = r["e3"] > r["e5"]; f10 = r["e3"] > r["e10"]
        if f5 and f10:
            ign.append(r["sym"])
    if ign:
        out.append({
            "type": "ignition", "label": "最早期點火 (效率3全榜▲▲延續最強)",
            "syms": [_disp(s) for s in ign[:8]],
            "note": "效率3 領先且 3vs5、3vs10 皆加速＝剛點火又仍在加速。3日樣本小，配合效率5/10 確認。",
        })

    # ④ 今日資金流入：量比高(>=1.5) 且 5日漲幅為正(量價同向)
    inflow = sorted([r for r in rows if r.get("volr", 0) >= 1.5 and r["r5"] > 0],
                    key=lambda r: r["volr"], reverse=True)
    if inflow:
        out.append({
            "type": "inflow", "label": "今日資金流入 (爆量+上漲)",
            "syms": [f"{_disp(r['sym'])}({r['volr']:.1f}×)" for r in inflow[:8]],
            "note": "量比≥1.5× 且 5日上漲＝量價同向，資金實質流入。爆量但下跌者不列入(可能出貨)。",
        })

    # ⑤ 極端值警示：效率5 絕對值過大(很可能單日跳空/極窄 ADR)
    extreme = [r for r in rows if abs(r["e5"]) >= 3.0]
    if extreme:
        extreme.sort(key=lambda r: abs(r["e5"]), reverse=True)
        out.append({
            "type": "warn", "label": "⚠️ 極端值留意",
            "syms": [f"{_disp(r['sym'])}(效率5={r['e5']:+.2f})" for r in extreme[:6]],
            "note": "效率5 絕對值≥3 多為單日跳空/極窄 ADR 造成，A/B 榜可能因此霸榜，需個別查財報事件，勿純看數字追高。",
        })

    return out


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


FRESH_CROSS_DAYS = 3  # 「剛觸發」窗口：cross_days <= 此值視為近期新交叉


def _cross_sort_key(r):
    """排序鍵：cross_days 小→前(None 墊底)、同天數 score 大→前。"""
    d = r.get("cross_days")
    days = d if d is not None else float("inf")
    return (days, -(r.get("score") or 0.0))


def _annotate_fresh_backtest(rows, downloader=None):
    """對指定 rows 抓5年收盤、跑金叉完整波段回測，把回測統計併回各列(in place):
    bt_win_rate(金叉勝率) / bt_avg(平均報酬) / bt_n(樣本數) /
    bt_avg_win(平均賺) / bt_avg_loss(平均賠) / bt_pl_ratio(賺賠比)。
    一次批次下載,downloader 供測試注入。"""
    syms = [r["sym"] for r in rows]
    if not syms:
        return
    dl = downloader or (lambda ss: yf.download(
        ss, period="5y", interval="1d", group_by="ticker",
        progress=False, auto_adjust=False))
    try:
        df = dl(syms)
    except Exception:
        return
    for r in rows:
        s = r["sym"]
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            bt = _golden_backtest_swing(list(sub["Close"]))
            if bt:
                r["bt_win_rate"] = bt["win_rate"]
                r["bt_avg"] = bt["avg"]
                r["bt_n"] = bt["n"]
                r["bt_avg_win"] = bt["avg_win"]
                r["bt_avg_loss"] = bt["avg_loss"]
                r["bt_pl_ratio"] = bt["pl_ratio"]
        except Exception:
            continue


def build_cross_signals(rows, downloader=None):
    """全池 EMA20×EMA60 交叉清單。把 compute_trend 的全池 rows 依交叉狀態分組。
    golden/death 各自依「越新觸發越前、同天數 Score 大→前」排序；
    cross_state 非 golden/death(資料不足)者略過。「剛觸發」由前端依 fresh_days 篩。
    「剛觸發」那幾檔(cross_days<=fresh_days)額外跑5年金叉回測，標 bt_win_rate/bt_avg/bt_n。"""
    def pack(r):
        return {"sym": r["sym"], "name": _name(r["sym"]),
                "cross_state": r.get("cross_state"),
                "cross_days": r.get("cross_days"),
                "sc5": _round(r.get("sc5"), 0), "r5": _round(r.get("r5"), 1),
                "score": _round(r.get("score"), 0),
                "e5": _round(r.get("e5"), 2), "e20": _round(r.get("e20"), 2),
                "a20": _round(r.get("a20"), 1), "cur": r.get("cur")}

    golden, death = [], []
    for r in rows:
        st = r.get("cross_state")
        if st == "golden":
            golden.append(pack(r))
        elif st == "death":
            death.append(pack(r))
    golden.sort(key=_cross_sort_key)
    death.sort(key=_cross_sort_key)
    # 全部金叉都標 5 年回測(勝率/平均賺/平均賠/賺賠比);死叉只標剛觸發(供🔥表)
    _annotate_fresh_backtest(golden, downloader=downloader)
    fresh_death = [r for r in death
                   if r["cross_days"] is not None and r["cross_days"] <= FRESH_CROSS_DAYS]
    _annotate_fresh_backtest(fresh_death, downloader=downloader)
    return {"fresh_days": FRESH_CROSS_DAYS,
            "golden": golden, "death": death,
            "n_golden": len(golden), "n_death": len(death)}


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
        "highlights": build_highlights(rows, main_rows, topn),
        "backtest_rank": build_backtest_rankings(main_rows),
        "cross_filter": build_cross_filter(rows, main_rows, topn),
        "cross_signals": build_cross_signals(rows),
        "volume_surge": build_volume_surge(rows, topn),
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

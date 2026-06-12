# -*- coding: utf-8 -*-
"""輕量金叉池匯出(us5000 / tw_all):1年日線→EMA20/60金叉→門檻→cross_signals(無回測)。
重用 adr_screen.compute_trend(分批) + export_json.build_cross_signals(offline downloader→不跑5年回測)。
不改動 export_json.run_pool / 40分流程。
用法: python export_lite_pool.py <us5000|tw_all>
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import adr_screen as eng
import export_json as ej

DATA_DIR = os.path.join(HERE, "..", "data")

PRESETS = {
    "us5000": {"label": "5000股",     "min_price": 5.0, "min_dolvol": 5e6, "cur": "USD", "buy_within": 5, "backtest": True},
    "tw_all": {"label": "台股全市場", "min_price": 0.0, "min_dolvol": 0.0, "cur": "TWD", "buy_within": 5, "backtest": True},
}

def _offline(syms):
    raise RuntimeError("lite pool: no 5y backtest")

# 強勢股篩選(對齊 TradingView Best-winners):價≥1、ADR≥4.5%、距52週低≥70%、
# 3M/6M/1Y 漲幅>0、30日均日成交額>50M、當日成交額>20M、EMA8≥EMA21、價>EMA60。
STRONG = {"min_price": 1.0, "min_adr": 4.5, "min_pal": 70.0,
          "min_dv30": 50e6, "min_dv1": 20e6}

def _is_strong(r):
    return (r.get("close", 0) >= STRONG["min_price"]
            and r.get("a20", 0) >= STRONG["min_adr"]
            and r.get("pal", -1) >= STRONG["min_pal"]
            and (r.get("p3m") or 0) > 0 and (r.get("p6m") or 0) > 0 and (r.get("p1y") or 0) > 0
            and r.get("dv30", 0) > STRONG["min_dv30"] and r.get("dv1", 0) > STRONG["min_dv1"]
            and r.get("up821") and r.get("abv60"))

def _write_strong(rows, out_dir):
    sel = [r for r in rows if _is_strong(r)]
    def _rs(r):  # 強度排序:3M+6M+1Y 漲幅合計
        return (r.get("p3m") or 0) + (r.get("p6m") or 0) + (r.get("p1y") or 0)
    sel.sort(key=_rs, reverse=True)
    out = []
    for r in sel:
        out.append({
            "sym": r["sym"], "name": r.get("name"),
            "close": round(r["close"], 2), "adr": round(r.get("a20", 0), 1),
            "pal": round(r.get("pal", 0), 0),
            "p3m": round(r.get("p3m") or 0, 1), "p6m": round(r.get("p6m") or 0, 1),
            "p1y": round(r.get("p1y") or 0, 1),
            "dv30": round(r.get("dv30", 0)), "dv1": round(r.get("dv1", 0)),
            "rs": round(_rs(r), 1),
            "cross_state": r.get("cross_state"), "buy_days": r.get("buy_days"),
            "cur": r.get("cur", "USD"),
        })
    payload = {
        "pool": "strong", "label": "強勢股", "lite": True,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filters": STRONG, "n": len(out), "rows": out,
    }
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, "strong.json")
    with io.open(fp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"[strong] -> {fp}  ({len(out)} 檔強勢股)", flush=True)

def run_lite_pool(pool, label, min_price=0.0, min_dolvol=0.0, default_cur="USD",
                  buy_within=0, backtest=False, symbols=None, compute=None, out_dir=None, batch=300,
                  strong=False):
    compute = compute or eng.compute_trend
    if symbols is None:
        symbols = eng.load_pool(pool)
        if symbols is None:
            raise SystemExit(f"找不到池清單: {pool}")
    rows, failed = [], []
    for i in range(0, len(symbols), batch):
        r, f = compute(symbols[i:i + batch], extra=strong) if strong else compute(symbols[i:i + batch])
        rows += r
        failed += f
        print(f"[lite:{pool}] {min(i + batch, len(symbols))}/{len(symbols)}", flush=True)
    rows = [r for r in rows
            if r.get("close", 1e18) >= min_price and r.get("dv", 0.0) >= min_dolvol]
    if strong:       # 強勢股篩選(TradingView Best-winners 條件)→ 另寫 strong.json(不受 buy_within 限制)
        _write_strong(rows, out_dir or DATA_DIR)
    if buy_within:   # 整池只留近 buy_within 天有 ChartArt Buy(交叉當根+收紅)
        rows = [r for r in rows
                if r.get("buy_days") is not None and r["buy_days"] <= buy_within]
    cs = ej.build_cross_signals(rows, downloader=(None if backtest else _offline))   # None=真下載跑5年回測; _offline=跳過
    payload = {
        "pool": pool, "pool_label": label, "lite": True, "buy_within": buy_within, "has_bt": bool(backtest),
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": ("yfinance (daily 1y" + (", ChartArt Buy<=%dd" % buy_within if buy_within else "") + ("" if backtest else ", no backtest") + ")"),
        "n_list": len(symbols), "n_ok": len(rows),
        "currencies": sorted(set(r["cur"] for r in rows)) or [default_cur],
        "cross_signals": cs,
        "failed": [{"sym": s, "why": w} for s, w in failed],
    }
    out_dir = out_dir or DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, f"{pool}.json")
    with io.open(fp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"[lite:{pool}] -> {fp}  ({payload['n_ok']}/{payload['n_list']} ok, "
          f"金叉{cs['n_golden']}/死叉{cs['n_death']})", flush=True)
    return payload

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in PRESETS:
        print("用法: python export_lite_pool.py <us5000|tw_all>")
        raise SystemExit(1)
    pool = sys.argv[1]
    p = PRESETS[pool]
    run_lite_pool(pool, p["label"], p["min_price"], p["min_dolvol"], p["cur"],
                  buy_within=p["buy_within"], backtest=p.get("backtest", False),
                  strong=(pool == "us5000"))   # 美股全市場順便產強勢股 strong.json

if __name__ == "__main__":
    main()

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
    "us5000": {"label": "5000股",     "min_price": 5.0, "min_dolvol": 5e6, "cur": "USD", "buy_within": 5},
    "tw_all": {"label": "台股全市場", "min_price": 0.0, "min_dolvol": 0.0, "cur": "TWD", "buy_within": 5},
}

def _offline(syms):
    raise RuntimeError("lite pool: no 5y backtest")

def run_lite_pool(pool, label, min_price=0.0, min_dolvol=0.0, default_cur="USD",
                  buy_within=0, symbols=None, compute=None, out_dir=None, batch=300):
    compute = compute or eng.compute_trend
    if symbols is None:
        symbols = eng.load_pool(pool)
        if symbols is None:
            raise SystemExit(f"找不到池清單: {pool}")
    rows, failed = [], []
    for i in range(0, len(symbols), batch):
        r, f = compute(symbols[i:i + batch])
        rows += r
        failed += f
        print(f"[lite:{pool}] {min(i + batch, len(symbols))}/{len(symbols)}", flush=True)
    rows = [r for r in rows
            if r.get("close", 1e18) >= min_price and r.get("dv", 0.0) >= min_dolvol]
    if buy_within:   # 整池只留近 buy_within 天有 ChartArt Buy(交叉當根+收紅)
        rows = [r for r in rows
                if r.get("buy_days") is not None and r["buy_days"] <= buy_within]
    cs = ej.build_cross_signals(rows, downloader=_offline)   # offline → 無 bt_ 欄
    payload = {
        "pool": pool, "pool_label": label, "lite": True, "buy_within": buy_within,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance (daily 1y, ChartArt Buy<=%dd, no backtest)" % buy_within if buy_within else "yfinance (daily 1y, no backtest)",
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
                  buy_within=p["buy_within"])

if __name__ == "__main__":
    main()

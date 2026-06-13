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

CAND_TOPN = 1000   # 候選池最多留 RS 前 1000(控 JSON 大小、確保產業涵蓋強者)

# 強勢股設定依幣別(美股以 USD、台股以 TWD;成交額數量級不同 → 門檻/單位分開)。
# defaults=前端預設篩選值(=原 TradingView 條件,使用者可調整/關閉);cand=候選池基底(永遠成立)。
def _strong_cfg(cur):
    if cur == "TWD":
        return {
            "file": "strong_tw.json", "label": "強勢股(台股)", "market": "tw", "cur": "TWD",
            "dv_unit": 1e8, "dv_suffix": "億",   # 前端輸入以「億 TWD」為單位
            "defaults": {"pal": 70, "adr": 4.5, "dv30": 5, "dv1": 2,
                         "p3m": 1, "p6m": 1, "p1y": 1, "ema": 1, "e60": 1, "buy": 0},
            "cand": {"min_price": 5.0, "min_bars": 230, "min_dv30": 2e8, "min_dv1": 5e7,
                     "min_adr": 3.0, "max_pal": 1500.0},
        }
    return {
        "file": "strong.json", "label": "強勢股(美股)", "market": "us", "cur": "USD",
        "dv_unit": 1e6, "dv_suffix": "M",      # 前端輸入以「M USD」為單位
        "defaults": {"pal": 70, "adr": 4.5, "dv30": 50, "dv1": 20,
                     "p3m": 1, "p6m": 1, "p1y": 1, "ema": 1, "e60": 1, "buy": 0},
        "cand": {"min_price": 1.0, "min_bars": 230, "min_dv30": 20e6, "min_dv1": 5e6,
                 "min_adr": 3.0, "max_pal": 1500.0},
    }

def _is_candidate(r, c):
    pal = r.get("pal", 0)
    return (r.get("close", 0) >= c["min_price"]
            and r.get("bars", 0) >= c["min_bars"] and r.get("lowok")
            and pal <= c["max_pal"]                          # 修分拆雜訊(SNDK +4939% 那種)
            and r.get("a20", 0) >= c["min_adr"]
            and r.get("dv30", 0) > c["min_dv30"] and r.get("dv1", 0) > c["min_dv1"]
            and r.get("p1y") is not None)

def _load_sector_cache(out_dir, fname):
    """重用上次 strong*.json 的 sector_zh 當快取(pull_live_data 會先把它拉回),只補抓新代號。"""
    try:
        old = json.load(io.open(os.path.join(out_dir, fname), encoding="utf-8"))
        return {x["sym"]: x.get("sector_zh") for x in old.get("rows", []) if x.get("sector_zh")}
    except Exception:
        return {}

def _load_industry_cache(out_dir, fname):
    """重用上次 strong*.json 的 industry_zh 當快取。"""
    try:
        old = json.load(io.open(os.path.join(out_dir, fname), encoding="utf-8"))
        return {x["sym"]: x.get("industry_zh") for x in old.get("rows", []) if x.get("industry_zh")}
    except Exception:
        return {}

def _fetch_sector_info(syms):
    """抓強勢股的粗/細產業(yfinance,平行)→中文 (sector_zh, industry_zh)。失敗則略過。"""
    if not syms:
        return {}
    try:
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor
        from patch_lite_sector import SECTOR_ZH, INDUSTRY_ZH
    except Exception:
        return {}
    out = {}
    def _one(s):
        try:
            info = yf.Ticker(s).info or {}
            sec = info.get("sector")
            ind = info.get("industry")
            sz = SECTOR_ZH.get(sec, sec) if sec else None
            iz = INDUSTRY_ZH.get(ind, ind) if ind else None
            return s, (sz, iz)
        except Exception:
            return s, (None, None)
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for s, (sz, iz) in ex.map(_one, syms):
                if sz or iz:
                    out[s] = (sz, iz)
    except Exception:
        pass
    return out

def _write_strong(rows, out_dir, cur):
    cfg = _strong_cfg(cur)
    cand_f, defs, unit = cfg["cand"], cfg["defaults"], cfg["dv_unit"]
    def _rs(r):  # 強度排序:3M+6M+1Y 漲幅合計
        return (r.get("p3m") or 0) + (r.get("p6m") or 0) + (r.get("p1y") or 0)
    cand = [r for r in rows if _is_candidate(r, cand_f)]
    cand.sort(key=_rs, reverse=True)
    cand = cand[:CAND_TOPN]
    # 產業:先用上次同檔當快取,只補抓還沒有的(每次最多 300,逐步收斂;CI yf.info 不穩故 best-effort)
    sec_cache = _load_sector_cache(out_dir, cfg["file"])
    ind_cache = _load_industry_cache(out_dir, cfg["file"])
    missing = [r["sym"] for r in cand if r["sym"] not in sec_cache and r["sym"] not in ind_cache][:300]
    for s, (sz, iz) in _fetch_sector_info(missing).items():
        if sz: sec_cache[s] = sz
        if iz: ind_cache[s] = iz
    out = []
    for r in cand:
        out.append({
            "sym": r["sym"], "name": r.get("name"),
            "sector_zh": sec_cache.get(r["sym"]), "industry_zh": ind_cache.get(r["sym"]),
            "close": round(r["close"], 2), "adr": round(r.get("a20", 0), 1),
            "pal": round(r.get("pal", 0), 0),
            "p3m": round(r.get("p3m") or 0, 1), "p6m": round(r.get("p6m") or 0, 1),
            "p1y": round(r.get("p1y") or 0, 1),
            "dv30": round(r.get("dv30", 0)), "dv1": round(r.get("dv1", 0)),
            "rs": round(_rs(r), 1),
            "up821": bool(r.get("up821")), "abv60": bool(r.get("abv60")),
            "cross_state": r.get("cross_state"), "buy_days": r.get("buy_days"),
            "cur": r.get("cur", cfg["cur"]),
        })
    payload = {
        "pool": cfg["market"], "label": cfg["label"], "market": cfg["market"], "cur": cfg["cur"], "lite": True,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "defaults": defs, "dv_unit": unit, "dv_suffix": cfg["dv_suffix"],
        "n": len(out), "rows": out,
    }
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, cfg["file"])
    with io.open(fp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    n_def = sum(1 for r in cand if (r.get("pal", 0) >= defs["pal"]
                and r.get("a20", 0) >= defs["adr"] and r.get("dv30", 0) > defs["dv30"] * unit
                and r.get("dv1", 0) > defs["dv1"] * unit and (r.get("p3m") or 0) > 0
                and (r.get("p6m") or 0) > 0 and (r.get("p1y") or 0) > 0 and r.get("up821") and r.get("abv60")))
    print(f"[strong] -> {fp}  (候選 {len(out)} 檔,預設條件命中 {n_def} 檔,細分產業 {sum(1 for r in out if r.get('industry_zh'))} 檔)", flush=True)

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
    if strong:       # 強勢股候選池(不受 buy_within 限制)→ 另寫 strong.json(美股)/ strong_tw.json(台股)
        _write_strong(rows, out_dir or DATA_DIR, default_cur)
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
                  strong=(pool in ("us5000", "tw_all")))   # 美股→strong.json、台股→strong_tw.json

if __name__ == "__main__":
    main()

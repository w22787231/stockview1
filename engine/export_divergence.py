# -*- coding: utf-8 -*-
"""個股二階導(效率背離)掃描匯出：股價還撐在高檔、但20日效率(單向性)已從近期高點明顯衰退。
重用 adr_screen.py 的下載/效率引擎(同一份計算口徑)，掃 tw150+sp500+ndx100 去重後的清單。
用法: python export_divergence.py
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")
import adr_screen as eng

DATA_DIR = os.path.join(HERE, "..", "data")
POOLS = ["tw150", "sp500", "ndx100"]
TOPN = 40           # 預設顯示前 N 檔(依衰退量排序)
EXPORT_CAP = 150    # 實際輸出到 JSON 的上限，讓前端搜尋能找到 40 名以外的個股


def main():
    symbols, seen = [], set()
    for p in POOLS:
        for s in (eng.load_pool(p) or []):
            if s not in seen:
                seen.add(s)
                symbols.append(s)

    rows, failed = eng.compute_divergence(symbols, lookback=60)

    out = []
    for r in rows[:EXPORT_CAP]:
        out.append({**r, "name": eng.disp(r["sym"]) if eng.is_tw(r["sym"]) else r["sym"]})

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pools": POOLS,
        "n_scanned": len(symbols) - len(failed),
        "n_flagged": len(rows),
        "topn": TOPN,
        "exported": len(out),
        "lookback_days": 60,
        "criteria": "peak_e20>=0.30 且 cur_e20<=peak_e20*0.5 且 現價>=波峰價*0.85 且 波峰後>=5個交易日",
        "rows": out,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    fp = os.path.join(DATA_DIR, "momentum_divergence.json")
    with io.open(fp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[divergence] 掃描 {len(symbols)} 檔，{len(rows)} 檔背離，輸出前 {len(out)} 檔 -> {fp}")


if __name__ == "__main__":
    main()

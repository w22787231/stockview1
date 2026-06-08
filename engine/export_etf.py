# -*- coding: utf-8 -*-
"""主動式 ETF 每日持股變化 → data/etf.json(留最近 30 個有變動的交易日)。
網站版:GitHub Actions 每天自抓自累積，與本機 etf_tool 脫鉤。
用法:cd engine && python export_etf.py
"""
import os, json, datetime
import fetch_etf as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "etf.json")
HISTORY_DAYS = 30
ACTION_KEEP = ("新增", "出清", "加碼", "減碼")


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def _to_map(rows):
    return {r["code"]: r for r in rows}


def compute_changes(cur, prev):
    """每檔 ETF 算變化。回傳 {etf: [change,...]}，含持平(由呼叫端 filter)。
    change: {etf,etf_name,code,name,action,dqty,qty,dweight,weight}。
    baseline: 僅當整個 prev 為 None/空(首次建立)才算「基準」;prev 存在但某檔空 → 該檔股票算新增。"""
    out = {}
    baseline = not prev
    for etf, rows in cur.items():
        cmap = _to_map(rows)
        pmap = _to_map(prev.get(etf, [])) if prev else {}
        name = F.ETFS.get(etf, {}).get("name", "")
        recs = []
        for code, r in cmap.items():
            cw, cq = _f(r["weight"]), _f(r["qty"])
            p = pmap.get(code)
            if baseline:
                action = "基準"
            elif p is None:
                action = "新增"
            else:
                dq = cq - _f(p["qty"])
                action = "加碼" if dq > 0 else ("減碼" if dq < 0 else "持平")
            pw = _f(p["weight"]) if p else 0.0
            pq = _f(p["qty"]) if p else 0.0
            recs.append({"etf": etf, "etf_name": name, "code": code, "name": r["name"],
                         "action": action, "dqty": int(cq - pq), "qty": int(cq),
                         "dweight": round(cw - pw, 2), "weight": cw})
        for code, p in pmap.items():
            if code not in cmap:
                recs.append({"etf": etf, "etf_name": name, "code": code, "name": p["name"],
                             "action": "出清", "dqty": -int(_f(p["qty"])), "qty": 0,
                             "dweight": -round(_f(p["weight"]), 2), "weight": 0.0})
        recs.sort(key=lambda x: x["weight"], reverse=True)
        out[etf] = recs
    return out


def merge_fetched(fetched, old_snapshot):
    """把今日抓到的持股與舊快照合併:某檔抓回空(失敗)→保留舊快照。
    全部失敗(都空)→回 None(呼叫端不覆寫)。"""
    if all(not rows for rows in fetched.values()):
        return None
    merged = {}
    for etf in F.ETFS:
        rows = fetched.get(etf, [])
        merged[etf] = rows if rows else old_snapshot.get(etf, [])
    return merged


def build_json(cur_snapshot, old_json, today):
    """用今日快照 + 舊 json 產新 json。純函式(不連網、不寫檔)，供測試。"""
    old_snap = (old_json or {}).get("snapshot") or {}
    history = list((old_json or {}).get("history") or [])
    changes = compute_changes(cur_snapshot, old_snap)
    day_changes = []
    for etf in F.ETFS:
        for c in changes.get(etf, []):
            if c["action"] in ACTION_KEEP:
                day_changes.append(c)
    existing_today = next((h for h in history if h.get("date") == today), None)
    history = [h for h in history if h.get("date") != today]
    if day_changes:
        history.insert(0, {"date": today, "changes": day_changes})
    elif existing_today is not None:
        history.insert(0, existing_today)
    history = history[:HISTORY_DAYS]
    return {
        "generated_at": today + "T00:00:00Z",
        "etfs": {e: {"name": F.ETFS[e]["name"]} for e in F.ETFS},
        "order": list(F.ETFS.keys()),
        "snapshot": cur_snapshot,
        "history": history,
    }


def main():
    today = datetime.date.today().isoformat()
    print("=== 抓取 5 檔 ETF 持股 ===", flush=True)
    fetched = F.fetch_all()
    old = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    if old is None:                              # CI 乾淨 checkout 無本機檔 → 從線上回讀,才能跨日累積異動 history
        try:
            import urllib.request
            old = json.loads(urllib.request.urlopen(urllib.request.Request(
                "https://stockview1.pages.dev/data/etf.json",
                headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore"))
            print("[etf] 本機無檔,改用線上 etf.json 當基準(history %d 日)" % len((old or {}).get("history") or []))
        except Exception as e:
            print("[etf] 線上回讀失敗,視為首次基準:", e)
            old = None
    old_snap = (old or {}).get("snapshot") or {}
    merged = merge_fetched(fetched, old_snap)
    if merged is None:
        print("[!] 5 檔全抓失敗 → 不覆寫 etf.json，保留上次資料")
        return
    j = build_json(merged, old, today)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    n_changes = len(j["history"][0]["changes"]) if (j["history"] and j["history"][0]["date"] == today) else 0
    print(f"✓ etf.json 已更新:今日 {n_changes} 筆變動，history {len(j['history'])} 日")


if __name__ == "__main__":
    main()

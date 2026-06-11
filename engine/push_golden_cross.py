# -*- coding: utf-8 -*-
"""收盤後偵測「全市場(各池)」當日新黃金交叉(EMA20×EMA60) → 發 Web Push 摘要通知。

資料流:
  - 各池 data/<pool>.json 的 cross_signals.golden 已含今日金叉(cross_days==0=今日觸發)。
  - 本腳本(GitHub Actions,收盤後、export 之後)讀本機 ../data/*.json,彙整今日新金叉,
    依「金叉評分」排序,組一則摘要,推播給 KV 內所有訂閱者。
  - 去重:KV 寫 gx:<sym>=<date>,同一檔同日只計一次(避免台股/美股兩次排程重複通知)。

訂閱由前端 POST /api/push/subscribe 寫入 KV(binding PUSH_SUBS)。
缺任一環境變數即 no-op,不影響其他部署步驟。
環境變數:CLOUDFLARE_API_TOKEN(KV 讀寫)、CLOUDFLARE_ACCOUNT_ID、PUSH_KV_ID、
         VAPID_PRIVATE_PEM、VAPID_SUBJECT。
"""
import os, json, glob, time, tempfile

API = "https://api.cloudflare.com/client/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def _need():
    g = lambda n: os.environ.get(n, "").strip()
    cfg = {"tok": g("CLOUDFLARE_API_TOKEN"), "acct": g("CLOUDFLARE_ACCOUNT_ID"),
           "kv": g("PUSH_KV_ID"), "pem": g("VAPID_PRIVATE_PEM"), "subj": g("VAPID_SUBJECT")}
    if not all(cfg.values()):
        print("[push] 缺環境變數(token/acct/PUSH_KV_ID/VAPID_*),跳過推播。")
        return None
    return cfg


def _score(r):
    """與前端 _crossBtScore 同公式(0~100):勝率30+賺賠比30+平均賺15+平均賠10+最差15,樣本折扣。"""
    n, wr = r.get("bt_n"), r.get("bt_win_rate")
    if n is None or wr is None:
        return None
    c = lambda x: 0.0 if x < 0 else (1.0 if x > 1 else x)
    win = c(wr / 100.0)
    pl = 0.0 if r.get("bt_pl_ratio") is None else c((r["bt_pl_ratio"] - 1) / 2.0)
    aw = 0.0 if r.get("bt_avg_win") is None else c(r["bt_avg_win"] / 20.0)
    al = 0.0 if r.get("bt_avg_loss") is None else c(1 - abs(r["bt_avg_loss"]) / 10.0)
    wo = 0.0 if r.get("bt_worst") is None else c(1 - abs(r["bt_worst"]) / 30.0)
    raw = 0.30 * win + 0.30 * pl + 0.15 * aw + 0.10 * al + 0.15 * wo
    return round(raw * (0.6 + 0.4 * c(n / 10.0)) * 100)


def _today_golden():
    """掃所有池 JSON,回今日新金叉(cross_days==0)清單,依評分高→低、去重(同 sym 取最高分)。"""
    best = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        cs = d.get("cross_signals")
        if not cs:
            continue
        for r in cs.get("golden", []):
            if r.get("cross_days") != 0:        # 只要今日剛觸發
                continue
            sym = r.get("sym")
            if not sym:
                continue
            sc = _score(r) or 0
            cur = best.get(sym)
            if cur is None or sc > cur[0]:
                best[sym] = (sc, r.get("name") or sym)
    rows = [(sym, sc, nm) for sym, (sc, nm) in best.items()]
    rows.sort(key=lambda x: -x[1])
    return rows


def _kv_list(cfg, sess):
    keys, cursor = [], None
    while True:
        url = f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/keys?prefix=sub:&limit=1000"
        if cursor:
            url += "&cursor=" + cursor
        j = sess.get(url, headers={"Authorization": "Bearer " + cfg["tok"]}, timeout=20).json()
        if not j.get("success"):
            print("[push] 讀 KV keys 失敗:", j.get("errors")); return keys
        keys += [k["name"] for k in j.get("result", [])]
        cursor = (j.get("result_info") or {}).get("cursor")
        if not cursor:
            break
    return keys


def _kv_get(cfg, sess, key):
    r = sess.get(f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/values/{key}",
                 headers={"Authorization": "Bearer " + cfg["tok"]}, timeout=20)
    if r.status_code != 200:
        return None
    try:
        return json.loads(r.text)
    except Exception:
        return r.text


def _kv_put(cfg, sess, key, val):
    try:
        sess.put(f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/values/{key}",
                 headers={"Authorization": "Bearer " + cfg["tok"]}, data=val.encode("utf-8"), timeout=20)
    except Exception:
        pass


def _kv_del(cfg, sess, key):
    try:
        sess.delete(f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/values/{key}",
                    headers={"Authorization": "Bearer " + cfg["tok"]}, timeout=20)
    except Exception:
        pass


_PEMPATH = None
def _pem_file(pem):
    global _PEMPATH
    if _PEMPATH is None:
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(pem); f.close()
        _PEMPATH = f.name
    return _PEMPATH


def _short(sym):
    return sym.replace(".TW", "").replace(".TWO", "")


def _host(url):
    try:
        return url.split("/")[2]
    except Exception:
        return "?"


def _device(ua):
    ua = ua or ""
    if "Android" in ua:
        return "Android"
    if "iPhone" in ua or "iPad" in ua or "iOS" in ua:
        return "iPhone/iPad"
    if "Windows" in ua:
        return "Windows"
    if "Macintosh" in ua or "Mac OS" in ua:
        return "Mac"
    return "其他/未知"


def _test_mode(cfg):
    """PUSH_TEST=1:不偵測金叉,直接發測試推播給所有訂閱者,印出服務商+狀態碼診斷。"""
    import requests
    from pywebpush import webpush, WebPushException
    sess = requests.Session()
    keys = _kv_list(cfg, sess)
    print(f"[push-test] 訂閱數:{len(keys)}")
    payload = json.dumps({"title": "股觀觀股 · 測試通知", "body": "這是一則測試推播,有收到代表推播設定成功 ✅", "url": "/?src=push#cross"})
    ok = 0
    for key in keys:
        rec = _kv_get(cfg, sess, key)
        sub = rec.get("subscription") if isinstance(rec, dict) else None
        if not sub:
            print(f"[push-test] {key}: 無 subscription,略過"); continue
        host = _host(sub.get("endpoint", ""))
        dev = _device(rec.get("ua", "")) if isinstance(rec, dict) else "?"
        try:
            r = webpush(subscription_info=sub, data=payload,
                        vapid_private_key=_pem_file(cfg["pem"]), vapid_claims={"sub": cfg["subj"]})
            print(f"[push-test] [{dev}] {host}: 狀態 {getattr(r,'status_code','?')} ✅"); ok += 1
        except WebPushException as e:
            sc = getattr(getattr(e, "response", None), "status_code", None)
            print(f"[push-test] [{dev}] {host}: 失敗 狀態={sc} {e}")
            if sc in (404, 410):
                _kv_del(cfg, sess, key); print(f"[push-test]   → 訂閱失效,已刪除")
    print(f"[push-test] 完成:成功送出 {ok}/{len(keys)}。(送出成功仍可能因裝置/SW/權限而沒跳)")


def main():
    cfg = _need()
    if not cfg:
        return
    import requests
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        print("[push] 缺 pywebpush,跳過:", e); return

    if os.environ.get("PUSH_TEST", "").strip() in ("1", "true", "yes"):
        _test_mode(cfg); return

    golden = _today_golden()
    print(f"[push] 今日全市場新金叉:{len(golden)} 檔")
    if not golden:
        print("[push] 今日無新金叉,不推播。"); return

    today = time.strftime("%Y-%m-%d")
    sess = requests.Session()
    keys = _kv_list(cfg, sess)
    print(f"[push] 訂閱數:{len(keys)}")
    if not keys:
        return

    def _strip(s):
        return s.upper().replace(".TW", "").replace(".TWO", "")

    sent = 0
    for key in keys:
        rec = _kv_get(cfg, sess, key)
        if not isinstance(rec, dict):
            continue
        sub = rec.get("subscription")
        if not sub:
            continue
        scope = rec.get("scope", "all")
        # 依 scope 取相關金叉
        if scope == "custom":
            wl = {_strip(c) for c in (rec.get("watchlist") or [])}
            relevant = [(s, sc, nm) for s, sc, nm in golden if _strip(s) in wl]
        else:
            relevant = list(golden)
        if not relevant:
            continue
        # 每訂閱各自去重(台股/美股兩排程同日不重複):pn:<hash> = {date, syms}
        mk = "pn:" + key[4:]
        prev = _kv_get(cfg, sess, mk)
        seen = set(prev.get("syms", [])) if isinstance(prev, dict) and prev.get("date") == today else set()
        fresh = [(s, sc, nm) for s, sc, nm in relevant if s not in seen]
        if not fresh:
            continue
        top = fresh[:6]
        names = "、".join(f"{nm}({_short(s)})" for s, sc, nm in top)
        more = f" 等 {len(fresh)} 檔" if len(fresh) > len(top) else ""
        scope_lab = "我的股池" if scope == "custom" else "全市場"
        title = f"股觀觀股 · {scope_lab}金叉"
        body = (f"{scope_lab}今日 {len(fresh)} 檔黃金交叉:{names}{more}"
                if len(fresh) > 1 else f"{top[0][2]}({_short(top[0][0])}) 出現黃金交叉")
        payload = json.dumps({"title": title, "body": body, "url": "/?src=push#cross"})
        try:
            webpush(subscription_info=sub, data=payload,
                    vapid_private_key=_pem_file(cfg["pem"]), vapid_claims={"sub": cfg["subj"]})
            sent += 1
            _kv_put(cfg, sess, mk, json.dumps({"date": today, "syms": list(seen | {s for s, _, _ in fresh})}))
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                _kv_del(cfg, sess, key)
            else:
                print("[push] 發送失敗:", e)
    print(f"[push] 已推播 {sent} 則。")


if __name__ == "__main__":
    main()

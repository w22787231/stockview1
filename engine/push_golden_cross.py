# -*- coding: utf-8 -*-
"""收盤後偵測「自訂股池」當日新黃金交叉(EMA20×EMA60) → 發 Web Push 通知。

資料流:
  - 訂閱由前端 POST /api/push/subscribe 寫入 Cloudflare KV(binding PUSH_SUBS)。
  - 本腳本(GitHub Actions,收盤後)用 Cloudflare API 讀 KV 所有 sub:* 訂閱,
    對每個訂閱的 watchlist 計算 EMA20/60,挑「最後一根剛金叉」者,發推播。
  - 去重:KV 寫 pn:<hash>:<sym>=<crossdate>,同一次金叉只推一次(best-effort)。

缺任一環境變數即直接結束(no-op),不影響其他部署步驟。
環境變數:CLOUDFLARE_API_TOKEN(需 KV 讀寫)、CLOUDFLARE_ACCOUNT_ID、PUSH_KV_ID、
         VAPID_PRIVATE_PEM、VAPID_SUBJECT。
"""
import os, json, sys, re, tempfile, time

API = "https://api.cloudflare.com/client/v4"


def _env(*names):
    return [os.environ.get(n, "").strip() for n in names]


def _need():
    tok, acct, kv, pem, subj = _env(
        "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "PUSH_KV_ID",
        "VAPID_PRIVATE_PEM", "VAPID_SUBJECT")
    if not (tok and acct and kv and pem and subj):
        print("[push] 缺環境變數(token/acct/PUSH_KV_ID/VAPID_*),跳過推播。")
        return None
    return {"tok": tok, "acct": acct, "kv": kv, "pem": pem, "subj": subj}


def _kv_list(cfg, sess):
    """列出所有 sub:* key。"""
    keys, cursor = [], None
    while True:
        url = f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/keys?prefix=sub:&limit=1000"
        if cursor:
            url += "&cursor=" + cursor
        r = sess.get(url, headers={"Authorization": "Bearer " + cfg["tok"]}, timeout=20)
        j = r.json()
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
        return None


def _kv_put(cfg, sess, key, val):   # best-effort 去重標記
    try:
        sess.put(f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/values/{key}",
                 headers={"Authorization": "Bearer " + cfg["tok"]}, data=val.encode("utf-8"), timeout=20)
    except Exception:
        pass


def _ema(vals, n):
    k = 2.0 / (n + 1)
    out, e = [None] * len(vals), None
    for i, v in enumerate(vals):
        if i < n - 1:
            continue
        if i == n - 1:
            e = sum(vals[:n]) / n
        else:
            e = v * k + e * (1 - k)
        out[i] = e
    return out


def _candidates(code):
    code = str(code).upper().strip()
    if re.fullmatch(r"\d{4,6}", code):
        return [code + ".TW", code + ".TWO"]
    return [code]


def _last_golden(closes):
    """回傳 (是否最後一根剛金叉, 名稱用收盤). EMA20 上穿 EMA60 於最後一根。"""
    if len(closes) < 65:
        return False
    s, l = _ema(closes, 20), _ema(closes, 60)
    n = len(closes)
    if s[n - 1] is None or l[n - 1] is None or s[n - 2] is None or l[n - 2] is None:
        return False
    return (s[n - 2] - l[n - 2]) <= 0 and (s[n - 1] - l[n - 1]) > 0


def main():
    cfg = _need()
    if not cfg:
        return
    import requests
    import yfinance as yf
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        print("[push] 缺 pywebpush,跳過:", e); return

    sess = requests.Session()
    keys = _kv_list(cfg, sess)
    print(f"[push] 訂閱數:{len(keys)}")
    if not keys:
        return
    subs = []
    allcodes = set()
    for k in keys:
        rec = _kv_get(cfg, sess, k)
        if rec and rec.get("subscription") and rec.get("watchlist"):
            subs.append((k, rec))
            allcodes.update(rec["watchlist"])
    if not subs:
        return

    # 解析代號 → 可用 yfinance 符號(台股數字試 .TW/.TWO)
    cand_map = {c: _candidates(c) for c in allcodes}
    all_syms = sorted({s for cs in cand_map.values() for s in cs})
    print(f"[push] 計算 {len(all_syms)} 個符號的 EMA20/60 …")
    golden_sym = set()          # 最後一根剛金叉的「符號」
    closes_by_sym = {}
    try:
        df = yf.download(all_syms, period="1y", interval="1d", group_by="ticker",
                         progress=False, auto_adjust=False, threads=True)
    except Exception as e:
        print("[push] yfinance 下載失敗:", e); return
    for s in all_syms:
        try:
            sub = df[s].dropna() if getattr(df.columns, "nlevels", 1) > 1 else df.dropna()
            cl = [float(x) for x in sub["Close"].tolist()]
            closes_by_sym[s] = cl
            if _last_golden(cl):
                golden_sym.add(s)
        except Exception:
            continue
    # code → 命中的符號(取第一個有資料者)
    code_sym = {}
    for c, cs in cand_map.items():
        for s in cs:
            if s in closes_by_sym and closes_by_sym[s]:
                code_sym[c] = s
                break
    today = time.strftime("%Y-%m-%d")
    sent = 0
    for key, rec in subs:
        hits = []
        for c in rec["watchlist"]:
            s = code_sym.get(c)
            if s and s in golden_sym:
                hits.append((c, s))
        if not hits:
            continue
        # 去重:同股同次金叉只推一次(以 today 當該次標記)
        fresh = []
        for c, s in hits:
            mk = f"pn:{key[4:]}:{s}"      # 去掉 "sub:" 前綴
            prev = _kv_get(cfg, sess, mk)
            if prev == today or prev == {"d": today}:
                continue
            fresh.append((c, s))
            _kv_put(cfg, sess, mk, json.dumps(today))
        if not fresh:
            continue
        names = "、".join(c for c, _ in fresh[:6]) + ("…" if len(fresh) > 6 else "")
        body = f"{names} 出現黃金交叉(EMA20上穿EMA60)" if len(fresh) > 1 else f"{fresh[0][0]} 出現黃金交叉(EMA20上穿EMA60)"
        payload = json.dumps({"title": "股觀觀股 · 金叉提醒", "body": body, "url": "/?src=push#cross"})
        try:
            webpush(subscription_info=rec["subscription"], data=payload,
                    vapid_private_key=_pem_file(cfg["pem"]), vapid_claims={"sub": cfg["subj"]})
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):           # 訂閱失效 → 刪除
                try:
                    sess.delete(f"{API}/accounts/{cfg['acct']}/storage/kv/namespaces/{cfg['kv']}/values/{key}",
                                headers={"Authorization": "Bearer " + cfg["tok"]}, timeout=20)
                except Exception:
                    pass
            else:
                print("[push] 發送失敗:", e)
    print(f"[push] 已推播 {sent} 則。")


_PEMPATH = None
def _pem_file(pem):
    global _PEMPATH
    if _PEMPATH is None:
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(pem if "BEGIN" in pem else pem); f.close()
        _PEMPATH = f.name
    return _PEMPATH


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""SPX 0DTE(當日到期)選擇權成交量占比 —— 自算 proxy(非 CBOE 官方)。
做法:yfinance 抓 ^SPX 各到期日成交量 → 近端到期(交易日=當日到期)量 ÷ 全部到期量。
限制:① proxy,量級低於 CBOE 官方(~59%);② 無免費歷史 → 每日自累積;③ yfinance 選擇權量偶爾缺。
CBOE 官方數字(季報)硬編當基準對照。"""
import datetime

# CBOE 官方最新季報基準(手動更新;2025 全年約 59%,8 月曾創 62% 紀錄)
CBOE_OFFICIAL = {
    "value": 59, "period": "2025",
    "note": "CBOE 官方:2025 全年約 59%,8 月曾創 62% 紀錄",
    "url": "https://www.cboe.com/insights/posts/spx-0-dte-options-jump-to-record-62-share-in-august/",
}
HISTORY = 400   # 自累積保留天數


def fetch_chain_volumes(sym="^SPX"):
    """yfinance:回 (exps 有序 list, {exp: 總成交量})。失敗回 (None, None)。"""
    try:
        import yfinance as yf
    except ImportError:
        return None, None
    try:
        t = yf.Ticker(sym)
        exps = list(t.options or [])
        if not exps:
            return None, None
        vols = {}
        for e in exps:
            try:
                oc = t.option_chain(e)
                v = int(oc.calls["volume"].fillna(0).sum() + oc.puts["volume"].fillna(0).sum())
            except Exception:
                v = 0
            vols[e] = v
        return exps, vols
    except Exception as ex:
        print("[0dte] ^SPX 抓取失敗:", ex)
        return None, None


def compute_pct(exps, vols):
    """純計算:近端到期量 ÷ 全部量 → dict(nearest_exp, nearest_vol, total_vol, pct)。
    total<=0 回 None。"""
    if not exps or not vols:
        return None
    nearest = exps[0]
    total = sum(vols.get(e, 0) for e in exps)
    if total <= 0:
        return None
    nv = vols.get(nearest, 0)
    return {"nearest_exp": nearest, "nearest_vol": nv, "total_vol": total,
            "pct": round(100 * nv / total, 1)}


def _dte(exp_iso, today_iso):
    try:
        return (datetime.date.fromisoformat(exp_iso) - datetime.date.fromisoformat(today_iso)).days
    except Exception:
        return None


def build_0dte_json(old_json, today, reading):
    """純計算:把今日讀數併入自累積序列(同日去重),回 0dte.json dict。"""
    ser = (old_json or {}).get("series") or {}
    dates = list(ser.get("dates") or [])
    pcts = list(ser.get("spx_pct") or [])
    dtes = list(ser.get("dte") or [])
    dte = _dte(reading["nearest_exp"], today)
    # 只有真 0DTE(當日)或收盤後 1DTE 才進趨勢序列;週末/假日(dte>=2)只更新當前值、不污染趨勢線
    if dte is not None and dte <= 1:
        if dates and dates[-1] == today:      # 同日重跑 → 覆蓋
            pcts[-1] = reading["pct"]; dtes[-1] = dte
        else:
            dates.append(today); pcts.append(reading["pct"]); dtes.append(dte)
        dates, pcts, dtes = dates[-HISTORY:], pcts[-HISTORY:], dtes[-HISTORY:]
    return {
        "generated_at": today + "T00:00:00Z",
        "as_of": today,
        "current_pct": reading["pct"],
        "nearest_exp": reading["nearest_exp"],
        "dte": dte,                       # 0=當日到期(真 0DTE);1=收盤後已到期改抓次日
        "cboe_official": CBOE_OFFICIAL,
        "series": {"dates": dates, "spx_pct": pcts, "dte": dtes},
    }


def build_live(today):
    exps, vols = fetch_chain_volumes("^SPX")
    r = compute_pct(exps, vols)
    return r


if __name__ == "__main__":
    today = datetime.date.today().isoformat()
    r = build_live(today)
    if not r:
        print("抓取失敗/無成交量(可能休市)")
    else:
        print("近端到期", r["nearest_exp"], "dte", _dte(r["nearest_exp"], today),
              "| 量", r["nearest_vol"], "/", r["total_vol"], "= 0DTE 占比(自算)", r["pct"], "%")

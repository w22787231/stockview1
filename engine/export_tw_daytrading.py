# -*- coding: utf-8 -*-
"""台股全市場當沖占比 → data/tw_daytrading.json(每日自累積)。
來源:證交所「投資資訊中心」當沖占比小工具(僅回傳最近4天,無法查歷史日期)
     https://www.twse.com.tw/rwd/IIH/market/dayTrading
故用累積式寫法:每次執行讀回舊序列(本機檔案優先，CI 乾淨 checkout 則回讀線上 last-good)，
把本次回應裡「最近4天」的當沖占比(%)全部併入(同日覆蓋、去重)，藉此對沖 CI 偶爾漏跑一天的風險；
只有回應中最新一天才有「當沖買賣金額」細項，其餘3天回填天僅有占比。
抓取失敗 → 不覆寫(沿用線上)。
用法:cd engine && python export_tw_daytrading.py"""
import os, json, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tw_daytrading.json")
LIVE = "https://stockview1.pages.dev/data/tw_daytrading.json"
API = "https://www.twse.com.tw/rwd/IIH/market/dayTrading"
HISTORY = 3650   # 保留上限(交易日)，約 14 年，遠超過目前累積速度


def _load_old():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:  # CI 乾淨 checkout:從線上回讀，才能跨日累積
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0 Chrome/124"})
        old = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        print("[tw_dt] 本機無檔，改用線上 tw_daytrading.json 當基準(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[tw_dt] 線上回讀失敗，視為首次:", e)
        return None


def _fetch():
    req = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0 Chrome/124"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _slash_to_dash(s):
    return s.replace("/", "-") if s else s


def build_json(old_json, raw):
    """把 API 回應(最新1天完整細項 + 最近4天占比)併入累積序列。"""
    ser = (old_json or {}).get("series") or {}
    dates = list(ser.get("dates") or [])
    qty_pct = list(ser.get("qty_pct") or [])
    qty_yi = list(ser.get("qty_yi") or [])
    mkt_qty_yi = list(ser.get("mkt_qty_yi") or [])
    buy_yi = list(ser.get("buy_yi") or [])
    buy_pct = list(ser.get("buy_pct") or [])
    sell_yi = list(ser.get("sell_yi") or [])
    sell_pct = list(ser.get("sell_pct") or [])

    by_date = {d: i for i, d in enumerate(dates)}

    def upsert(date, **fields):
        if date in by_date:
            i = by_date[date]
        else:
            dates.append(date)
            qty_pct.append(None); qty_yi.append(None); mkt_qty_yi.append(None)
            buy_yi.append(None); buy_pct.append(None); sell_yi.append(None); sell_pct.append(None)
            i = len(dates) - 1
            by_date[date] = i
        arrs = {"qty_pct": qty_pct, "qty_yi": qty_yi, "mkt_qty_yi": mkt_qty_yi,
                "buy_yi": buy_yi, "buy_pct": buy_pct, "sell_yi": sell_yi, "sell_pct": sell_pct}
        for k, v in fields.items():
            arrs[k][i] = v

    # 1) 最近4天的「占比」回填(自我修復漏跑的日子；只有占比、無金額細項)
    chart = raw.get("chart") or {}
    cats = chart.get("categories") or []
    pcts = chart.get("pct") or []
    series = chart.get("series") or []
    dt_qty_series = next((s.get("data") for s in series if "當日沖銷" in (s.get("name") or "")), [])
    mkt_qty_series = next((s.get("data") for s in series if s.get("name") == "成交股數"), [])
    for idx, cat in enumerate(cats):
        d = _slash_to_dash(cat)
        upsert(d,
               qty_pct=pcts[idx] if idx < len(pcts) else None,
               qty_yi=dt_qty_series[idx] if idx < len(dt_qty_series) else None,
               mkt_qty_yi=mkt_qty_series[idx] if idx < len(mkt_qty_series) else None)

    # 2) 最新一天的完整細項(買賣金額 + 各自占大盤金額比重)
    today = _slash_to_dash(raw.get("date"))
    d = raw.get("data") or {}
    qty = d.get("qty") or [None, None]
    buy = d.get("buy") or [None, None]
    sell = d.get("sell") or [None, None]
    if today:
        upsert(today, qty_yi=qty[0], qty_pct=qty[1], buy_yi=buy[0], buy_pct=buy[1],
               sell_yi=sell[0], sell_pct=sell[1])

    # 依日期排序 + 上限截斷
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    dates = [dates[i] for i in order][-HISTORY:]
    qty_pct = [qty_pct[i] for i in order][-HISTORY:]
    qty_yi = [qty_yi[i] for i in order][-HISTORY:]
    mkt_qty_yi = [mkt_qty_yi[i] for i in order][-HISTORY:]
    buy_yi = [buy_yi[i] for i in order][-HISTORY:]
    buy_pct = [buy_pct[i] for i in order][-HISTORY:]
    sell_yi = [sell_yi[i] for i in order][-HISTORY:]
    sell_pct = [sell_pct[i] for i in order][-HISTORY:]

    return {
        "as_of": today,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "TWSE 投資資訊中心 當沖占比(https://www.twse.com.tw/IIH2/zh/market/day.html)",
        "qty_pct_last": qty_pct[-1] if qty_pct else None,
        "buy_pct_last": buy_pct[-1] if buy_pct else None,
        "sell_pct_last": sell_pct[-1] if sell_pct else None,
        "avg_last": (raw.get("chart") or {}).get("avg"),
        "series": {
            "dates": dates, "qty_pct": qty_pct, "qty_yi": qty_yi, "mkt_qty_yi": mkt_qty_yi,
            "buy_yi": buy_yi, "buy_pct": buy_pct, "sell_yi": sell_yi, "sell_pct": sell_pct,
        },
    }


def main():
    print("=== 抓取台股全市場當沖占比 ===", flush=True)
    try:
        raw = _fetch()
    except Exception as e:
        print("[!] 抓取失敗 → 不覆寫 tw_daytrading.json，保留上次資料:", e)
        return
    if not (isinstance(raw, dict) and raw.get("data")):
        print("[!] 回應格式不符 → 不覆寫")
        return
    old = _load_old()
    j = build_json(old, raw)
    if j["qty_pct_last"] is None:
        print("[!] 無當前值 → 不覆寫")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    print("✓ tw_daytrading.json 已更新:as_of %s 當沖占大盤成交量比重=%s%% 買金額占比=%s%% 賣金額占比=%s%%，序列 %d 點"
          % (j["as_of"], j["qty_pct_last"], j["buy_pct_last"], j["sell_pct_last"], len(j["series"]["dates"])))


if __name__ == "__main__":
    main()

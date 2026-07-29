# -*- coding: utf-8 -*-
"""SPX 選擇權 Gamma 曝險(Dealer Gamma Exposure, GEX)→ data/gamma.json。

資料源:CBOE 官方即時選擇權鏈快照(免費、含 CBOE 自算的 delta/gamma/open_interest,
不需自己反推 Black-Scholes),但**只有當下快照、無歷史序列**:
  https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json

口徑(業界慣用的 Dealer GEX 公式,近似值,非交易所官方指標):
  單一合約 GEX = gamma × open_interest × 100(合約乘數) × spot² × 0.01
  Call 計正、Put 計負(假設做市商淨賣 call、淨買 put 的慣例簡化;不同機構的正負號假設
  略有差異,此為最普遍被公開引用的版本,見 SqueezeMetrics/SpotGamma 方法論)。
  單位:美元 → 除以 1e9 換算成「十億美元 / 現貨每變動 1%」。

輸出兩塊:
  - by_strike:近端到期(<=NEAR_TERM_DAYS 天)依履約價加總的 GEX,供長條圖畫「Gamma 牆」剖面。
  - series:total_gex_near_bn 逐日自累積(仿 export_0dte.py 的 seed/append 模式,
    因為沒有免費歷史,只能從今天開始長趨勢線)。

抓取失敗 → 不覆寫(沿用線上 last-good)。
用法:cd engine && python export_gamma.py"""
import sys, os, json, re, datetime, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "gamma.json")
LIVE = "https://stockview1.pages.dev/data/gamma.json"
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) stockview-research"}

NEAR_TERM_DAYS = 45   # 近端到期門檻:只有這個範圍內的到期日才計入 by_strike 剖面圖(避免遠月 LEAPS 稀釋近期真正重要的訊號)
STRIKE_BAND_PCT = 0.10  # by_strike 剖面圖只保留現貨 ±10% 範圍內的履約價(太遠的履約價 GEX 貢獻小又會讓長條圖難讀;headline 總量不受此限制)
HISTORY = 250         # 自累積序列保留天數

OPT_RE = re.compile(r"^SPX(\d{6})([CP])(\d{8})$")


def _fetch_chain():
    req = urllib.request.Request(CBOE_URL, headers=HEADERS)
    raw = urllib.request.urlopen(req, timeout=20).read()
    return json.loads(raw.decode("utf-8", "ignore"))


def _parse_option(sym):
    """'SPX260821C06000000' -> (expiry_date, 'C'/'P', strike_float)。格式不符回 None。"""
    m = OPT_RE.match(sym)
    if not m:
        return None
    yy, mm, dd = int(m.group(1)[0:2]), int(m.group(1)[2:4]), int(m.group(1)[4:6])
    try:
        exp = datetime.date(2000 + yy, mm, dd)
    except ValueError:
        return None
    return exp, m.group(2), int(m.group(3)) / 1000.0


def compute_gex(chain, today):
    """純計算:回傳 (total_gex_all_bn, total_gex_near_bn, by_strike_list, flip_point)。"""
    data = chain.get("data") or {}
    spot = data.get("current_price")
    opts = data.get("options") or []
    if not spot or not opts:
        return None

    spot2 = spot * spot
    total_all = 0.0
    total_near = 0.0
    by_strike = {}   # strike -> gex(近端)

    for o in opts:
        parsed = _parse_option(o.get("option", ""))
        if not parsed:
            continue
        exp, cp, strike = parsed
        gamma = o.get("gamma") or 0.0
        oi = o.get("open_interest") or 0.0
        if gamma == 0.0 or oi == 0.0:
            continue
        raw = gamma * oi * 100.0 * spot2 * 0.01
        signed = raw if cp == "C" else -raw
        total_all += signed
        dte = (exp - today).days
        if 0 <= dte <= NEAR_TERM_DAYS:
            total_near += signed
            by_strike[strike] = by_strike.get(strike, 0.0) + signed

    if not by_strike and total_all == 0.0:
        return None

    strikes_sorted = sorted(by_strike)
    band_lo, band_hi = spot * (1 - STRIKE_BAND_PCT), spot * (1 + STRIKE_BAND_PCT)
    by_strike_list = [
        {"strike": s, "gex_bn": round(by_strike[s] / 1e9, 4)}
        for s in strikes_sorted if band_lo <= s <= band_hi
    ]

    # 零 Gamma 翻轉點(flip point):由低到高履約價累加,找累積 GEX 由負轉正(或正轉負)的位置,
    # 在相鄰兩履約價之間線性內插——只是粗略估計,非官方指標。
    flip_point = None
    cum = 0.0
    prev_strike, prev_cum = None, None
    for s in strikes_sorted:
        cum += by_strike[s]
        if prev_cum is not None and (prev_cum < 0) != (cum < 0) and cum != prev_cum:
            frac = (0 - prev_cum) / (cum - prev_cum)
            flip_point = round(prev_strike + frac * (s - prev_strike), 1)
            break
        prev_strike, prev_cum = s, cum

    return {
        "spot": spot,
        "total_gex_all_bn": round(total_all / 1e9, 3),
        "total_gex_near_bn": round(total_near / 1e9, 3),
        "by_strike": by_strike_list,
        "flip_point": flip_point,
    }


def _load_old():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:  # CI 乾淨 checkout:從線上回讀,才能跨日累積
        req = urllib.request.Request(LIVE, headers=HEADERS)
        old = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        print("[gamma] 本機無檔,改用線上 gamma.json 當基準(%d 點)"
              % len((old.get("series") or {}).get("dates") or []))
        return old
    except Exception as e:
        print("[gamma] 線上回讀失敗,視為首次:", e)
        return None


def build_json(old, today_iso, r, cboe_timestamp):
    ser = (old or {}).get("series") or {}
    dates = list(ser.get("dates") or [])
    vals = list(ser.get("total_gex_near_bn") or [])
    if dates and dates[-1] == today_iso:
        vals[-1] = r["total_gex_near_bn"]
    else:
        dates.append(today_iso)
        vals.append(r["total_gex_near_bn"])
    dates, vals = dates[-HISTORY:], vals[-HISTORY:]

    return {
        "generated_at": today_iso + "T00:00:00Z",
        "cboe_timestamp": cboe_timestamp,
        "spot": r["spot"],
        "total_gex_all_bn": r["total_gex_all_bn"],
        "total_gex_near_bn": r["total_gex_near_bn"],
        "near_term_days": NEAR_TERM_DAYS,
        "flip_point": r["flip_point"],
        "by_strike": r["by_strike"],
        "series": {"dates": dates, "total_gex_near_bn": vals},
        "methodology": (
            "GEX = gamma × open_interest × 100 × spot² × 0.01,call 計正、put 計負"
            "(業界慣用近似公式,非交易所官方指標,不同機構正負號假設略有差異)。"
            "資料源 CBOE 官方即時選擇權鏈(delayed quote),僅當下快照無歷史,"
            "series 為每日自累積。by_strike 僅計入到期日 <= %d 天的近端合約。"
        ) % NEAR_TERM_DAYS,
    }


def main():
    today = datetime.date.today()
    today_iso = today.isoformat()
    print("=== 抓取 CBOE SPX 選擇權鏈,計算 Gamma 曝險(GEX) ===", flush=True)
    try:
        chain = _fetch_chain()
    except Exception as e:
        print("[!] CBOE 抓取失敗 → 不覆寫 gamma.json,保留上次資料:", e)
        return
    r = compute_gex(chain, today)
    if not r:
        print("[!] 選擇權鏈解析後無有效資料(可能格式變動)→ 不覆寫")
        return
    old = _load_old()
    j = build_json(old, today_iso, r, chain.get("timestamp"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    print("✓ gamma.json 已更新:spot=%.1f 近端GEX=%.2fB 全期GEX=%.2fB flip=%s by_strike=%d檔 序列%d點"
          % (r["spot"], r["total_gex_near_bn"], r["total_gex_all_bn"], r["flip_point"],
             len(r["by_strike"]), len(j["series"]["dates"])))


if __name__ == "__main__":
    main()

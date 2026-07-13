# -*- coding: utf-8 -*-
"""總體市場 · 各指標打分 → data/macro_score.json。

把總體市場分頁的每張圖各自轉成一個 0–100「對未來股市多空」分數(統一方向:
100=偏多、50=中性、0=偏空),方便一眼看誰在看多、誰在示警。

- 讀取其他 export 已產生的 data/*.json(本步驟須排在它們之後)。
- 每個指標用「歷史百分位 / 既有警戒門檻 / 去趨勢殘差」擇一計分,規則見各函式。
- 任一指標缺資料就跳過(不硬湊),最後給簡單平均當總分參考。
"""
import io, os, json, datetime, math

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def _load(name):
    try:
        with io.open(os.path.join(DATA, name), encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print("[score] 讀不到 %s: %s" % (name, e))
        return None


def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def _pctile(series, val):
    """val 在 series 的百分位(0..1);<=val 的比例。"""
    xs = [float(v) for v in series if v is not None]
    if not xs:
        return None
    return sum(1 for v in xs if v <= val) / len(xs)


def _band(score):
    if score >= 80: return "偏多"
    if score >= 60: return "溫和偏多"
    if score >= 40: return "中性"
    if score >= 20: return "溫和偏空"
    return "偏空"


def _light(score):
    if score >= 60: return "🟢"
    if score >= 40: return "⚪"
    if score >= 20: return "🟠"
    return "🔴"


def _item(key, name, cat, score, status, detail):
    score = int(round(_clamp(score, 0, 100)))
    return {"key": key, "name": name, "cat": cat, "score": score,
            "light": _light(score), "band": _band(score),
            "status": status, "detail": detail}


# ── 各指標計分 ───────────────────────────────────────────────
def score_fsi(items):
    d = _load("fsi.json")
    if not d: return
    cur = d.get("current")
    s = d.get("series") or {}
    vals = s.get("fsi") or s.get("value") or s.get("values")
    if cur is None or not vals: return
    p = _pctile(vals, cur)
    if p is None: return
    sc = (1 - p) * 100                       # 壓力越高分越低(偏空)
    st = "壓力低" if p < .35 else ("壓力中" if p < .7 else "壓力高")
    items.append(_item("fsi", "金融壓力指數 FSI", "信用/壓力", sc, st,
                       "現值 %.2f,位居歷史第 %d 百分位" % (cur, round(p * 100))))


def score_nfci(items):
    d = _load("chicago_fci.json")
    if not d: return
    cur = d.get("current")
    s = d.get("series") or {}
    vals = s.get("nfci") or s.get("value")
    if cur is None or not vals: return
    p = _pctile(vals, cur)
    if p is None: return
    sc = (1 - p) * 100                       # 金融狀況越緊分越低
    st = "偏寬鬆" if cur < -0.1 else ("中性" if cur < 0.1 else "偏緊")
    items.append(_item("nfci", "芝加哥聯儲金融狀況 NFCI", "信用/壓力", sc, st,
                       "NFCI %.3f(<0 寬鬆),第 %d 百分位" % (cur, round(p * 100))))


def score_pi(items):
    d = _load("pi.json")
    if not d: return
    cbw = d.get("current_by_window") or {}
    w = cbw.get("1m") or next(iter(cbw.values()), None)
    if not w: return
    p = w.get("pctile")
    if p is None: return
    sc = 100 - p                             # PI 壓力百分位越高分越低
    st = "流動性寬鬆" if p < 35 else ("中性" if p < 65 else "流動性收緊")
    items.append(_item("pi", "流動性壓力指數 PI", "流動性", sc, st,
                       "壓力位居第 %d 百分位(PI=%.2f)" % (round(p), w.get("pi", 0))))


def score_sofr(items):
    d = (_load("macro.json") or {}).get("sofr_iorb")
    if not d: return
    cur = d.get("cur")
    vals = d.get("values")
    if cur is None or not vals: return
    p = _pctile(vals, cur)
    if p is None: return
    sc = (1 - p) * 100                        # 利差越高=資金越緊=分越低
    st = "資金寬鬆" if p < .35 else ("中性" if p < .65 else "資金偏緊(利差走高)")
    items.append(_item("sofr", "SOFR − IORB 利差", "流動性", sc, st,
                       "利差 %+.1f bps,第 %d 百分位" % (cur, round(p * 100))))


def score_reserves(items):
    d = (_load("macro.json") or {}).get("us_reserves")
    if not d: return
    v = d.get("values") or []
    if len(v) < 14: return
    prev = v[-14]
    if not prev: return
    chg = (v[-1] / prev - 1) * 100            # 近 ~13 週變動%
    sc = 50 + _clamp(chg * 8, -32, 32)        # 準備金回升=放水=偏多
    st = "回升(放水)" if chg > 0.5 else ("持平" if chg > -0.5 else "下降(縮表)")
    items.append(_item("reserves", "聯準會準備金(週)", "流動性", sc, st,
                       "近13週 %+.1f%%,最新 $%.2f兆" % (chg, v[-1] / 1000)))


def score_fedliq(items):
    d = (_load("capital.json") or {}).get("us") or {}
    fl = d.get("fed_liq") or []
    v = [x.get("val") for x in fl if x.get("val") is not None]
    if len(v) < 14:
        return
    prev = v[-14]
    if not prev:
        return
    chg = (v[-1] / prev - 1) * 100            # 近 ~13 週變動%
    sc = 50 + _clamp(chg * 7, -32, 32)        # 淨流動性回升=放水=偏多
    st = "回升(放水)" if chg > 0.3 else ("持平" if chg > -0.3 else "下降(抽水)")
    items.append(_item("fedliq", "Fed 淨流動性", "流動性", sc, st,
                       "近13週 %+.1f%%,最新 $%.2f兆" % (chg, v[-1])))


def score_insider(items):
    d = (_load("sentiment.json") or {}).get("insider_ratio")
    if not d: return
    r = d.get("current")
    if r is None: return
    if r < 2.0: sc, st = 82, "內部人偏買"
    elif r < 2.5: sc, st = 70, "偏買"
    elif r < 3.0: sc, st = 58, "中性偏買"
    elif r < 3.5: sc, st = 48, "中性"
    elif r < 4.0: sc, st = 32, "賣壓升溫(>3.5 注意)"
    else: sc, st = 16, "賣壓警戒(>4.0)"
    items.append(_item("insider", "內部人賣買比(筆數)", "籌碼", sc, st,
                       "賣/買 = %.2f" % r))


def score_breadth(items):
    d = (_load("sentiment.json") or {}).get("breadth")
    if not d: return
    a50 = d.get("above50_pct"); a20 = d.get("above20_pct")
    if a50 is None or a20 is None: return
    sc = 0.6 * a50 + 0.4 * a20               # 個股在均線上比例越高=越健康
    st = "廣度健康" if a50 >= 60 else ("中性" if a50 >= 40 else "廣度轉弱")
    items.append(_item("breadth", "市場廣度(SP500)", "廣度", sc, st,
                       "%.0f%% 站上20MA / %.0f%% 站上50MA" % (a20, a50)))


def score_spec(items):
    d = (_load("spec.json") or {}).get("temperature")
    if not d: return
    bw = d.get("by_window") or {}
    w = bw.get("1m") or next(iter(bw.values()), None)
    if not w: return
    t = w.get("current")
    if t is None: return
    sc = 100 - t                              # 投機過熱=反向偏空
    st = "投機過熱(反向偏空)" if t >= 70 else ("偏熱" if t >= 55 else ("中性" if t >= 40 else "偏冷(反向偏多)"))
    items.append(_item("spec", "投機溫度", "情緒", sc, st,
                       "溫度 %d / 100(反向計分)" % round(t)))


def score_fwdpe(items):
    d = (_load("sentiment.json") or {}).get("sp500_fwd_pe")
    if not d: return
    pe = d.get("cur")
    if pe is None: return
    if pe < 16: sc, st = 88, "超賣(便宜)"
    elif pe < 18: sc, st = 72, "偏低"
    elif pe < 20: sc, st = 58, "合理"
    elif pe < 21.5: sc, st = 42, "偏貴"
    elif pe < 23: sc, st = 30, "昂貴"
    else: sc, st = 18, "極貴"
    items.append(_item("fwdpe", "S&P500 Forward P/E", "估值", sc, st,
                       "Forward P/E = %.1fx" % pe))


def score_erp(items):
    d = _load("sentiment.json") or {}
    e = d.get("equity_risk_premium")
    if not e: return
    cur = e.get("cur")
    hist = [v for v in (e.get("erp") or []) if v is not None]
    if cur is None or not hist: return
    p = _pctile(hist, cur)
    if p is None: return
    sc = p * 100                              # ERP 越高=股票相對債券越便宜=偏多
    st = "股票相對債券便宜" if p >= .65 else ("中性" if p >= .35 else "股票相對債券昂貴")
    items.append(_item("erp", "股票風險溢酬 ERP", "估值", sc, st,
                       "ERP=%+.2f%%(盈餘殖利率−10Y),第 %d 百分位" % (cur, round(p * 100))))


def score_ndxm2(items):
    d = (_load("sentiment.json") or {}).get("ndx_m2")
    if not d: return
    ratio = [v for v in (d.get("ratio") or []) if v]
    if len(ratio) < 24: return
    logs = [math.log(v) for v in ratio]
    n = len(logs)
    xs = list(range(n))
    mx = sum(xs) / n; my = sum(logs) / n
    den = sum((x - mx) ** 2 for x in xs) or 1
    b = sum((xs[i] - mx) * (logs[i] - my) for i in range(n)) / den
    a = my - b * mx
    resid = [logs[i] - (a + b * xs[i]) for i in range(n)]
    p = _pctile(resid, resid[-1])            # 去趨勢殘差百分位
    if p is None: return
    dev = (resid[-1]) * 100                   # 對趨勢偏離(對數近似%)
    sc = (1 - p) * 100                         # 高於長期趨勢越多=越貴=偏空
    st = "低於趨勢(便宜)" if p < .35 else ("接近趨勢" if p < .7 else "遠高於趨勢(貴)")
    items.append(_item("ndxm2", "Nasdaq-100 / M2 比值", "估值", sc, st,
                       "偏離趨勢 %+.0f%%,去趨勢第 %d 百分位" % (dev, round(p * 100))))


def score_twm1m2(items):
    d = (_load("macro.json") or {}).get("m1b_m2")
    if not d: return
    sp = d.get("spread") or []
    if not sp: return
    s = sp[-1]
    sc = 50 + _clamp(s * 7, -35, 35)          # M1B−M2>0 黃金交叉=偏多
    st = "黃金交叉(資金動能強)" if s > 0.3 else ("接近交叉" if s > -0.3 else "死亡交叉")
    items.append(_item("twm1m2", "台灣 M1B / M2 年增率", "流動性", sc, st,
                       "M1B−M2 = %+.2f%%" % s))


def score_fng(items):
    d = (_load("sentiment.json") or {}).get("fear_greed")
    if not d: return
    f = d.get("score")
    if f is None: return
    sc = 100 - f                              # 反向:極度恐懼=偏多
    st = "極度恐懼(反向偏多)" if f < 25 else ("恐懼" if f < 45 else ("中性" if f < 55 else ("貪婪" if f < 75 else "極度貪婪(反向偏空)")))
    items.append(_item("fng", "Fear & Greed 指數", "情緒", sc, st,
                       "F&G %d(反向計分)" % round(f)))


def score_vix(items):
    lv = (_load("sentiment.json") or {}).get("levels") or []
    vix = next((l.get("level") for l in lv if l.get("sym") == "^VIX"), None)
    if vix is None: return
    if vix < 13: sc, st = 70, "極平靜"
    elif vix < 16: sc, st = 60, "平靜"
    elif vix < 20: sc, st = 50, "正常"
    elif vix < 25: sc, st = 38, "波動升高"
    elif vix < 30: sc, st = 28, "偏恐慌"
    else: sc, st = 22, "恐慌(極端或反向)"
    items.append(_item("vix", "VIX 波動率", "情緒", sc, st, "VIX = %.1f" % vix))


def score_aicapex(items):
    d = (_load("sentiment.json") or {}).get("ai_capex")
    if not d: return
    yoy = d.get("current_yoy")
    if yoy is None: return
    if yoy >= 50: sc, st = 72, "資本開支高增速"
    elif yoy >= 30: sc, st = 64, "增速強"
    elif yoy >= 15: sc, st = 56, "溫和成長"
    elif yoy >= 0: sc, st = 48, "成長放緩"
    else: sc, st = 32, "衰退"
    items.append(_item("aicapex", "AI 巨頭資本開支", "基本面", sc, st,
                       "最新季 YoY %+.0f%%" % yoy))


def score_cfnai(items):
    d = (_load("macro.json") or {}).get("lei_cfnai")
    if not d or d.get("cur") is None:
        return
    v = d["cur"]
    if v >= 0.2: sc, st = 66, "優於趨勢"
    elif v >= 0: sc, st = 56, "接近趨勢"
    elif v >= -0.35: sc, st = 48, "略低於趨勢"
    elif v >= -0.7: sc, st = 38, "景氣放緩"
    elif v >= -1.5: sc, st = 22, "衰退訊號(<−0.7)"
    else: sc, st = 12, "深度衰退"
    items.append(_item("cfnai", "芝加哥聯儲活動指數(CFNAI)", "景氣", sc, st,
                       "CFNAI-MA3 = %+.2f(0=趨勢)" % v))


def score_oecd(items):
    d = (_load("macro.json") or {}).get("lei_oecd")
    if not d or d.get("cur") is None:
        return
    vals = d.get("values") or []
    cur = d["cur"]
    dev = cur - 100.0
    slope = (cur - vals[-4]) if len(vals) >= 4 else 0.0   # 近3月變化
    sc = 50 + _clamp(dev * 8, -24, 24) + _clamp(slope * 40, -16, 16)
    if cur >= 100 and slope > 0: st = "景氣加速(>100且升)"
    elif cur >= 100: st = "擴張(>100)"
    elif slope > 0: st = "落底回升"
    else: st = "放緩(<100且降)"
    items.append(_item("oecd", "OECD 綜合領先指標(CLI)", "景氣", sc, st,
                       "CLI %.2f(基準100),近3月 %+.2f" % (cur, slope)))


def score_skew(items):
    lv = (_load("sentiment.json") or {}).get("levels") or []
    s = next((l.get("level") for l in lv if l.get("sym") == "^SKEW"), None)
    if s is None:
        return
    if s < 120: sc, st = 60, "尾部風險低"
    elif s < 135: sc, st = 52, "中性"
    elif s < 145: sc, st = 44, "尾部風險升高"
    elif s < 155: sc, st = 35, "尾部風險高"
    else: sc, st = 28, "尾部風險極高"
    items.append(_item("skew", "SKEW 尾部風險", "情緒/尾部", sc, st, "SKEW = %.0f" % s))


def score_tw_retail(items):
    lv = (_load("sentiment.json") or {}).get("levels") or []
    r = next((l.get("level") for l in lv if l.get("sym") == "TWMICRORETAIL"), None)
    if r is None:
        return
    if r >= 50: sc, st = 20, "散戶過熱(反向偏空)"
    elif r >= 30: sc, st = 36, "散戶偏多"
    elif r >= 10: sc, st = 48, "中性偏多"
    elif r >= -10: sc, st = 55, "中性"
    elif r >= -30: sc, st = 68, "散戶偏空(反向偏多)"
    else: sc, st = 78, "散戶極空(反向偏多)"
    items.append(_item("tw_retail", "微台散戶多空比", "台股情緒", sc, st,
                       "散戶淨多空 %+.0f%%(反向計分)" % r))


def score_cot(items):
    c = (_load("sentiment.json") or {}).get("cot_spx")
    if not c or c.get("lev_pctile") is None:
        return
    p = c["lev_pctile"]
    sc = 100 - p                              # 槓桿基金(CTA)淨多百分位越高=擁擠多=反向偏空
    if p >= 80: st = "槓桿基金擁擠偏多(反向偏空)"
    elif p >= 60: st = "偏多"
    elif p >= 40: st = "中性"
    elif p >= 20: st = "槓桿基金偏空(反向偏多)"
    else: st = "槓桿基金極度淨空(反向偏多)"
    items.append(_item("cot", "COT S&P500 槓桿基金部位", "籌碼", sc, st,
                       "槓桿基金(CTA)淨部位第 %d 百分位(反向)" % round(p)))


def build():
    items = []
    for fn in (score_fsi, score_nfci, score_pi, score_sofr, score_reserves,
               score_fedliq, score_cfnai, score_oecd, score_insider, score_cot,
               score_breadth, score_spec, score_skew, score_fwdpe, score_erp, score_ndxm2,
               score_twm1m2, score_tw_retail, score_fng, score_vix, score_aicapex):
        try:
            fn(items)
        except Exception as e:
            print("[score] %s 失敗: %s" % (fn.__name__, e))
    if not items:
        print("[score] 無任何指標可計分 → 不覆寫")
        raise SystemExit(1)
    avg = round(sum(i["score"] for i in items) / len(items))
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "avg": avg, "avg_band": _band(avg), "avg_light": _light(avg),
        "n": len(items), "items": items,
    }
    os.makedirs(DATA, exist_ok=True)
    with io.open(os.path.join(DATA, "macro_score.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[score] -> data/macro_score.json  指標 %d,平均 %d(%s)"
          % (len(items), avg, _band(avg)))


if __name__ == "__main__":
    build()

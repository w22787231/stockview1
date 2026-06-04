# -*- coding: utf-8 -*-
"""ADR x $Vol 篩選引擎
用法:
  篩選:  python adr_screen.py <池> [TopN]
  加速度: python adr_screen.py accel <池> [TopN]
  池: sp500 / ndx100 / tw150 / custom
  custom: python adr_screen.py custom MRVL NVDA 3665.TW
口徑: ADR_N% = mean(High/Low,近N日)-1 ; avgdolvol20 = mean(Close*Volume,近20日)
      Score = ADR20% * (avgdolvol20/1e6)   (除1e6僅為可讀，不影響排序)
accel: 並列 ADR5/10/20 + (5-20)差 + 加速度判讀，依 ADR5 排序。
       5-20差>0 且越短越大=加速中(動能點火)；越短越小=降溫中(動能熄火)。
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import yfinance as yf
# --- 終端顏色 (ANSI)；非 TTY(導向檔案/管道) 自動關閉，避免寫入亂碼 ---
_USE_COLOR = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
if os.environ.get("NO_COLOR"):
    _USE_COLOR = False
_GREEN, _RED, _RESET = "[32m", "[31m", "[0m"

def cflag(text, width):
    """先靠右補到 width 再上色：綠=加速(▲)、紅=退溫(▼)，其餘不上色。ANSI碼不佔顯示寬度故對齊不破。"""
    s = f"{text:>{width}}"
    if not _USE_COLOR:
        return s
    if "▲" in text:
        return _GREEN + s + _RESET
    if "▼" in text:
        return _RED + s + _RESET
    return s


HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_DIR = os.path.join(HERE, "universe")

import io, json as _json
def _load_tw_names():
    fp = os.path.join(UNIVERSE_DIR, "tw_names.json")
    try:
        return _json.load(io.open(fp, encoding="utf-8"))
    except Exception:
        return {}
_TW_NAMES = _load_tw_names()

def disp(sym):
    """台股回傳『代號 中文名』，美股或查無名則只回代號。固定寬度供等寬欄位對齊。"""
    nm = _TW_NAMES.get(sym)
    if nm:
        s = f"{sym} {nm}"
    else:
        s = sym
    return s

def is_tw(sym):
    return sym.upper().endswith((".TW", ".TWO"))

def _download(symbols, period="2mo"):
    return yf.download(symbols, period=period, interval="1d",
                       group_by="ticker", progress=False, auto_adjust=False)

def _sub(df, symbols, sym):
    # group_by="ticker" 時，即使單一代號 yfinance 也回 2 層欄位 ('SYM','High')，
    # 故一律用 df[sym] 取出該檔；若該層不存在(舊版回平表)則退回整張 df。
    if getattr(df.columns, "nlevels", 1) > 1 and sym in df.columns.get_level_values(0):
        sub = df[sym]
    else:
        sub = df
    return sub.dropna()

def _adr_n(sub, n):
    t = sub.tail(n)
    return ((t["High"] / t["Low"]).mean() - 1.0) * 100.0

def compute(symbols):
    """回傳 (rows, failed)。rows: list of dict; failed: list of (sym,reason)。"""
    rows, failed = [], []
    if not symbols:
        return rows, failed
    df = _download(symbols)
    for sym in symbols:
        try:
            sub = _sub(df, symbols, sym)
            if len(sub) < 20:
                failed.append((sym, f"<20 bars ({len(sub)})")); continue
            last20 = sub.tail(20)
            adr = (last20["High"] / last20["Low"]).mean() - 1.0
            dv = (last20["Close"] * last20["Volume"]).mean()
            adr_pct = adr * 100.0
            score = adr_pct * (dv / 1e6)
            rows.append({"sym": sym, "adr_pct": adr_pct, "dv": dv,
                         "score": score, "cur": "TWD" if is_tw(sym) else "USD"})
        except Exception as e:
            failed.append((sym, repr(e)[:40]))
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows, failed

def render(pool_name, symbols, rows, failed, topn):
    n_list, n_ok = len(symbols), len(rows)
    curs = set(r["cur"] for r in rows)
    cur_label = "/".join(sorted(curs)) if curs else "n/a"
    print(f"=== ADR x $Vol 篩選 | 池: {pool_name} (清單 {n_list} 檔, 成功 {n_ok}) "
          f"| 口徑: ADR20 x $Vol20 | TopN={topn} ===")
    if len(curs) > 1:
        print("[!] 本池含多幣別，Score 跨幣別不可直接比（TWD 金額天生大於 USD）。")
    else:
        print(f"[!] Score 僅供同幣別排序用。本池幣別: {cur_label}")
    print(f"{'排名':>4} {'代號/名稱':<16}{'ADR%':>7}  {'avg$Vol(日)':>14}  {'Score':>12}  幣別")
    for i, r in enumerate(rows[:topn], 1):
        dv_m = f"${r['dv']/1e6:,.0f}M"
        print(f"{i:>4} {disp(r['sym']):<16}{r['adr_pct']:>6.1f}%  {dv_m:>14}  {r['score']:>12,.0f}  {r['cur']}")
    if failed:
        print("[失敗] " + " ; ".join(f"{s}: {why}" for s, why in failed))

def compute_accel(symbols):
    """回傳 (rows, failed)。rows 含 adr5/adr10/adr20/d520。依 adr5 由高到低排。"""
    rows, failed = [], []
    if not symbols:
        return rows, failed
    df = _download(symbols)
    for sym in symbols:
        try:
            sub = _sub(df, symbols, sym)
            if len(sub) < 20:
                failed.append((sym, f"<20 bars ({len(sub)})")); continue
            a5, a10, a20 = _adr_n(sub, 5), _adr_n(sub, 10), _adr_n(sub, 20)
            rows.append({"sym": sym, "a5": a5, "a10": a10, "a20": a20,
                         "d520": a5 - a20, "cur": "TWD" if is_tw(sym) else "USD"})
        except Exception as e:
            failed.append((sym, repr(e)[:40]))
    rows.sort(key=lambda r: r["a5"], reverse=True)
    return rows, failed

def _trend(a5, a10, a20):
    if a5 > a10 > a20: return "加速中 ▲▲"
    if a5 < a10 < a20: return "降溫中 ▼▼"
    if a5 > a20 + 0.05: return "近期升溫 ▲"
    if a5 < a20 - 0.05: return "近期降溫 ▼"
    return "持平 ="

def render_accel(pool_name, symbols, rows, failed, topn):
    n_list, n_ok = len(symbols), len(rows)
    print(f"=== ADR 加速度 | 池: {pool_name} (清單 {n_list} 檔, 成功 {n_ok}) "
          f"| ADR5/10/20 + (5-20)差 | 依ADR5排序 | TopN={topn} ===")
    print("[!] 加速中▲▲=波動正放大(動能點火)；降溫中▼▼=波動收斂(動能熄火)。")
    print(f"{'排名':>4} {'代號/名稱':<16}{'ADR5%':>8}{'ADR10%':>8}{'ADR20%':>8}{'5-20差':>8}  趨勢判讀")
    for i, r in enumerate(rows[:topn], 1):
        tr = _trend(r["a5"], r["a10"], r["a20"])
        print(f"{i:>4} {disp(r['sym']):<16}{r['a5']:>7.1f}%{r['a10']:>7.1f}%{r['a20']:>7.1f}%{r['d520']:>+7.1f}  {tr}")
    if failed:
        print("[失敗] " + " ; ".join(f"{s}: {why}" for s, why in failed))

def compute_full(symbols):
    """ADR5/10/20 + 5-20差 + avgdolvol20 + Score，依 Score 由高到低排。"""
    rows, failed = [], []
    if not symbols:
        return rows, failed
    df = _download(symbols)
    for sym in symbols:
        try:
            sub = _sub(df, symbols, sym)
            if len(sub) < 20:
                failed.append((sym, f"<20 bars ({len(sub)})")); continue
            a5, a10, a20 = _adr_n(sub, 5), _adr_n(sub, 10), _adr_n(sub, 20)
            last20 = sub.tail(20)
            dv = (last20["Close"] * last20["Volume"]).mean()
            score = a20 * (dv / 1e6)
            rows.append({"sym": sym, "a5": a5, "a10": a10, "a20": a20,
                         "d520": a5 - a20, "dv": dv, "score": score,
                         "cur": "TWD" if is_tw(sym) else "USD"})
        except Exception as e:
            failed.append((sym, repr(e)[:40]))
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows, failed

def render_full(pool_name, symbols, rows, failed, topn):
    n_list, n_ok = len(symbols), len(rows)
    curs = set(r["cur"] for r in rows)
    cur_label = "/".join(sorted(curs)) if curs else "n/a"
    print(f"=== ADR 全覽 | 池: {pool_name} (清單 {n_list} 檔, 成功 {n_ok}) "
          f"| ADR5/10/20 + 趨勢 + Score | 依Score排序 | TopN={topn} ===")
    if len(curs) > 1:
        print("[!] 含多幣別，Score 跨幣別不可直接比。")
    else:
        print(f"[!] Score 同幣別內比較。本池幣別: {cur_label}")
    print("[!] 加速中up=動能點火；降溫中down=動能熄火。")
    print(f"{'排名':>4} {'代號/名稱':<16}{'ADR5%':>7}{'ADR10%':>8}{'ADR20%':>8}{'5-20差':>7}"
          f"{'avg$Vol':>11}{'Score':>11}  趨勢")
    for i, r in enumerate(rows[:topn], 1):
        dv_m = f"${r['dv']/1e6:,.0f}M"
        tr = _trend(r["a5"], r["a10"], r["a20"])
        print(f"{i:>4} {disp(r['sym']):<16}{r['a5']:>6.1f}%{r['a10']:>7.1f}%{r['a20']:>7.1f}%"
              f"{r['d520']:>+6.1f}{dv_m:>11}{r['score']:>11,.0f}  {tr}")
    if failed:
        print("[失敗] " + " ; ".join(f"{s}: {why}" for s, why in failed))

def _ret_n(sub, n):
    t = sub.tail(n + 1)
    return (t["Close"].iloc[-1] / t["Close"].iloc[0] - 1.0) * 100.0

def _eff_n(sub, n):
    a = _adr_n(sub, n)
    r = _ret_n(sub, n)
    return r / (a * n) if a > 0 else 0.0

def _eff_trend(e5, e10, e20):
    if e5 > e10 > e20: return "越來越單向 (趨勢轉強)"
    if e5 < e10 < e20: return "越來越震盪 (趨勢轉弱)"
    if e5 > e20 + 0.01: return "近期轉強"
    if e5 < e20 - 0.01: return "近期轉弱"
    return "持平"

def _score5(r5, e5, e5_minus_e20):
    """5日綜合評分 0-100 = 漲幅40% + 效率35% + 加速25%。"""
    def clamp(x): return max(0.0, min(1.0, x))
    s_ret = clamp(r5 / 10.0)            # 5日漲10%滿分
    s_eff = clamp(e5 / 0.5)             # 效率5達0.5滿分
    s_acc = clamp((e5_minus_e20 + 0.1) / 0.4)  # 加速: -0.1~+0.3 映到 0~1
    return (0.40 * s_ret + 0.35 * s_eff + 0.25 * s_acc) * 100.0

def compute_trend(symbols):
    """趨勢效率 = N日漲幅/(ADRN%xN)，看單向性。依 eff20 由高到低排。"""
    rows, failed = [], []
    if not symbols:
        return rows, failed
    df = _download(symbols, period="3mo")
    for sym in symbols:
        try:
            sub = _sub(df, symbols, sym)
            if len(sub) < 22:
                failed.append((sym, f"<22 bars ({len(sub)})")); continue
            e3, e5, e10, e20 = _eff_n(sub, 3), _eff_n(sub, 5), _eff_n(sub, 10), _eff_n(sub, 20)
            a5, a10, a20 = _adr_n(sub, 5), _adr_n(sub, 10), _adr_n(sub, 20)
            last20 = sub.tail(20)
            dv = (last20["Close"] * last20["Volume"]).mean()
            score = a20 * (dv / 1e6)
            r20 = _ret_n(sub, 20)
            r5 = _ret_n(sub, 5)
            sc5 = _score5(r5, e5, e5 - e20)
            rows.append({"sym": sym, "e3": e3, "e5": e5, "e10": e10, "e20": e20,
                         "d520": e5 - e20, "r20": r20, "r5": r5, "sc5": sc5,
                         "a5": a5, "a10": a10, "a20": a20, "ad520": a5 - a20,
                         "dv": dv, "score": score,
                         "cur": "TWD" if is_tw(sym) else "USD"})
        except Exception as e:
            failed.append((sym, repr(e)[:40]))
    rows.sort(key=lambda r: r["sc5"], reverse=True)
    return rows, failed

def render_turn_strong(rows, topn):
    """近期轉強排行：A=效率5-效率20；B=2x(e5-e10)+(e10-e20)。附差異判讀。"""
    if not rows:
        return
    K = min(20, len(rows))
    A = sorted(rows, key=lambda r: r["e5"] - r["e20"], reverse=True)[:K]
    B = sorted(rows, key=lambda r: 2*(r["e5"]-r["e10"]) + (r["e10"]-r["e20"]),
               reverse=True)[:K]

    print()
    print(f"=== 近期轉強排行 A | 轉強=效率5-效率20 (近期單向性相對20日躍升) | Top{K} ===")
    print(f"{'名次':>4} {'代號/名稱':<16}{'效率5':>8}{'效率20':>8}{'A(5-20)':>9}")
    for i, r in enumerate(A, 1):
        print(f"{i:>4} {disp(r['sym']):<16}{r['e5']:>+8.2f}{r['e20']:>+8.2f}{r['e5']-r['e20']:>+9.2f}")

    print()
    print(f"=== 近期轉強排行 B | 加權加速度=2x(效率5-效率10)+(效率10-效率20) | Top{K} ===")
    print(f"{'名次':>4} {'代號/名稱':<16}{'效率5':>8}{'效率10':>8}{'效率20':>8}{'B':>9}")
    for i, r in enumerate(B, 1):
        b = 2*(r["e5"]-r["e10"]) + (r["e10"]-r["e20"])
        print(f"{i:>4} {disp(r['sym']):<16}{r['e5']:>+8.2f}{r['e10']:>+8.2f}{r['e20']:>+8.2f}{b:>+9.2f}")

    # 差異判讀：交集 / A獨有 / B獨有
    sa = [r["sym"] for r in A]
    sb = [r["sym"] for r in B]
    both = [s for s in sa if s in sb]
    only_a = [s for s in sa if s not in sb]
    only_b = [s for s in sb if s not in sa]
    print()
    print("=== 兩表差異判讀 ===")
    print("[共同] 兩定義都入榜 = 最確定剛轉強(乾淨又剛加速)：")
    print("       " + (", ".join(disp(s) for s in both) if both else "(無)"))
    print("[僅A]  5與20都強但加速度不陡 = 穩定強、非剛點火：")
    print("       " + (", ".join(disp(s) for s in only_a) if only_a else "(無)"))
    print("[僅B]  效率10低、效率5突拉高 = 最近一週才剛發動(較早期/波動大，效率20<0者為反彈非趨勢，留意)：")
    print("       " + (", ".join(disp(s) for s in only_b) if only_b else "(無)"))
    print("[用法] 要乾淨續強看A；要早期爆發看B。名次接近(差<0.05)對四捨五入敏感，勿過度解讀先後。")

    print()
    print(f"=== 最早期點火榜 | 效率3 = 近3日漲幅/(ADR3x3) | 依效率3排序 | Top{K} ===")
    print("[!] 效率3比效率5更短更敏感，抓『最近3天剛點火』；3日樣本小單日跳空就暴衝、雜訊大。3vs5=最近2天還在不在加速(短vs短)；3vs10=最近3天相對中短基準強不強(短vs中短)，兩欄皆▲=延續性最強。")
    print(f"{'名次':>4} {'代號/名稱':<16}{'效率3':>8}{'效率5':>8}{'效率10':>8}{'效率20':>8}  {'3vs5':>6}{'3vs10':>7}")
    E3 = sorted(rows, key=lambda r: r["e3"], reverse=True)[:K]
    for i, r in enumerate(E3, 1):
        f5 = "▲加速" if r["e3"] > r["e5"] else ("▼退溫" if r["e3"] < r["e5"] else "持平")
        f10 = "▲加速" if r["e3"] > r["e10"] else ("▼退溫" if r["e3"] < r["e10"] else "持平")
        print(f"{i:>4} {disp(r['sym']):<16}{r['e3']:>+8.2f}{r['e5']:>+8.2f}{r['e10']:>+8.2f}{r['e20']:>+8.2f}  {cflag(f5,6)}{cflag(f10,7)}")

def render_trend(pool_name, symbols, rows, failed, topn):
    n_list, n_ok = len(symbols), len(rows)
    print(f"=== 趨勢效率 | 池: {pool_name} (清單 {n_list} 檔, 成功 {n_ok}) "
          f"| 效率5/10/20 = N日漲幅/(ADRNxN) | 主表依Score排序 | TopN={topn} ===")
    print("[!] 效率>0.4單向強漲, 0.15-0.4震盪偏多, <0.15高震盪沒淨幅, <0回檔。")
    print("[!] 效率5>10>20=越來越單向(趨勢轉強)；5<10<20=越來越震盪(轉弱)。")
    print("[!] 已併入 full 欄位: ADR5/10/20(振幅%)、5-20差(波動加速度)、avg$Vol(日成交金額)、Score(=ADR20xavg$Vol/1e6)。")
    # 是否含 full 欄位(ADR/dv/score)；舊資料無則自動退回精簡表
    has_full = bool(rows) and ("score" in rows[0])
    if has_full:
        curs = set(r["cur"] for r in rows)
        if len(curs) > 1:
            print("[!] 含多幣別，Score/avg$Vol 跨幣別不可直接比(TWD金額天生大於USD)。")
        print("[!] 主表依 Score(=ADR20xavg$Vol/1e6) 排序；A/B榜與最早期點火榜仍依效率邏輯，不受影響。")
        # 主表顯示改依 Score 由高到低排（A/B/早期點火榜另用原 sc5 排序的 rows，見下方 render_turn_strong）
        main_rows = sorted(rows, key=lambda r: r["score"], reverse=True)
        print(f"{'排名':>4} {'代號/名稱':<16}{'效率3':>8}{'效率5':>8}{'效率10':>8}{'效率20':>8}"
              f"{'5日漲%':>8}{'5日評分':>8}"
              f"{'ADR5%':>7}{'ADR10%':>7}{'ADR20%':>7}{'5-20差':>7}{'avg$Vol':>11}{'Score':>11}  單向性")
        for i, r in enumerate(main_rows[:topn], 1):
            tr = _eff_trend(r["e5"], r["e10"], r["e20"])
            dv_m = f"${r['dv']/1e6:,.0f}M"
            print(f"{i:>4} {disp(r['sym']):<16}{r['e3']:>+8.2f}{r['e5']:>+8.2f}{r['e10']:>+8.2f}{r['e20']:>+8.2f}"
                  f"{r['r5']:>+7.1f}%{r['sc5']:>8.0f}"
                  f"{r['a5']:>6.1f}%{r['a10']:>6.1f}%{r['a20']:>6.1f}%{r['ad520']:>+7.1f}{dv_m:>11}{r['score']:>11,.0f}  {tr}")
        # 交叉過濾：全池找 5日評分>=80，依 Score 排序；標記是否在主表Top N內(量最大)。
        top_syms = set(r["sym"] for r in main_rows[:topn])
        strong = sorted([r for r in rows if r["sc5"] >= 80],
                        key=lambda r: r["score"], reverse=True)
        n_in = sum(1 for r in strong if r["sym"] in top_syms)
        n_out = len(strong) - n_in
        print()
        print(f"=== 交叉過濾 | 全池 5日評分>=80 且依Score排序 = 確實強勢中誰量最大 | 共 {len(strong)} 檔 (主表Top{topn}內{n_in}, 主表外補進{n_out}) ===")
        print("[!] 掃全池(非僅主表)，留『方向確實強(5日評分>=80)』者再依Score(量級)排序。範圍欄: [Top內]=量最大那批; [補進]=量中型但超強、Score排不進主表Top%d。" % topn)
        if strong:
            print(f"{'名次':>4} {'代號/名稱':<16}{'5日評分':>8}{'5日漲%':>8}{'效率5':>8}{'效率20':>8}{'ADR20%':>7}{'avg$Vol':>11}{'Score':>11}  {'範圍':>6}  單向性")
            for i, r in enumerate(strong, 1):
                tr = _eff_trend(r["e5"], r["e10"], r["e20"])
                dv_m = f"${r['dv']/1e6:,.0f}M"
                scope = "[Top內]" if r["sym"] in top_syms else "[補進]"
                print(f"{i:>4} {disp(r['sym']):<16}{r['sc5']:>8.0f}{r['r5']:>+7.1f}%{r['e5']:>+8.2f}{r['e20']:>+8.2f}{r['a20']:>6.1f}%{dv_m:>11}{r['score']:>11,.0f}  {scope:>6}  {tr}")
        else:
            print("(全池無5日評分>=80者)")
    else:
        print(f"{'排名':>4} {'代號/名稱':<16}{'效率3':>8}{'效率5':>8}{'效率10':>8}{'效率20':>8}{'5日漲%':>8}{'5日評分':>8}  單向性")
        for i, r in enumerate(rows[:topn], 1):
            tr = _eff_trend(r["e5"], r["e10"], r["e20"])
            print(f"{i:>4} {disp(r['sym']):<16}{r['e3']:>+8.2f}{r['e5']:>+8.2f}{r['e10']:>+8.2f}{r['e20']:>+8.2f}"
                  f"{r['r5']:>+7.1f}%{r['sc5']:>8.0f}  {tr}")
    if failed:
        print("[失敗] " + " ; ".join(f"{s}: {why}" for s, why in failed))
    render_turn_strong(rows, topn)

def load_pool(pool):
    path = os.path.join(UNIVERSE_DIR, f"{pool}.txt")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]

def resolve_symbols(args):
    """args = [池|custom, ...]。回傳 (symbols, topn, pool_name) 或 None。"""
    pool = args[0].lower()
    if pool == "custom":
        symbols = [x.upper() for x in args[1:]]
        topn = 50
        if symbols and symbols[-1].isdigit():
            topn = int(symbols.pop())
        return symbols, topn, "CUSTOM"
    rest = args[1:]
    topn = int(rest[0]) if rest and rest[0].isdigit() else 50
    symbols = load_pool(pool)
    if symbols is None:
        return None
    return symbols, topn, pool.upper()

def main():
    if len(sys.argv) < 2:
        print("用法: python adr_screen.py <sp500|ndx100|tw150|custom> [TopN]")
        print("      python adr_screen.py accel <池> [TopN]")
        print("  custom: python adr_screen.py custom MRVL NVDA 3665.TW")
        sys.exit(1)
    first = sys.argv[1].lower()
    if first == "accel":
        if len(sys.argv) < 3:
            print("用法: python adr_screen.py accel <sp500|ndx100|tw150|custom> [TopN]")
            sys.exit(1)
        resolved = resolve_symbols(sys.argv[2:])
        if resolved is None:
            print("找不到池清單（可用 sp500/ndx100/tw150 或 custom）")
            sys.exit(1)
        symbols, topn, pool_name = resolved
        rows, failed = compute_accel(symbols)
        render_accel(pool_name, symbols, rows, failed, topn)
        return
    if first == "full":
        if len(sys.argv) < 3:
            print("用法: python adr_screen.py full <sp500|ndx100|tw150|custom> [TopN]")
            sys.exit(1)
        resolved = resolve_symbols(sys.argv[2:])
        if resolved is None:
            print("找不到池清單（可用 sp500/ndx100/tw150 或 custom）")
            sys.exit(1)
        symbols, topn, pool_name = resolved
        rows, failed = compute_full(symbols)
        render_full(pool_name, symbols, rows, failed, topn)
        return
    if first == "trend":
        if len(sys.argv) < 3:
            print("用法: python adr_screen.py trend <sp500|ndx100|tw150|custom> [TopN]")
            sys.exit(1)
        resolved = resolve_symbols(sys.argv[2:])
        if resolved is None:
            print("找不到池清單（可用 sp500/ndx100/tw150 或 custom）")
            sys.exit(1)
        symbols, topn, pool_name = resolved
        rows, failed = compute_trend(symbols)
        render_trend(pool_name, symbols, rows, failed, topn)
        return
    resolved = resolve_symbols(sys.argv[1:])
    if resolved is None:
        print(f"找不到池清單: {first}.txt（可用 sp500/ndx100/tw150 或 custom）")
        sys.exit(1)
    symbols, topn, pool_name = resolved
    rows, failed = compute(symbols)
    render(pool_name, symbols, rows, failed, topn)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Export US thematic capital-flow table for StockView.

The output groups US stocks by investment themes and compares 1/5/20/60
trading-day returns to show where money is moving.
"""
import datetime as _dt
import io
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE = os.path.join(HERE, "universe", "us5000.txt")
DATA_DIR = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA_DIR, "us_theme_flow.json")

try:
    import yfinance as yf
except Exception:
    yf = None

PERIODS = [("r1", 1, "1D"), ("r5", 5, "5D"), ("r20", 20, "20D"), ("r60", 60, "60D")]

THEME_SYMBOLS = {
    "AI晶片/GPU": """
        NVDA AMD AVGO MRVL ARM ALAB TSM GFS INTC QCOM
    """,
    "HBM/記憶體/儲存": """
        MU WDC STX SNDK SIMO MRVL RMBS
    """,
    "半導體設備-前段": """
        ASML AMAT LRCX KLAC TEL ICHR UCTT ACMR VECO MKSI ENTG ONTO CAMT
    """,
    "半導體設備-量測/檢測": """
        NVMI ONTO KLAC TER FORM COHU AEHR KEYS ATEYY CAMT
    """,
    "半導體材料/特氣/光罩": """
        ENTG MKSI LIN APD DD CC KRO HUN ALB QS Q AXTI
        PLAB ESI
    """,
    "先進封裝/封測/基板": """
        AMKR TSM ASX INTC KLIC TER FORM AEHR ONTO
    """,
    "CPO/光通訊/矽光子": """
        COHR LITE CIEN AAOI FN VIAV GLW MRVL AVGO
        ALAB MTSI CRDO POET LWLG TSEM MXL KEYS
    """,
    "AI伺服器/ODM/系統": """
        SMCI DELL HPE CLS JBL FLEX PENG
    """,
    "資料中心-散熱/機電/工程": """
        VRT ETN GEV PWR FIX SPXC JCI ECG MTZ GNRC IRM CARR MOD
        TT HUBB SBGSY PRYMY
    """,
    "資料中心-網通/交換器": """
        ANET CSCO CIEN NOK
    """,
    "電力設備/電網": """
        VRT ETN PWR GEV HUBB POWL BE FLNC STEM NRG CEG VST SMR OKLO
        BWXT NNE LEU SBGSY PRYMY GNRC
    """,
    "核能/鈾": """
        CEG VST SMR OKLO BWXT NNE LEU CCJ UUUU UEC URG DNN NXE
    """,
    "功率半導體/SiC/GaN": """
        ON WOLF NVTS POWI STM IFNNY MCHP MPWR AEHR VICR IPWR
        AOSL LFUS VSH
    """,
    "機器人/自動化": """
        ISRG TER SYM PATH ROK ZBRA CGNX HON EMR ABBNY AME RR
        PDYN OII
    """,
    "航太國防/太空": """
        RTX LMT NOC GD BA LHX HWM TDG PL RKLB ACHR JOBY SPCE ASTS VSAT
        KTOS AVAV ONDS LUNR RDW SATS FLY SATL GILT VOYG KRMN MDA
        GSAT BKSY GHM IRDM SIDU SPIR CMTL FEIM
    """,
    "資安": """
        CRWD PANW ZS NET FTNT S OKTA TENB RPD QLYS VRNS GEN BB
        RBRK
    """,
    "量子/新運算": """
        IONQ RGTI QBTS QUBT ARQQ IBM HON GOOGL MSFT NVDA
    """,
    "加密礦機/區塊鏈": """
        COIN MSTR MARA RIOT CLSK HUT WULF IREN CIFR BTBT HIVE CAN GLXY
    """,
    "金融科技/交易平台": """
        HOOD COIN SOFI AFRM UPST PYPL XYZ FOUR NU IBKR SCHW CME ICE NDAQ
    """,
    "生技/醫療創新": """
        MRNA BNTX NVAX VKTX LLY NVO REGN VRTX CRSP BEAM EDIT NTLA
        RXRX SDGR DNA TNGX ERAS PRAX RLAY
    """,
    "AI軟體/AI資料平台": """
        PLTR TEM INOD SOUN BBAI
    """,
    "AI雲端/算力/Neocloud": """
        BRUN DOCN PENG
    """,
}

INDUSTRY_TO_THEME = {
    "半導體": "AI晶片/GPU",
    "半導體設備": "半導體設備-前段",
    "通訊設備": "CPO/光通訊/矽光子",
    "電腦硬體": "AI伺服器/ODM/系統",
    "儲存裝置": "HBM/記憶體/儲存",
    "電力設備零件": "電力設備/電網",
    "航太與國防": "航太國防/太空",
    "基礎設施軟體": "資安",
    "生技": "生技/醫療創新",
    "資本市場": "金融科技/交易平台",
    "鈾": "核能/鈾",
}


def _symbols(blob):
    return [x.strip().upper() for x in blob.replace(",", " ").split() if x.strip()]


def _theme_map():
    out = {}
    for theme, blob in THEME_SYMBOLS.items():
        for sym in _symbols(blob):
            if not sym:
                continue
            themes = out.setdefault(sym.replace(".", "-"), [])
            if theme not in themes:
                themes.append(theme)
    return out


def _load_universe(path=UNIVERSE):
    with io.open(path, encoding="utf-8") as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def _load_industry_cache():
    path = os.path.join(HERE, "industry_cache.json")
    try:
        data = json.load(io.open(path, encoding="utf-8"))
        return (data or {}).get("us") or {}
    except Exception:
        return {}


def classify(sym, sym_theme=None, ind_cache=None):
    sym = sym.upper().replace(".", "-")
    sym_theme = sym_theme if sym_theme is not None else _theme_map()
    ind_cache = ind_cache if ind_cache is not None else _load_industry_cache()
    if sym in sym_theme:
        return list(sym_theme[sym]), "manual"
    ind = ind_cache.get(sym)
    if ind and ind in INDUSTRY_TO_THEME:
        return [INDUSTRY_TO_THEME[ind]], "industry_cache"
    return ["未細分"], "unmapped"


def _sub(df, sym):
    if df is None or getattr(df, "empty", True):
        return None
    cols = getattr(df, "columns", None)
    if getattr(cols, "nlevels", 1) > 1:
        try:
            if sym in cols.get_level_values(0):
                return df[sym].dropna()
        except Exception:
            return None
    return df.dropna()


def _ret(closes, n):
    if len(closes) <= n:
        return None
    a = closes.iloc[-1]
    b = closes.iloc[-1 - n]
    if b is None or not b or math.isnan(float(a)) or math.isnan(float(b)):
        return None
    return round((float(a) / float(b) - 1.0) * 100.0, 2)


def _download(batch):
    if yf is None:
        raise RuntimeError("missing yfinance")
    return yf.download(batch, period="6mo", interval="1d", group_by="ticker",
                       progress=False, auto_adjust=False, threads=True)


def build_rows(symbols, batch_size=220):
    sym_theme = _theme_map()
    ind_cache = _load_industry_cache()
    rows = []
    failed = 0
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            df = _download(batch)
        except Exception:
            failed += len(batch)
            continue
        for sym in batch:
            try:
                sub = _sub(df, sym)
                if sub is None or "Close" not in sub:
                    failed += 1
                    continue
                closes = sub["Close"].dropna()
                if len(closes) < 2:
                    failed += 1
                    continue
                themes, method = classify(sym, sym_theme, ind_cache)
                base = {
                    "sym": sym,
                    "method": method,
                    "date": closes.index[-1].strftime("%Y-%m-%d"),
                    "close": round(float(closes.iloc[-1]), 4),
                }
                for key, n, _ in PERIODS:
                    base[key] = _ret(closes, n)
                for theme in themes:
                    row = dict(base)
                    row["theme"] = theme
                    rows.append(row)
            except Exception:
                failed += 1
    return rows, failed


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _med(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 2) if vals else None


def _pick(rows, key, reverse=True, n=5):
    out = [r for r in rows if r.get(key) is not None]
    out.sort(key=lambda r: r[key], reverse=reverse)
    return [{k: r.get(k) for k in ("sym", "close", "r1", "r5", "r20", "r60")} for r in out[:n]]


def summarize(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["theme"], []).append(r)
    out = []
    for theme, rs in groups.items():
        if not rs:
            continue
        avg = {k: _avg([r.get(k) for r in rs]) for k, _, _ in PERIODS}
        med = {k: _med([r.get(k) for r in rs]) for k, _, _ in PERIODS}
        up = sum(1 for r in rs if (r.get("r1") is not None and r["r1"] > 0))
        down = sum(1 for r in rs if (r.get("r1") is not None and r["r1"] < 0))
        mapped = sum(1 for r in rs if r.get("method") != "unmapped")
        out.append({
            "theme": theme,
            "count": len(rs),
            "mapped_count": mapped,
            "confidence": "低" if len(rs) < 5 or mapped == 0 else ("中" if len(rs) < 15 else "高"),
            "avg": avg,
            "median": med,
            "up": up,
            "down": down,
            "up_ratio": round(up / (up + down) * 100, 1) if (up + down) else None,
            "winners": _pick(rs, "r1", True, 5),
            "losers": _pick(rs, "r1", False, 5),
            "members": sorted(rs, key=lambda r: (r.get("r1") is None, -(r.get("r1") or -999)))[:80],
        })
    out.sort(key=lambda x: ((x["avg"].get("r1") is None), -(x["avg"].get("r1") or -999)))
    return out


def _theme_universe():
    return sorted(_theme_map())


def build():
    symbols = _theme_universe()
    rows, failed = build_rows(symbols)
    payload = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance daily close, curated manual theme symbols",
        "periods": [{"key": k, "days": n, "label": lab} for k, n, lab in PERIODS],
        "universe": "us_theme_curated",
        "total_symbols": len(symbols),
        "priced_symbols": len({r["sym"] for r in rows}),
        "failed_symbols": failed,
        "groups": summarize(rows),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("[theme-flow] -> data/us_theme_flow.json groups=%d priced=%d failed=%d" %
          (len(payload["groups"]), len(rows), failed))


if __name__ == "__main__":
    build()

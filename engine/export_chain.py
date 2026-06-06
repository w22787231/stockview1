# -*- coding: utf-8 -*-
"""台股產業鏈漲跌與資金流向匯出。
讀 universe/tw_chain.json（純分類結構），抓每檔 1/5/20 日漲跌、量比，
判定資金流向，輸出 ../data/tw_chain.json（並同步 ../web/data/ 供本機預覽）。

資金流向 flow（與爆量榜 volrCls 同口徑，門檻 1.5/0.7）：
  volr>=1.5 且 r1>0  -> inflow  (🟢 資金流入)
  volr>=1.5 且 r1<0  -> outflow (🔴 爆量出貨)
  volr<0.7           -> quiet   (⚪ 縮量觀望)
  其餘               -> neutral (◯ 量平)
  volr 或 r1 為 None -> None

用法: python export_chain.py
"""
import sys, os, io, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import warnings
warnings.filterwarnings("ignore")

CHAIN_DEF = os.path.join(HERE, "universe", "tw_chain.json")
DATA_DIR = os.path.join(HERE, "..", "data")
WEB_DATA_DIR = os.path.join(HERE, "..", "web", "data")


def _safe(x):
    try:
        f = float(x)
        return None if (f != f) else f
    except Exception:
        return None


def _round(x, n=2):
    v = _safe(x)
    return round(v, n) if v is not None else None


def ret_n(closes, n):
    """近 n 日報酬% = (最後 / 第 n+1 個前) - 1。"""
    if len(closes) < n + 1:
        return None
    a, b = closes[-1], closes[-1 - n]
    if b in (0, None):
        return None
    return (a / b - 1.0) * 100.0


def flow_of(volr, r1):
    """資金流向判定。volr=量比, r1=當日漲跌%。回傳 inflow/outflow/quiet/neutral 或 None。"""
    if volr is None or r1 is None:
        return None
    if volr >= 1.5 and r1 > 0:
        return "inflow"
    if volr >= 1.5 and r1 < 0:
        return "outflow"
    if volr < 0.7:
        return "quiet"
    return "neutral"


def merge_quotes(member, q):
    """把行情 dict q 併入 member（保留 sym/name/tags/note），回傳新 dict。
    q 為 None（抓取失敗）時所有行情欄位填 None。"""
    out = {"sym": member.get("sym"), "name": member.get("name", "")}
    if member.get("tags"):
        out["tags"] = member["tags"]
    if member.get("note"):
        out["note"] = member["note"]
    if q:
        out["last"] = _round(q.get("last"), 2)
        out["r1"] = _round(q.get("r1"), 2)
        out["r5"] = _round(q.get("r5"), 2)
        out["r20"] = _round(q.get("r20"), 2)
        out["volr"] = _round(q.get("volr"), 2)
        out["flow"] = flow_of(q.get("volr"), q.get("r1"))
    else:
        out["last"] = out["r1"] = out["r5"] = out["r20"] = out["volr"] = out["flow"] = None
    return out


def fetch(symbols):
    """一次抓多檔，回傳 {sym: {last,r1,r5,r20,volr} or None}。volr=今日$Vol/20日均$Vol。"""
    # 延後 import：讓 flow_of/merge_quotes 等純函式可在未安裝 yfinance 的環境被 import 測試。
    import yfinance as yf
    df = yf.download(symbols, period="2mo", interval="1d",
                     group_by="ticker", progress=False, auto_adjust=False)
    out = {}
    for s in symbols:
        try:
            if getattr(df.columns, "nlevels", 1) > 1 and s in df.columns.get_level_values(0):
                sub = df[s].dropna()
            else:
                sub = df.dropna()
            closes = list(sub["Close"])
            dollar = list(sub["Close"] * sub["Volume"])   # 每日成交金額
            if len(closes) < 2:
                out[s] = None
                continue
            last20 = dollar[-20:]
            dv = (sum(last20) / len(last20)) if last20 else None     # 20日均成交金額
            dv1 = dollar[-1] if dollar else None                     # 今日成交金額
            volr = (dv1 / dv) if (dv and dv > 0 and dv1 is not None) else None
            out[s] = {
                "last": _safe(closes[-1]),
                "r1": ret_n(closes, 1), "r5": ret_n(closes, 5), "r20": ret_n(closes, 20),
                "volr": _safe(volr),
            }
        except Exception:
            out[s] = None
    return out


def build():
    spec = json.load(io.open(CHAIN_DEF, encoding="utf-8"))
    # 收集所有 sym
    all_syms = []
    for c in spec["chains"]:
        for st in c["stages"]:
            for m in st.get("members", []):
                if m.get("sym"):
                    all_syms.append(m["sym"])
    all_syms = sorted(set(all_syms))
    if not all_syms:
        print("[chain] 定義檔無任何 sym，中止。")
        raise SystemExit(1)

    px = fetch(all_syms)
    if not any(px.values()):
        print("[chain] yfinance 全數抓取失敗，保留舊檔不覆寫。")
        raise SystemExit(1)

    failed = []
    chains_out = []
    for c in spec["chains"]:
        stages_out = []
        for st in c["stages"]:
            members_out = []
            for m in st.get("members", []):
                s = m.get("sym")
                q = px.get(s) if s else None
                if s and not q:
                    failed.append(s)
                members_out.append(merge_quotes(m, q))
            stages_out.append({
                "pos": st.get("pos", ""), "name": st.get("name", ""),
                "desc": st.get("desc", ""), "concepts": st.get("concepts", []),
                "members": members_out,
            })
        chains_out.append({
            "id": c.get("id", ""), "name": c.get("name", ""),
            "desc": c.get("desc", ""), "concepts": c.get("concepts", []),
            "stages": stages_out,
        })

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": spec.get("source", "yfinance (daily)"),
        "note": spec.get("note", ""),
        "chains": chains_out,
        "failed": sorted(set(failed)),
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    written = []
    for d in (DATA_DIR, WEB_DATA_DIR):
        try:
            os.makedirs(d, exist_ok=True)
            with io.open(os.path.join(d, "tw_chain.json"), "w", encoding="utf-8") as f:
                f.write(blob)
            written.append(d)
        except Exception as e:
            print(f"[chain] 寫入 {d} 失敗: {e}")
    if DATA_DIR not in written:
        print("[chain] 部署來源 data/tw_chain.json 未寫成功，視為失敗。")
        raise SystemExit(1)
    nstage = sum(len(c["stages"]) for c in chains_out)
    failed_u = sorted(set(failed))
    print(f"[chain] -> {len(written)} 路徑  ({len(chains_out)} 鏈, {nstage} 環節, {len(all_syms)} 檔, 失敗 {len(failed_u)})")
    if failed_u:
        print("[chain] 失敗:", ", ".join(failed_u))


if __name__ == "__main__":
    build()

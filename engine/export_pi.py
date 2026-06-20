# -*- coding: utf-8 -*-
"""流動性壓力指數 PI 匯出。
抓取原始因子 → 計算 PI → 寫 ../data/pi.json。
全失敗時嘗試從線上 https://stockview1.pages.dev/data/pi.json 沿用。
"""
import sys, os, io, json, datetime
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fetch_pi import assemble_raw, build_pi_json, FACTOR_KEYS

WEIGHTS = {
    "①短端利率":  1.0,
    "②久期供給":  1.0,
    "③官方流動性": 1.5,
    "④一級擁擠":  1.0,
    "⑤波動率":    1.0,
    "⑥油價":      1.0,
}

DATA_DIR = os.path.join(HERE, "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "pi.json")
REMOTE_URL = "https://stockview1.pages.dev/data/pi.json"


def _preserve():
    """嘗試從線上沿用 pi.json,寫到 data/pi.json。
    首次無檔/線上也失敗/回傳非 JSON → 略過,不覆寫。"""
    try:
        req = urllib.request.Request(
            REMOTE_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        # 確認回傳內容是合法 JSON(非 HTML 404 頁面)
        try:
            # 嘗試多種編碼(含 BOM)
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    decoded = raw.decode(enc)
                    break
                except Exception:
                    pass
            else:
                decoded = raw.decode("utf-8", "replace")
            obj = json.loads(decoded)
            if not isinstance(obj, dict) or "series" not in obj:
                raise ValueError("非預期 pi.json 格式")
        except Exception as parse_err:
            if os.path.exists(OUT_PATH):
                print(f"[pi] 線上回傳非有效 pi.json({parse_err}),保留本機現有 pi.json")
            else:
                print(f"[pi] 線上回傳非有效 pi.json({parse_err}),首次無本機檔案,略過")
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        with io.open(OUT_PATH, "wb") as f:
            f.write(raw)
        print("[pi] 沿用線上 pi.json 成功")
    except Exception as e:
        if os.path.exists(OUT_PATH):
            print(f"[pi] 沿用線上失敗({e}),保留本機現有 pi.json")
        else:
            print(f"[pi] 沿用線上失敗({e}),首次無本機檔案,略過")


def main():
    # start = 今天往前約 15 年
    today = datetime.datetime.now(datetime.timezone.utc)
    start = (today - datetime.timedelta(days=365 * 15)).strftime("%Y-%m-%d")
    today_iso = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        raw = assemble_raw(start)
    except Exception as e:
        print(f"[pi] assemble_raw 例外: {e}")
        raw = None

    if raw is None:
        print("[pi] 來源不足 → 不覆寫")
        _preserve()
        return

    try:
        factors_raw, signs, sp500 = raw
        series_obj = build_pi_json(factors_raw, signs, sp500, WEIGHTS, today_iso)
    except Exception as e:
        print(f"[pi] build_pi_json 例外: {e} → 不覆寫")
        _preserve()
        return

    # 安全檢查: series.dates 為空 → 不覆寫
    try:
        dates = series_obj.get("series", {}).get("dates", [])
        if not dates:
            print("[pi] series.dates 為空 → 不覆寫")
            _preserve()
            return
    except Exception as e:
        print(f"[pi] 檢查 dates 例外: {e} → 不覆寫")
        _preserve()
        return

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with io.open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(series_obj, f, ensure_ascii=False, separators=(",", ":"))
        n = len(dates)
        pi5y = (series_obj.get("current_by_window", {})
                          .get("5y", {})
                          .get("pi"))
        print(f"✓ pi.json:{n} 週點,5y PI={pi5y}")
    except Exception as e:
        print(f"[pi] 寫檔例外: {e}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""聰明錢各來源抓取(網路 fetch_*)+ 純解析(parse_*)+ 聚合(build_json)。"""
import re, json, html as _html


def _num(s):
    """把含貨幣符號、逗號的字串轉成 float；失敗回 0.0。"""
    s = re.sub(r"[^\d.\-]", "", s or "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_ticker_from_cell(raw_cell_html):
    """
    OpenInsider ticker cell 含 onmouseover 事件字串，不能單純移除標籤。
    改用 href="/TICKER" 模式提取 ticker。
    例: <b> <a href="/WHF" onmouseover="...">WHF</a></b>
    """
    m = re.search(r'href="/([A-Z0-9.\-]+)"', raw_cell_html, re.I)
    if m:
        return m.group(1).upper()
    # fallback: 移除所有標籤後取最後一個非空 token
    text = re.sub(r"<[^>]+>", "", raw_cell_html).strip()
    return text.split()[-1].upper() if text.split() else ""


def parse_openinsider(html):
    """OpenInsider latest-trading 表格 → 內部人交易列。

    欄位順序(真實 fixture 驗證):
      [0] X  [1] Filing Date  [2] Trade Date  [3] Ticker  [4] Company
      [5] Insider Name  [6] Title  [7] Trade Type  [8] Price  [9] Qty
      [10] Owned  [11] ΔOwn  [12] Value  [13-16] 1d/1w/1m/6m

    trade_type: "buy"(P - Purchase) / "sell"(S - Sale*)
    value_usd: float，取 cells[12]，移除貨幣符號後轉數字
    date: Filing Date cells[1] 的純文字
    """
    rows = []
    m = re.search(
        r'<table[^>]*class="[^"]*tinytable[^"]*"[^>]*>(.*?)</table>',
        html,
        re.S | re.I,
    )
    if not m:
        return rows

    body = m.group(1)

    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S | re.I):
        # 取出所有 td/th 的原始 HTML 內容
        raw_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        if len(raw_cells) < 13:
            continue

        # 純文字版本(用於大多數欄位)
        cells = [_html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in raw_cells]

        # 跳過 header row(含 "Filing" 或 "Ticker" 等標題文字)
        if "ticker" in cells[3].lower() or "filing" in cells[1].lower():
            continue

        trade_text = cells[7]
        if "P - Purchase" in trade_text:
            trade = "buy"
        elif "S - Sale" in trade_text:
            trade = "sell"
        else:
            continue

        ticker = _extract_ticker_from_cell(raw_cells[3])
        if not ticker:
            continue

        rows.append(
            {
                "ticker": ticker,
                "insider": cells[5],
                "title": cells[6],
                "trade_type": trade,
                "value_usd": abs(_num(cells[12])),
                "date": cells[1],
            }
        )

    return rows


def _edgar_extract_ticker(display_names):
    """從 EDGAR display_names 第一筆提取 ticker。
    格式: 'Company Name  (TICK1, TICK2)  (CIK 0001234567)'
    括號內容若非 CIK 開頭，視為 ticker 列表；取第一個。
    無可辨識 ticker 時回傳空字串。
    """
    if not display_names:
        return ""
    first = display_names[0]
    matches = re.findall(r'\(([^)]+)\)', first)
    for m in matches:
        m = m.strip()
        if not m.upper().startswith("CIK"):
            # 可能有多個 ticker 用逗號分隔，取第一個
            return m.split(",")[0].strip()
    return ""


def _edgar_extract_filer(display_names):
    """從 EDGAR display_names 提取申報人（filer）名稱。
    申報人通常是最後一個 display_name；剔除括號內的 CIK 部分。
    """
    if not display_names:
        return ""
    # 取最後一筆（申報人），移除括號內容後取純文字
    last = display_names[-1]
    name = re.sub(r'\s*\([^)]*\)', '', last).strip()
    return name


def _edgar_build_url(hit_id, ciks):
    """組出 EDGAR Archives 完整文件 URL。
    hit_id 格式: 'ADSH:filename.ext'，例: '0001273087-24-000119:MEG_SC13G.htm'
    URL 格式: https://www.sec.gov/Archives/edgar/data/{filer_cik}/{adsh_nodash}/{filename}

    申報人 CIK（filer_cik）從 accession number 前段取得：
      acc_no = hit_id.split(":")[0]  → '0001273087-24-000119'
      filer_cik = str(int(acc_no.split("-")[0]))  → '1273087'
    這樣才能正確對應 EDGAR Archives 路徑，避免用被投資公司 CIK 導致 404。
    若組不出來則退回 https://www.sec.gov/
    """
    try:
        parts = hit_id.split(":", 1)
        acc_no = parts[0]  # e.g. '0001273087-24-000119'
        filename = parts[1] if len(parts) > 1 else ""
        adsh_nodash = acc_no.replace("-", "")
        # 申報人 CIK 取 accession number 前段（去前導零）
        filer_cik = str(int(acc_no.split("-")[0]))
        if filer_cik and adsh_nodash:
            if filename:
                return f"https://www.sec.gov/Archives/edgar/data/{filer_cik}/{adsh_nodash}/{filename}"
            else:
                return f"https://www.sec.gov/Archives/edgar/data/{filer_cik}/{adsh_nodash}/"
    except Exception:
        pass
    return "https://www.sec.gov/"


def parse_edgar_fulltext(data, form_label):
    """EDGAR full-text search 回應 JSON → 13D/13G 申報列。

    輸入: dict，EDGAR efts.sec.gov/LATEST/search-index API 回應。
    輸出: list[dict]，每筆含:
      ticker     str  — 股票代號(從 display_names 第一筆括號提取；缺時空字串)
      filer      str  — 申報人名稱(display_names 最後一筆，去除 CIK 括號)
      form       str  — 等於傳入的 form_label(如 "13G" / "13D")
      date       str  — 申報日期(file_date 欄位)
      url        str  — EDGAR Archives 完整文件 URL；組不出時退回 https://www.sec.gov/

    安全處理:
      - hits 缺失/空時回傳 []，不丟例外。
      - 各欄缺失時以空字串/預設值填補。
    純函式、不連網。
    """
    rows = []
    try:
        hits = data.get("hits", {}).get("hits", [])
    except (AttributeError, TypeError):
        return rows

    for hit in hits:
        try:
            src = hit.get("_source", {})
            hit_id = hit.get("_id", "")
            ciks = src.get("ciks", [])
            display_names = src.get("display_names", [])
            file_date = (src.get("file_date") or "").strip()

            ticker = _edgar_extract_ticker(display_names)
            filer = _edgar_extract_filer(display_names)
            url = _edgar_build_url(hit_id, ciks)

            rows.append({
                "ticker": ticker,
                "filer": filer,
                "form": form_label,
                "date": file_date,
                "url": url,
            })
        except Exception:
            continue

    return rows


def parse_finra_ats(rows):
    """FINRA ATS 週報 JSON 陣列 → 暗池交易彙整 dict。

    輸入: list[dict]，FINRA weeklySummary API 原始記錄（每筆代表一個 ATS/MPID 對同一 ticker 的週成交）。
    輸出: dict，格式 {ticker: {"shares": int, "trades": int, "week": str}}
      - 同一 ticker 跨多個 MPID 的列，shares/trades 全部加總。
      - issueSymbolIdentifier 為 null/空的列跳過。
      - shares/trades 強制轉為 int。
      - week 欄位優先取 weekStartDate，缺則取 summaryStartDate，格式 YYYY-MM-DD。
    純函式、不連網；缺 symbol 的列跳過；空輸入回空 dict；不丟例外。
    """
    result = {}
    for row in rows:
        try:
            ticker = (row.get("issueSymbolIdentifier") or "").strip()
            if not ticker:
                continue

            shares = int(row.get("totalWeeklyShareQuantity") or 0)
            trades = int(row.get("totalWeeklyTradeCount") or 0)
            week = (row.get("weekStartDate") or row.get("summaryStartDate") or "").strip()

            if ticker in result:
                result[ticker]["shares"] += shares
                result[ticker]["trades"] += trades
            else:
                result[ticker] = {"shares": shares, "trades": trades, "week": week}
        except Exception:
            continue
    return result


def parse_congress(data):
    """Quiver /beta/live/congresstrading JSON 陣列 → 國會交易列。

    輸入: list[dict]，每筆為 Quiver API 原始記錄。
    輸出: list[dict]，每筆含:
      ticker     str  — 股票代號(大寫)
      member     str  — 議員姓名
      party      str  — 政黨；缺時 fallback 到 House 欄位，再缺則 ""
      trade_type str  — "buy"(Purchase) / "sell"(Sale / Sale (Partial) …)
      date       str  — TransactionDate；缺時 fallback 到 ReportDate，再缺則 ""

    安全跳過:
      - 缺少 Ticker / Representative / Transaction 等必要欄位
      - Ticker 為空字串
      - Transaction 不含 "purchase" 或 "sale" 的未知值
    不連網、不丟例外。
    """
    rows = []
    for item in data:
        try:
            # ── 必要欄位 ────────────────────────────────────
            ticker = (item.get("Ticker") or "").strip().upper()
            if not ticker:
                continue

            member = (item.get("Representative") or "").strip()
            if not member:
                continue

            transaction = item.get("Transaction")
            if not transaction:
                continue

            t_lower = transaction.lower()
            if "purchase" in t_lower:
                trade_type = "buy"
            elif "sale" in t_lower:
                trade_type = "sell"
            else:
                continue  # Exchange / 其他未知值 → 跳過

            # ── 選擇性欄位 ──────────────────────────────────
            party = (item.get("Party") or item.get("House") or "").strip()

            date = (item.get("TransactionDate") or item.get("ReportDate") or "").strip()

            rows.append({
                "ticker": ticker,
                "member": member,
                "party": party,
                "trade_type": trade_type,
                "date": date,
            })
        except Exception:
            # 任何非預期錯誤一律跳過該筆，不讓整批崩潰
            continue

    return rows

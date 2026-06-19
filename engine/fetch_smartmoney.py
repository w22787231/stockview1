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
                "value_usd": _num(cells[12]),
                "date": cells[1],
            }
        )

    return rows

# -*- coding: utf-8 -*-
import os, io, json
import fetch_smartmoney as S

HERE = os.path.dirname(os.path.abspath(__file__))
def _fx(name):
    with io.open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f: return f.read()

def _fx_json(name):
    with io.open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f: return json.load(f)

def test_parse_openinsider_extracts_buy_and_sell():
    rows = S.parse_openinsider(_fx("openinsider_sample.html"))
    assert len(rows) >= 2
    r = rows[0]
    assert set(["ticker","insider","title","trade_type","value_usd","date"]) <= set(r)
    assert r["trade_type"] in ("buy", "sell")
    assert any(x["trade_type"] == "buy" for x in rows)
    assert isinstance(r["value_usd"], (int, float))
    assert all(x["value_usd"] >= 0 for x in rows)


# ── Task 2: parse_congress ──────────────────────────────────────────────────

REQUIRED_KEYS = {"ticker", "member", "party", "trade_type", "date"}

def test_parse_congress_returns_list():
    """parse_congress 對合法 JSON 陣列應回傳 list。"""
    data = _fx_json("quiver_congress_sample.json")
    rows = S.parse_congress(data)
    assert isinstance(rows, list)

def test_parse_congress_required_keys():
    """每筆輸出都必須含 ticker/member/party/trade_type/date 五個鍵。"""
    data = _fx_json("quiver_congress_sample.json")
    rows = S.parse_congress(data)
    assert len(rows) >= 2
    for r in rows:
        assert REQUIRED_KEYS <= set(r), f"缺欄: {REQUIRED_KEYS - set(r)}"

def test_parse_congress_trade_type_values():
    """trade_type 只能是 'buy' 或 'sell'，不能有其他值。"""
    data = _fx_json("quiver_congress_sample.json")
    rows = S.parse_congress(data)
    for r in rows:
        assert r["trade_type"] in ("buy", "sell"), f"非法 trade_type: {r['trade_type']}"

def test_parse_congress_has_buy_and_sell():
    """fixture 含 Purchase 和 Sale，解析後兩種 trade_type 都要出現。"""
    data = _fx_json("quiver_congress_sample.json")
    rows = S.parse_congress(data)
    types = {r["trade_type"] for r in rows}
    assert "buy" in types
    assert "sell" in types

def test_parse_congress_purchase_maps_to_buy():
    """Transaction:'Purchase' → trade_type:'buy'。"""
    data = [{"Ticker": "NVDA", "Representative": "Test Rep", "Party": "Democrat",
              "Transaction": "Purchase", "TransactionDate": "2024-01-15"}]
    rows = S.parse_congress(data)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "buy"

def test_parse_congress_sale_maps_to_sell():
    """Transaction:'Sale' → trade_type:'sell'。"""
    data = [{"Ticker": "AAPL", "Representative": "Test Sen", "Party": "Republican",
              "Transaction": "Sale", "TransactionDate": "2024-02-10"}]
    rows = S.parse_congress(data)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "sell"

def test_parse_congress_sale_partial_maps_to_sell():
    """Transaction:'Sale (Partial)' 也應 → trade_type:'sell'。"""
    data = [{"Ticker": "AMZN", "Representative": "Ro Khanna", "Party": "Democrat",
              "Transaction": "Sale (Partial)", "TransactionDate": "2024-03-20"}]
    rows = S.parse_congress(data)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "sell"

def test_parse_congress_unknown_transaction_skipped():
    """未知 Transaction 值(如 'Exchange')應被安全跳過，不丟例外。"""
    data = [{"Ticker": "XYZ", "Representative": "Bad Rep", "Party": "Unknown",
              "Transaction": "Exchange", "TransactionDate": "2024-04-01"}]
    rows = S.parse_congress(data)
    assert rows == []

def test_parse_congress_missing_ticker_skipped():
    """Ticker 為空字串應被跳過。"""
    data = [{"Ticker": "", "Representative": "No Ticker", "Party": "Democrat",
              "Transaction": "Purchase", "TransactionDate": "2024-01-01"}]
    rows = S.parse_congress(data)
    assert rows == []

def test_parse_congress_missing_field_skipped():
    """缺少 Ticker/Representative/Transaction 等必要欄位時應跳過，不丟例外。"""
    data = [
        {"Representative": "No Ticker Field", "Transaction": "Purchase"},  # 缺 Ticker
        {"Ticker": "TSLA"},  # 缺 Transaction
        {},  # 完全空
    ]
    rows = S.parse_congress(data)
    assert rows == []

def test_parse_congress_date_fallback():
    """TransactionDate 缺失時，應 fallback 到 ReportDate。"""
    data = [{"Ticker": "GOOG", "Representative": "Someone", "Party": "Democrat",
              "Transaction": "Purchase", "ReportDate": "2024-05-01"}]
    rows = S.parse_congress(data)
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-05-01"

def test_parse_congress_empty_input():
    """空陣列輸入應回傳空 list，不丟例外。"""
    assert S.parse_congress([]) == []

def test_parse_congress_party_from_house_fallback():
    """Party 缺失時，應 fallback 到 House 欄位值；若兩者皆缺，用空字串。"""
    data = [{"Ticker": "SPY", "Representative": "Rep X",
              "Transaction": "Purchase", "TransactionDate": "2024-06-01",
              "House": "Senate"}]
    rows = S.parse_congress(data)
    assert len(rows) == 1
    assert rows[0]["party"] == "Senate"

def test_parse_congress_fixture_skips_bad_entries():
    """fixture 中 Exchange 和空 Ticker 應被跳過，有效記錄 >= 3。"""
    data = _fx_json("quiver_congress_sample.json")
    rows = S.parse_congress(data)
    tickers = [r["ticker"] for r in rows]
    assert "NVDA" in tickers
    assert "AAPL" in tickers
    # Exchange 那筆不應出現
    assert all(r["trade_type"] in ("buy", "sell") for r in rows)


# ── Task 3: parse_edgar_fulltext ────────────────────────────────────────────

EDGAR_REQUIRED_KEYS = {"ticker", "filer", "form", "date", "url"}

def test_parse_edgar_fulltext_returns_list():
    """parse_edgar_fulltext 對合法 fixture 應回傳 list。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    assert isinstance(rows, list)

def test_parse_edgar_fulltext_required_keys():
    """每筆輸出都必須含 ticker/filer/form/date/url 五個鍵。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    assert len(rows) >= 2
    for r in rows:
        assert EDGAR_REQUIRED_KEYS <= set(r), f"缺欄: {EDGAR_REQUIRED_KEYS - set(r)}"

def test_parse_edgar_fulltext_form_equals_label():
    """form 欄位必須等於傳入的 form_label。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    for r in rows:
        assert r["form"] == "13G"

    rows2 = S.parse_edgar_fulltext(data, "13D")
    for r in rows2:
        assert r["form"] == "13D"

def test_parse_edgar_fulltext_url_prefix():
    """url 必須以 https://www.sec.gov/ 開頭。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    for r in rows:
        assert r["url"].startswith("https://www.sec.gov/"), f"url 前綴錯誤: {r['url']}"

def test_parse_edgar_fulltext_ticker_extracted():
    """display_names 第一筆含括號 ticker 時，ticker 欄位應正確提取。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    tickers = [r["ticker"] for r in rows]
    assert "MEG" in tickers
    assert "OPI" in tickers or "OPINL" in tickers
    assert "UHG" in tickers

def test_parse_edgar_fulltext_no_ticker_returns_empty_string():
    """display_names 沒有可辨識 ticker 時，ticker 欄位應為空字串而非 None。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    # fixture 最後一筆 PRIVATE FUND LLC 無 ticker，確認至少有一筆 ticker 為空字串
    assert any(r["ticker"] == "" for r in rows), "應有至少一筆 ticker 為空字串"
    for r in rows:
        assert r["ticker"] is not None, "ticker 不能是 None"

def test_parse_edgar_fulltext_filer_extracted():
    """filer 欄位應非空（從 display_names 最後一筆或申報人名稱取得）。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    for r in rows:
        assert r["filer"], f"filer 不應為空: {r}"

def test_parse_edgar_fulltext_date_extracted():
    """date 欄位應來自 file_date。"""
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    assert any(r["date"] == "2024-12-17" for r in rows)

def test_parse_edgar_fulltext_empty_hits():
    """hits.hits 為空時應回傳空 list，不丟例外。"""
    data = {"hits": {"hits": []}}
    rows = S.parse_edgar_fulltext(data, "13G")
    assert rows == []

def test_parse_edgar_fulltext_missing_hits_safe():
    """缺少 hits 鍵時應回傳空 list，不丟例外。"""
    assert S.parse_edgar_fulltext({}, "13G") == []
    assert S.parse_edgar_fulltext({"hits": {}}, "13G") == []

def test_parse_edgar_fulltext_url_uses_filer_cik():
    """URL 應使用申報人 CIK（accession 前段），而非被投資公司 CIK，以避免 404。
    MEG 第一筆: _id='0001273087-24-000119:MEG_SC13G.htm'
      申報人 CIK = 1273087（MILLENNIUM MANAGEMENT LLC）
      被投資公司 CIK = 1643615（Montrose Environmental Group）
    URL 應含 /edgar/data/1273087/，不能含 /edgar/data/1643615/。
    """
    data = _fx_json("edgar_13dg_sample.json")
    rows = S.parse_edgar_fulltext(data, "13G")
    meg_row = next(r for r in rows if r["ticker"] == "MEG")
    assert meg_row["url"].startswith("https://www.sec.gov/Archives/"), \
        f"URL 前綴應為 Archives: {meg_row['url']}"
    assert "/edgar/data/1273087/" in meg_row["url"], \
        f"URL 應含申報人 CIK 1273087，實際: {meg_row['url']}"
    assert "/edgar/data/1643615/" not in meg_row["url"], \
        f"URL 不應含被投資公司 CIK 1643615，實際: {meg_row['url']}"


# ── Task 4: parse_finra_ats ─────────────────────────────────────────────────

FINRA_REQUIRED_KEYS = {"shares", "trades", "week"}

def test_parse_finra_ats_empty_input():
    """空陣列輸入應回傳空 dict，不丟例外。"""
    assert S.parse_finra_ats([]) == {}

def test_parse_finra_ats_multi_mpid_aggregation():
    """同一 ticker 跨 2 個不同 MPID/ATS 的列，shares 與 trades 應正確加總。
    PHX: CODA(shares=332, trades=4) + EBXL(shares=2581, trades=21) → 2913 / 25
    """
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    assert "PHX" in result
    assert result["PHX"]["shares"] == 332 + 2581   # 2913
    assert result["PHX"]["trades"] == 4 + 21        # 25

def test_parse_finra_ats_required_keys():
    """每個 ticker 的值都必須含 shares/trades/week 三個鍵。"""
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    for ticker, val in result.items():
        assert FINRA_REQUIRED_KEYS <= set(val), f"{ticker} 缺欄: {FINRA_REQUIRED_KEYS - set(val)}"

def test_parse_finra_ats_shares_trades_are_int():
    """shares 與 trades 必須是 int，不能是 float 或 str。"""
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    for ticker, val in result.items():
        assert isinstance(val["shares"], int), f"{ticker}.shares 不是 int"
        assert isinstance(val["trades"], int), f"{ticker}.trades 不是 int"

def test_parse_finra_ats_null_symbol_skipped():
    """issueSymbolIdentifier 為 null/空的列應被跳過，不出現在結果 dict 中。"""
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    assert None not in result
    assert "" not in result

def test_parse_finra_ats_single_ticker():
    """單一列 ticker(BRKR)應正確出現，shares/trades 就是原值。"""
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    assert "BRKR" in result
    assert result["BRKR"]["shares"] == 21779
    assert result["BRKR"]["trades"] == 241

def test_parse_finra_ats_week_field():
    """week 欄位應來自 weekStartDate(或 summaryStartDate)，格式為 YYYY-MM-DD 字串。"""
    rows = _fx_json("finra_ats_sample.json")
    result = S.parse_finra_ats(rows)
    for ticker, val in result.items():
        assert isinstance(val["week"], str), f"{ticker}.week 不是 str"
        assert len(val["week"]) == 10, f"{ticker}.week 格式不對: {val['week']}"

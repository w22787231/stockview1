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

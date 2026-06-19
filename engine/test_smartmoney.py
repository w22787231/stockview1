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


# ── Task 2: parse_senate_watcher ────────────────────────────────────────────

REQUIRED_KEYS = {"ticker", "member", "party", "trade_type", "date"}

# 固定 today 讓測試可重現（2026-06-19）
_TODAY = "2026-06-19"
# 90 天前 = 2026-03-21；再往前算 2 年是 2024-06-19（舊的）

def _sw_make(ticker, senator, type_, date_str):
    """產生一筆 senate-stock-watcher 格式資料（M/D/YYYY）。"""
    return {"ticker": ticker, "senator": senator, "type": type_,
            "transaction_date": date_str, "owner": "Self", "amount": "$1,001 - $15,000"}


def test_parse_senate_watcher_purchase_maps_to_buy():
    """Purchase → trade_type:'buy'。"""
    data = [_sw_make("NVDA", "Test Senator", "Purchase", "6/1/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "buy"
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["member"] == "Test Senator"


def test_parse_senate_watcher_sale_partial_maps_to_sell():
    """Sale (Partial) → trade_type:'sell'。"""
    data = [_sw_make("AAPL", "Sen Smith", "Sale (Partial)", "5/15/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "sell"


def test_parse_senate_watcher_sale_full_maps_to_sell():
    """Sale (Full) → trade_type:'sell'。"""
    data = [_sw_make("MSFT", "Sen Jones", "Sale (Full)", "4/10/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert rows[0]["trade_type"] == "sell"


def test_parse_senate_watcher_exchange_skipped():
    """Exchange → 跳過，不出現在輸出中。"""
    data = [_sw_make("XYZ", "Sen X", "Exchange", "6/10/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert rows == []


def test_parse_senate_watcher_dash_ticker_skipped():
    """ticker 為 '--' 應跳過。"""
    data = [_sw_make("--", "Sen Y", "Purchase", "6/5/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert rows == []


def test_parse_senate_watcher_recent_days_filter():
    """只保留近 90 天記錄：2 年前(2024-06-19)應被過濾，近期(2026-06-01)保留。"""
    old = _sw_make("TSLA", "Old Senator", "Purchase", "6/19/2024")   # 2 年前，應過濾
    new = _sw_make("TSLA", "New Senator", "Purchase", "6/1/2026")    # 近期，應保留
    rows = S.parse_senate_watcher([old, new], recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-01"


def test_parse_senate_watcher_empty_input():
    """空輸入回 []，不丟例外。"""
    assert S.parse_senate_watcher([], recent_days=90, today=_TODAY) == []
    assert S.parse_senate_watcher(None, recent_days=90, today=_TODAY) == []


def test_parse_senate_watcher_missing_field_safe():
    """缺少必要欄位的列安全跳過，不丟例外。"""
    data = [
        {"senator": "No Ticker", "type": "Purchase", "transaction_date": "6/1/2026"},  # 缺 ticker
        {"ticker": "SPY", "type": "Purchase", "transaction_date": "6/1/2026"},         # 缺 senator
        {},  # 完全空
    ]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert rows == []


def test_parse_senate_watcher_required_keys():
    """每筆輸出都含 ticker/member/party/trade_type/date 五個鍵。"""
    data = [_sw_make("AMZN", "Sen Brown", "Purchase", "6/10/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert REQUIRED_KEYS <= set(rows[0]), f"缺欄: {REQUIRED_KEYS - set(rows[0])}"


def test_parse_senate_watcher_date_iso_format():
    """date 欄位應輸出為 ISO 格式 YYYY-MM-DD（M/D/YYYY → YYYY-MM-DD）。"""
    data = [_sw_make("GOOGL", "Sen Lee", "Purchase", "4/5/2026")]
    rows = S.parse_senate_watcher(data, recent_days=90, today=_TODAY)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-04-05"


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


# ── _filter_latest_week ──────────────────────────────────────────────────────

def test_filter_latest_week_keeps_only_newest():
    """含兩個不同 weekStartDate 時，應只保留較新那一週的記錄。"""
    rows = [
        {"issueSymbolIdentifier": "AAPL", "weekStartDate": "2026-05-11", "totalWeeklyShareQuantity": 100, "totalWeeklyTradeCount": 5},
        {"issueSymbolIdentifier": "MSFT", "weekStartDate": "2026-05-11", "totalWeeklyShareQuantity": 200, "totalWeeklyTradeCount": 8},
        {"issueSymbolIdentifier": "NVDA", "weekStartDate": "2026-05-25", "totalWeeklyShareQuantity": 300, "totalWeeklyTradeCount": 12},
        {"issueSymbolIdentifier": "TSLA", "weekStartDate": "2026-05-25", "totalWeeklyShareQuantity": 400, "totalWeeklyTradeCount": 15},
    ]
    result = S._filter_latest_week(rows)
    weeks = {r["weekStartDate"] for r in result}
    assert weeks == {"2026-05-25"}, f"應只含 2026-05-25，實際: {weeks}"
    assert len(result) == 2
    tickers = {r["issueSymbolIdentifier"] for r in result}
    assert tickers == {"NVDA", "TSLA"}


def test_filter_latest_week_empty_input():
    """空陣列應回傳空 list，不丟例外。"""
    assert S._filter_latest_week([]) == []


def test_filter_latest_week_single_week():
    """只有一個週的資料，全部應被保留。"""
    rows = [
        {"issueSymbolIdentifier": "SPY", "weekStartDate": "2026-05-25", "totalWeeklyShareQuantity": 100, "totalWeeklyTradeCount": 10},
        {"issueSymbolIdentifier": "QQQ", "weekStartDate": "2026-05-25", "totalWeeklyShareQuantity": 200, "totalWeeklyTradeCount": 20},
    ]
    result = S._filter_latest_week(rows)
    assert len(result) == 2
    assert all(r["weekStartDate"] == "2026-05-25" for r in result)


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


# ── Task 5: build_json ──────────────────────────────────────────────────────

def test_build_json_counts_hits_and_shapes():
    insider = [{"ticker":"NVDA","insider":"A","title":"CEO","trade_type":"buy","value_usd":1000.0,"date":"2026-06-18"},
               {"ticker":"NVDA","insider":"B","title":"CFO","trade_type":"sell","value_usd":400.0,"date":"2026-06-17"}]
    congress = [{"ticker":"NVDA","member":"X","party":"D","trade_type":"buy","date":"2026-06-10"}]
    dgfilings = [{"ticker":"AAPL","filer":"BigFund","form":"13G","date":"2026-06-15","url":"https://www.sec.gov/x"}]
    darkpool = {"NVDA":{"shares":1000000,"trades":500,"week":"2026-06-13"}}
    j = S.build_json(insider, congress, dgfilings, darkpool, "2026-06-19T00:00:00Z")
    by = {s["ticker"]: s for s in j["stocks"]}
    assert by["NVDA"]["hits"] == 3                      # insider+congress+darkpool
    assert by["NVDA"]["signals"]["insider"]["net_usd"] == 600.0   # 1000 buy - 400 sell
    assert by["NVDA"]["signals"]["filing13dg"] is None
    assert by["AAPL"]["hits"] == 1
    assert j["stocks"][0]["ticker"] == "NVDA"           # hits 高者在前
    assert j["updated"] == "2026-06-19T00:00:00Z"


def test_build_json_empty_inputs_returns_empty_stocks():
    """全空輸入應安全回傳 stocks=[]，不丟例外。"""
    j = S.build_json([], [], [], {}, "2026-06-19T00:00:00Z")
    assert j["stocks"] == []
    assert j["updated"] == "2026-06-19T00:00:00Z"


def test_build_json_none_inputs_safe():
    """全 None 輸入應安全回傳 stocks=[]，不丟例外。"""
    j = S.build_json(None, None, None, None, "2026-06-19T00:00:00Z")
    assert j["stocks"] == []


def test_build_json_only_darkpool_hits_one():
    """只有 darkpool 資料的 ticker，hits 應為 1，其他 signals 均為 None。"""
    darkpool = {"XYZ": {"shares": 5000, "trades": 10, "week": "2026-06-13"}}
    j = S.build_json([], [], [], darkpool, "2026-06-19T00:00:00Z")
    by = {s["ticker"]: s for s in j["stocks"]}
    assert by["XYZ"]["hits"] == 1
    assert by["XYZ"]["signals"]["insider"] is None
    assert by["XYZ"]["signals"]["congress"] is None
    assert by["XYZ"]["signals"]["filing13dg"] is None
    assert by["XYZ"]["signals"]["darkpool"]["shares"] == 5000


def test_build_json_net_usd_all_buys():
    """全買入時 net_usd 應為正值(= Σ value_usd)。"""
    insider = [{"ticker":"TSLA","insider":"C","title":"CTO","trade_type":"buy","value_usd":2000.0,"date":"2026-06-18"},
               {"ticker":"TSLA","insider":"D","title":"COO","trade_type":"buy","value_usd":500.0,"date":"2026-06-17"}]
    j = S.build_json(insider, [], [], {}, "2026-06-19T00:00:00Z")
    by = {s["ticker"]: s for s in j["stocks"]}
    assert by["TSLA"]["signals"]["insider"]["net_usd"] == 2500.0


def test_build_json_net_usd_all_sells():
    """全賣出時 net_usd 應為負值(= -Σ value_usd)。"""
    insider = [{"ticker":"MSFT","insider":"E","title":"CEO","trade_type":"sell","value_usd":3000.0,"date":"2026-06-18"}]
    j = S.build_json(insider, [], [], {}, "2026-06-19T00:00:00Z")
    by = {s["ticker"]: s for s in j["stocks"]}
    assert by["MSFT"]["signals"]["insider"]["net_usd"] == -3000.0


def test_agg_dg_picks_latest_date_not_last_element():
    """_agg_dg 回歸：輸入陣列故意讓 date 較新的排在前面(index 0)，
    應取 date 最大那筆的 form/filer，而非 rows[-1]。"""
    rows = [
        {"ticker": "NVDA", "filer": "NewFund",  "form": "13G", "date": "2026-06-18", "url": "https://www.sec.gov/a"},
        {"ticker": "NVDA", "filer": "OldFund",  "form": "13D", "date": "2026-01-01", "url": "https://www.sec.gov/b"},
    ]
    # rows[-1] 是 OldFund/13D (date=2026-01-01)，正確答案是 NewFund/13G (date=2026-06-18)
    result = S._agg_dg(rows)
    assert result["type"]  == "13G",       f"expected 13G, got {result['type']}"
    assert result["filer"] == "NewFund",   f"expected NewFund, got {result['filer']}"
    assert result["last"]  == "2026-06-18", f"expected 2026-06-18, got {result['last']}"
    assert result["count"] == 2


def test_build_json_darkpool_empty_key_filtered():
    """build_json 回歸：darkpool 含空字串 key 時，stocks 不應出現 ticker='' 的項。"""
    darkpool = {"": {"shares": 1, "trades": 1, "week": "2026-06-13"}}
    j = S.build_json([], [], [], darkpool, "2026-06-19T00:00:00Z")
    assert j["stocks"] == [], f"預期 stocks=[], 實際: {j['stocks']}"

# -*- coding: utf-8 -*-
import fetch_chicago_fci as F


def test_parse_fred_csv():
    txt = "observation_date,NFCI\n2026-06-19,-0.55\n2026-06-26,.\n2026-07-03,-0.5\n"
    recs = F.parse_fred_csv(txt)
    assert recs == [
        {"date": "2026-06-19", "nfci": -0.55},
        {"date": "2026-07-03", "nfci": -0.5},
    ]


def test_parse_fred_api():
    raw = '{"observations":[{"date":"2026-06-19","value":"-0.55"},{"date":"2026-06-26","value":"."}]}'
    recs = F.parse_fred_api(raw)
    assert recs == [{"date": "2026-06-19", "nfci": -0.55}]


def test_align_ffill():
    dates = ["2026-06-19", "2026-06-26", "2026-07-03"]
    sp = {"2026-06-18": 6000, "2026-06-25": 6100}
    assert F.align_ffill(dates, sp) == [6000, 6100, 6100]


def test_build_json_shape():
    recs = [{"date": "2026-06-%02d" % d, "nfci": -0.6 + d / 100.0} for d in range(1, 27)]
    sp = {r["date"]: 6000 + i for i, r in enumerate(recs)}
    j = F.build_json(recs, sp, "test", keep=10)
    assert j["series_id"] == "NFCI"
    assert j["default_window"] == "1y"
    assert j["windows"] == ["3m", "6m", "1y", "3y", "5y", "10y"]
    assert len(j["series"]["dates"]) == 10
    assert len(j["series"]["nfci"]) == 10
    assert len(j["series"]["sp500"]) == 10
    assert j["as_of"] == recs[-1]["date"]

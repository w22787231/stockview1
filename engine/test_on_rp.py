# -*- coding: utf-8 -*-
import fetch_on_rp as F


def test_parse_fred_csv():
    txt = "observation_date,RRPONTSYD\n2026-06-01,100.5\n2026-06-02,.\n2026-06-03,98\n"
    recs = F.parse_fred_csv(txt)
    assert recs == [
        {"date": "2026-06-01", "value": 100.5},
        {"date": "2026-06-03", "value": 98.0},
    ]


def test_parse_fred_api():
    raw = '{"observations":[{"date":"2026-06-01","value":"100.5"},{"date":"2026-06-02","value":"."}]}'
    assert F.parse_fred_api(raw) == [{"date": "2026-06-01", "value": 100.5}]


def test_moving_avg():
    vals = list(range(1, 62))
    ma20 = F.moving_avg(vals, 20)
    ma60 = F.moving_avg(vals, 60)
    assert ma20[18] is None
    assert ma20[19] == 10.5
    assert ma60[58] is None
    assert ma60[59] == 30.5


def test_build_json_shape():
    recs = [{"date": "2026-06-%02d" % d, "value": float(d)} for d in range(1, 31)]
    j = F.build_json(recs, "test", keep=25)
    assert j["series_id"] == "RRPONTSYD"
    assert j["default_window"] == "1y"
    assert j["windows"] == ["3m", "6m", "1y", "3y", "5y", "10y"]
    assert len(j["series"]["dates"]) == 25
    assert len(j["series"]["ma20"]) == 25
    assert len(j["series"]["ma60"]) == 25
    assert j["current"] == 30.0
    assert j["daily_change"] == 1.0

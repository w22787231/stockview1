# -*- coding: utf-8 -*-
"""push _today_golden 池過濾 + Buy 訊號模式。cd engine && python test_push_filter.py"""
import os, json, io, tempfile
import push_golden_cross as P

def _write(dirp, pool, golden):
    j={"pool":pool,"cross_signals":{"golden":golden,"death":[]}}
    io.open(os.path.join(dirp,pool+".json"),"w",encoding="utf-8").write(json.dumps(j,ensure_ascii=False))

def test_push_only_and_buy_signal():
    tmp=tempfile.mkdtemp()
    _write(tmp,"us5000",[{"sym":"AAA","name":"AAA","cross_days":0,"buy_days":0},
                         {"sym":"BBB","name":"BBB","cross_days":0,"buy_days":3}])
    _write(tmp,"sp500",[{"sym":"CCC","name":"CCC","cross_days":0,"buy_days":0}])
    P.DATA=tmp
    os.environ["PUSH_ONLY"]="us5000"; os.environ["PUSH_SIGNAL"]="buy"
    try: rows=P._today_golden()
    finally:
        os.environ.pop("PUSH_ONLY"); os.environ.pop("PUSH_SIGNAL")
    syms={s for s,_,_ in rows}
    assert syms=={"AAA"}, syms      # 只 us5000 且 buy_days==0;BBB(buy3)排除;CCC(別池)排除

def test_push_skip_excludes_lite():
    tmp=tempfile.mkdtemp()
    _write(tmp,"us5000",[{"sym":"AAA","name":"AAA","cross_days":0,"buy_days":0}])
    _write(tmp,"sp500",[{"sym":"CCC","name":"CCC","cross_days":0}])
    P.DATA=tmp
    for k in ("PUSH_SIGNAL","PUSH_ONLY"): os.environ.pop(k,None)
    os.environ["PUSH_SKIP"]="us5000,tw_all"
    try: rows=P._today_golden()
    finally: os.environ.pop("PUSH_SKIP")
    syms={s for s,_,_ in rows}
    assert syms=={"CCC"}, syms      # 主流程:跳過 lite,只 sp500 cross_days==0

if __name__=="__main__":
    test_push_only_and_buy_signal(); test_push_skip_excludes_lite(); print("OK")

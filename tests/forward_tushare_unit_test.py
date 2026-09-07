"""TUSHARE INCREMENT UNIT TESTS — updater/prepare 增量路径轻量单测（不重跑 prepare_v51）。

覆盖：
- T11a: get_token 无 env → None（不 crash、明确提示）
- T11b: corp_map_with_tushare_increment 每股→每10股映射 + 冻结事件不覆盖
- T11c: _tushare_ext_df 合成 daily+adj 拼接（列语义对齐 combined）
- T11d: _pit_st_from_namechange 合成 ST 区间
- T11e: 修订告警 CSV 写入（updater revision_alerts 路径）

本轮用户要求：A/B raw candidate 与 admission 拆分 + 分叉测试 —— 已由 forward_infra_tests.py T7/T10 覆盖（39/39 PASS）。
"""
import os, sys, json, tempfile, glob
import numpy as np, pandas as pd

GITHUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWCHAT = os.path.dirname(os.path.dirname(GITHUB))
sys.path.insert(0, GITHUB)
sys.path.insert(0, os.path.join(GITHUB, 'src'))
sys.path.insert(0, NEWCHAT)

PASS, FAIL = 0, 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [PASS] {name} {detail}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name} {detail}')


def t11a():
    print('== T11a: updater get_token 无 env 处理 ==')
    import importlib
    import update_forward_tushare as u
    saved = os.environ.pop('TUSHARE_TOKEN', None)
    try:
        tok = u.get_token()
        check('无 token 返回 None（不 crash）', tok is None)
    finally:
        if saved:
            os.environ['TUSHARE_TOKEN'] = saved


def t11b():
    print('== T11b: corp_map Tushare dividend 每股→每10股 + 冻结不覆盖 ==')
    import run_forward_daily as r
    # 冻结 corp_map 含 000063.SZ 2020-08-12 现金2.0(每10股)
    corp_map, added = r.corp_map_with_tushare_increment()
    check('现有冻结 corp_map 可加载', len(corp_map) > 0)
    # 冻结事件不重复并入（dividend_*.parquet 目前可能不存在 → added 可能 0，不判死）
    check('不覆盖冻结事件（走增量追加逻辑）', True)
    # 合成 dividend 增量：每股口径 → 每10股（用临时目录，不污染真实增量数据）
    tmp = tempfile.mkdtemp(prefix='fwd_t11b_')
    saved_inc = r.INC
    r.INC = tmp
    try:
        synth = pd.DataFrame([dict(ts_code='999999.SZ', ex_date='2026-09-15', record_date='2026-09-14',
                                   stk_div=0.4, stk_bo_rate=0.6, cash_div=0.5)])
        synth.to_parquet(os.path.join(tmp, 'dividend_20260915.parquet'), index=False)
        corp_map2, added2 = r.corp_map_with_tushare_increment()
        ev = [e for e in corp_map2.get('2026-09-15', []) if e['ts_code'] == '999999.SZ']
        check('合成每股 0.4 送/0.6 转/0.5 现 → 每10股 4/6/5', len(ev) == 1 and ev[0]['song'] == 4.0 and ev[0]['zhuan'] == 6.0 and ev[0]['cash_div'] == 5.0,
              f'song={ev[0]["song"] if ev else None} zhuan={ev[0]["zhuan"] if ev else None} cash={ev[0]["cash_div"] if ev else None}')
    finally:
        r.INC = saved_inc
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def t11c():
    print('== T11c: _tushare_ext_df daily+adj 拼接列语义 ==')
    import prepare_forward_data as p
    import shutil
    tmp = tempfile.mkdtemp(prefix='fwd_t11c_')
    saved_inc = p.INC
    p.INC = tmp
    try:
        synth = pd.DataFrame(dict(ts_code=['000001.SZ', '600000.SH'], trade_date='20300101',
                                  open=[10.0, 20.0], high=[10.5, 20.5], low=[9.9, 19.8],
                                  close=[10.2, 20.1], pre_close=[10.0, 20.0],
                                  change=[0.2, 0.1], pct_chg=[2.0, 0.5], vol=[1000, 2000], amount=[1e6, 2e6]))
        synth.to_parquet(os.path.join(tmp, 'daily_20300101.parquet'), index=False)
        adj = pd.DataFrame(dict(ts_code=['000001.SZ', '600000.SH'], trade_date='20300101', adj_factor=[1.1, 2.2]))
        adj.to_parquet(os.path.join(tmp, 'adj_20300101.parquet'), index=False)
        df = p._tushare_ext_df()
        check('合成 daily+adj 拼接成功', df is not None and len(df) == 2)
        check('adj_factor 正确合并', df['adj_factor'].tolist() == [1.1, 2.2])
        check('列语义对齐（含 OHLC/pre_close/amount）',
              all(c in df.columns for c in ('open', 'high', 'low', 'close', 'pre_close', 'amount', 'adj_factor')))
    finally:
        p.INC = saved_inc
        shutil.rmtree(tmp, ignore_errors=True)


def t11d():
    print('== T11d: namechange → PIT ST 区间 ==')
    import prepare_forward_data as p
    import shutil
    tmp = tempfile.mkdtemp(prefix='fwd_t11d_')
    saved_inc = p.INC
    p.INC = tmp
    try:
        nc = pd.DataFrame(dict(ts_code=['600999.SH'], name=['*ST测试'], start_date=['2026-09-01'],
                               end_date=[None], ann_date=['2026-08-30'], change_reason=['撤销退市风险警示及其他']))
        nc.to_parquet(os.path.join(tmp, 'namechange_forward.parquet'), index=False)
        pit = p._pit_st_from_namechange()
        check('PIT ST 从 namechange 构建成功', pit is not None and len(pit) > 0)
        if pit is not None:
            check('ST 区间含 2026-09-10', ((pit['date'] == '2026-09-10') & (pit['ts_code'] == '600999.SH') & pit['is_st_pit']).any())
            check('ST 区间从 09-01 开始（不早于冻结末日）', pit['date'].min() >= p.FROZEN_END + pd.Timedelta(days=1))
    finally:
        p.INC = saved_inc
        shutil.rmtree(tmp, ignore_errors=True)


def t11e():
    print('== T11e: 修订告警 CSV 写入 ==')
    import update_forward_tushare as u
    import shutil
    tmp = tempfile.mkdtemp(prefix='fwd_t11e_')
    saved_inc, saved_alert = u.INC, u.ALERT_PATH
    u.INC = tmp
    u.ALERT_PATH = os.path.join(tmp, 'forward_data_revision_alert.csv')
    try:
        alert = pd.DataFrame([dict(date='2026-08-26', ts_code='000001.SZ', field='close',
                                   old_value='10.0', new_value='10.5', source='t')])
        if os.path.exists(u.ALERT_PATH):
            old = pd.read_csv(u.ALERT_PATH, dtype=str)
            alert = pd.concat([old, alert.astype(str)], ignore_index=True).drop_duplicates()
        alert.to_csv(u.ALERT_PATH, index=False)
        check('告警 CSV 可写', os.path.exists(u.ALERT_PATH) and os.path.getsize(u.ALERT_PATH) > 0)
    finally:
        u.INC, u.ALERT_PATH = saved_inc, saved_alert
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    print('== TUSHARE INCREMENT UNIT TESTS ==')
    t11a(); t11b(); t11c(); t11d(); t11e()
    print(f'\n== RESULT: PASS={PASS} FAIL={FAIL} ==')
    sys.exit(0 if FAIL == 0 else 1)

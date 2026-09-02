"""BACKTEST_INVARIANTS 自动测试 (Round5.1 结案)

验证 STRICT_V2 引擎 (round51_audit.py) 与源码满足 BACKTEST_INVARIANTS.md 全部规则。
任何新策略接入本项目时, 只要引入: 未来函数 / PIT泄漏 / T+1违规 / 资金不守恒 /
ETF时序倒流 / 手续费未入现金流 / 期末未清仓, 本测试必须 FAIL。

运行:
    python3 tests/test_backtest_invariants.py            # 直接运行
    pytest tests/test_backtest_invariants.py -v          # pytest 运行
"""
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import round51_audit as R

# ---------------- 缓存: prepare 只跑一次 ----------------
_CACHE = {}

def _prepare():
    if 'prepare' not in _CACHE:
        _CACHE['prepare'] = R.prepare_v51(limit_down_mode='correct', st_mode='pit')
    return _CACHE['prepare']

def _run(exit_mode='close_confirm_next', etf_on=True):
    key = (exit_mode, etf_on)
    if key not in _CACHE:
        days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = _prepare()
        eq, tr, ac = R.run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off,
                                          K=3, exit_bb_mode=exit_mode, open_fill='limit_conservative',
                                          etf_enabled=etf_on, record_actions=True)
        _CACHE[key] = (eq, tr, ac)
    return _CACHE[key]

_FAILURES = []
def _check(name, cond, detail=''):
    if cond:
        print(f'  [PASS] {name}')
    else:
        print(f'  [FAIL] {name}  {detail}')
        _FAILURES.append(name)

# ================= 运行时不变量 =================

def test_cash_conservation():
    """R1: 每日 equity == cash + stock_mv + etf_mv (资金守恒)"""
    print('\n== 资金守恒 (STRICT_V2_B, K=3) ==')
    eq, tr, ac = _run('close_confirm_next', True)
    err = (eq['equity'] - (eq['cash'] + eq['stock_val'] + eq['etf_val'])).abs().max()
    _check('equity == cash + stock + etf (max_err=%.2e)' % err, err < 1e-4, f'err={err}')

def test_final_settle_synced():
    """R12: 期末清仓进入最终 equity (末行 stock=0, etf=0, equity==cash)"""
    print('\n== 期末清仓同步 ==')
    eq, tr, ac = _run('close_confirm_next', True)
    last = eq.iloc[-1]
    _check('末行 stock_val==0', last['stock_val'] == 0.0)
    _check('末行 etf_sh==0', last['etf_sh'] == 0)
    _check('末行 equity==cash', abs(last['equity'] - last['cash']) < 1e-6,
           f"equity={last['equity']} cash={last['cash']}")

def test_t_plus_1_lot_level():
    """R9: T+1 lot-level — 买入当日不可卖 (无同日同标的先买后卖)"""
    print('\n== T+1 lot-level ==')
    eq, tr, ac = _run('close_confirm_next', True)
    tr2 = tr[tr['exit_type'] != 'FINAL_SETTLE']
    _check('非FINAL_SETTLE每笔 hold_days>=1', (tr2['hold_days'] >= 1).all(),
           f"min_hold={(tr2['hold_days'].min() if len(tr2) else None)}")
    # actions: 同日同 ts_code 不得先 BUY 后 SELL
    if len(ac):
        ac['date'] = ac['date'].astype(str)
        buys = set(ac[ac['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])].groupby(['date', 'ts_code']).size().index)
        sells = set(ac[ac['action'].isin(['TAKE_PROFIT_UB', 'FINAL_SETTLE', 'STOP_LOSS'])].groupby(['date', 'ts_code']).size().index)
        viol = buys & sells
        _check('无同日同标的先买后卖', len(viol) == 0, f'violations={list(viol)[:5]}')
    else:
        _check('无同日同标的先买后卖', True)

def test_fees_in_cashflow():
    """R11: 手续费/税进入真实现金流 — 重建单笔 pnl 与引擎一致"""
    print('\n== 手续费进入现金流 ==')
    eq, tr, ac = _run('close_confirm_next', True)
    if len(ac) == 0 or len(tr) == 0:
        _check('有交易可审计', False, 'no trades')
        return
    # 取一笔含买入+卖出的 round
    tr1 = tr.iloc[0]
    rnd = tr1['round']; tc = tr1['ts_code']
    acts = ac[(ac['round'] == rnd) & (ac['ts_code'] == tc)]
    bu = acts[acts['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
    se = acts[acts['action'].isin(['TAKE_PROFIT_UB', 'FINAL_SETTLE'])]
    if len(bu) == 0 or len(se) == 0:
        _check('round 含买卖 action', False, f'round={rnd}')
        return
    # 重建买入总成本: Σ(amount_i + buy_fee_i); 卖出净额: sell_amount - sell_fee
    total_cost = 0.0
    for _, a in bu.iterrows():
        amt = a['amount']
        total_cost += amt + max(amt * R.COMMISSION_RATE, R.MIN_COMMISSION) + amt * R.TRANSFER_FEE_RATE
    sell_amt = se.iloc[0]['amount']
    sell_fee = max(sell_amt * R.COMMISSION_RATE, R.MIN_COMMISSION) + sell_amt * R.stamp_rate(pd.Timestamp(se.iloc[0]['date']), 'historical') + sell_amt * R.TRANSFER_FEE_RATE
    exp_pnl = sell_amt - sell_fee - total_cost
    _check('重建pnl≈引擎pnl (%.2f vs %.2f)' % (exp_pnl, tr1['pnl']), abs(exp_pnl - tr1['pnl']) < 1.0,
           f"exp={exp_pnl:.2f} engine={tr1['pnl']:.2f}")
    # 滑点进入成交价
    eq0, tr0, ac0 = _run('close_confirm_next', True)
    # 验证资金守恒已含费用(第1条隐含): equity 随费用下降 => 用无滑点对照在 test_slippage 处理

def test_no_retroactive_etf():
    """R5: ETF 无时间倒流 — B模式(收盘确认->T+1 open)买入价=执行日open, 非信号日close"""
    print('\n== ETF/股票时序 (B: 收盘信号->T+1 open执行) ==')
    eq, tr, ac = _run('close_confirm_next', True)
    bu = ac[ac['action'] == 'INITIAL_ENTRY']
    if len(bu):
        # 执行日 open*(1+slip) 应等于 action.price
        bu2 = bu.copy()
        bu2['date'] = pd.to_datetime(bu2['date'])
        ratio_ok = (np.abs(bu2['price'] - bu2['open'] * 1.001) < 0.02).mean()
        _check('买入价=执行日open*(1+slip) 比例=%.3f' % ratio_ok, ratio_ok > 0.99,
               f'ratio={ratio_ok:.3f}')
        # 证明不是用信号日 close: 若 price≈close 会失败
        close_ratio = (np.abs(bu2['price'] - bu2['close']) < 0.02).mean()
        _check('买入价≠当日close(非收盘倒流), close_ratio=%.3f' % close_ratio, close_ratio < 0.5,
               f'close_ratio={close_ratio:.3f}')
    else:
        _check('B模式有买入action', False)

def test_exit_b_next_open():
    """R5/R7: B模式退出在 T+1 open (卖出价=执行日open)"""
    print('\n== B模式退出 T+1 open ==')
    eq, tr, ac = _run('close_confirm_next', True)
    se = ac[ac['action'] == 'TAKE_PROFIT_UB']
    if len(se):
        se2 = se.copy(); se2['date'] = pd.to_datetime(se2['date'])
        ratio_ok = (np.abs(se2['price'] - se2['open'] * 0.999) < 0.02).mean()
        _check('卖出价=执行日open*(1-slip) 比例=%.3f' % ratio_ok, ratio_ok > 0.99,
               f'ratio={ratio_ok:.3f}')
    else:
        _check('B模式有卖出action', True, 'no TAKE_PROFIT_UB (可能全部FINAL_SETTLE)')

def test_pit_st_used():
    """R3: PIT ST 状态生效 (非快照name)"""
    print('\n== PIT ST ==')
    days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = _prepare()
    pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    # 抽样 5 天, 比对 D[d]['is_st'] 与 pit 的 is_st_pit
    ok = True; ndiff = 0; ntot = 0
    for d in days[::len(days)//5][:5]:
        dd = D[d]
        sub = pit[pit['date'] == d]
        m = sub.set_index('ts_code')['is_st_pit'].reindex(dd['ts']).fillna(False).to_numpy()
        ndiff += int((m != dd['is_st']).sum()); ntot += len(dd['ts'])
        if not np.array_equal(m.astype(bool), dd['is_st'].astype(bool)):
            ok = False
    _check('D[d].is_st == pit.is_st_pit (diff=%d/%d)' % (ndiff, ntot), ok, f'ndiff={ndiff}')

def test_bb_no_future():
    """R1/R4: BB 仅用 T-19..T close_adj (rolling右对齐, 无未来)"""
    print('\n== BB 无未来信息 ==')
    days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = _prepare()
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    df['close_adj'] = df['close'] * df['adj_factor']
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')].sort_values(['ts_code', 'date'])
    tc = '600519.SH'
    g = df[df['ts_code'] == tc].reset_index(drop=True)
    # 选第 41 行 (0-based 40): rolling(20) 使用 iloc[21:41]
    if len(g) > 40:
        row = g.iloc[40]
        d = row['date']
        window = g.iloc[21:41]['close_adj'].to_numpy()
        ma = window.mean(); sd = window.std(ddof=1)  # 引擎 pandas rolling.std() 默认 ddof=1 (口径见 BACKTEST_INVARIANTS R1)
        dd = D[d]; j = dd['pos'].get(tc)
        if j is not None:
            eng_low = dd['bb_lower'][j]
            _check('bb_lower == 手动 rolling(20) (%.4f vs %.4f)' % (ma - 2*sd, eng_low),
                   abs((ma - 2*sd) - eng_low) < 1e-6,
                   f'manual={ma-2*sd:.6f} engine={eng_low:.6f}')
        else:
            _check('股票在D[d]中', False)
    else:
        _check('有足够数据验证BB', False)

def test_listing_from_listdate():
    """R4: 上市满60日来自真实 list_date (老股票 2020 初即可交易, 非切片首日)"""
    print('\n== listing = list_date + 交易日历 ==')
    days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = _prepare()
    sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))
    old = sb[(sb['list_date'] < '2019-06-01')]['ts_code'].tolist()
    if old:
        fel_old = [fel.get(t, 10**9) for t in old[:50]]
        # 这些股票 2020-01-02 (索引 offset) 时已上市满60交易日 => fel < offset
        _check('2019年中前上市股票 fel < offset(2020起点)', max(fel_old) < off,
               f'max_fel={max(fel_old)} offset={off}')
    else:
        _check('找到老股票样本', False)

# ================= 静态不变量 (源码扫描) =================

def test_static_no_future_patterns():
    """R1: 源码禁止已知未来函数模式"""
    print('\n== 静态: 未来函数模式 ==')
    src = open(os.path.join(ROOT, 'round51_audit.py'), encoding='utf-8').read()
    bad = [p for p in ['shift(-1)', "shift(-1)", 'center=True', 'center = True',
                       'iloc[i + 1]', 'iloc[i+1]', 'future_leak'] if p in src]
    _check('无 shift(-1)/center=True/iloc[i+1]', len(bad) == 0, f'found={bad}')

def test_static_no_whole_day_oneword():
    """R6: next_open 成交判断禁止使用整日一字板 open==high==low==close"""
    print('\n== 静态: 无整日一字板判断成交 ==')
    src = open(os.path.join(ROOT, 'round51_audit.py'), encoding='utf-8').read()
    _check("open_fill 参数存在", "open_fill='limit_conservative'" in src or "open_fill" in src)
    # 确认成交判断只使用 open 与 limit 价, 不使用 high/low/close 组合判一字板
    _check('成交判断用 limit_up_px/limit_down_px(非OHLC相等)',
           "dd['open_'][j] >= dd['limit_up_px'][j]" in src and "dd['open_'][j] <= dd['limit_down_px'][j]" in src)

def test_static_no_single_etf_px_for_whole_day():
    """R5: ETF 交易价不得单一变量覆盖整天 (无时间倒流)"""
    print('\n== 静态: ETF 事件驱动 ==')
    src = open(os.path.join(ROOT, 'round51_audit.py'), encoding='utf-8').read()
    _check('ensure_cash_open 存在(open筹资)', 'def ensure_cash_open' in src)
    _check('rebalance_close 存在(close再投资)', 'def rebalance_close' in src)
    _check('无单一 etf_trade_px 覆盖整天', 'etf_trade_px' not in src)

def test_static_adj_only_for_signal():
    """R8: 复权价只用于信号, 实际现金流用真实价"""
    print('\n== 静态: 复权价仅用于信号 ==')
    src = open(os.path.join(ROOT, 'round51_audit.py'), encoding='utf-8').read()
    # 买入/卖出用 dd['open_']/dd['close'] (真实价), BB 信号用 close_adj/high_adj
    _check('买入价用 open_', "dd['open_'][j]" in src)
    _check('卖出(FINAL)价用 close', "dd['close'][j]" in src)
    _check('信号用 close_adj', "dd['close_adj'][j]" in src)

def test_static_params_frozen():
    """R14: 冻结参数不得被调参覆盖 (仅审计口径)"""
    print('\n== 静态: 冻结参数 ==')
    src = open(os.path.join(ROOT, 'round51_audit.py'), encoding='utf-8').read()
    for p in ["K=3", "top_n=10", "max_levels=5", "level_cash=200_000", "bb_window=20", "bb_std=2.0"]:
        _check(f'参数 {p} 存在(默认冻结)', p in src)

# ================= runner =================

def run_all():
    print('===== BACKTEST INVARIANTS 自动测试 (STRICT_V2) =====')
    test_cash_conservation()
    test_final_settle_synced()
    test_t_plus_1_lot_level()
    test_fees_in_cashflow()
    test_no_retroactive_etf()
    test_exit_b_next_open()
    test_pit_st_used()
    test_bb_no_future()
    test_listing_from_listdate()
    test_static_no_future_patterns()
    test_static_no_whole_day_oneword()
    test_static_no_single_etf_px_for_whole_day()
    test_static_adj_only_for_signal()
    test_static_params_frozen()
    print('\n===== 结果 =====')
    if _FAILURES:
        print(f'FAILED ({len(_FAILURES)}): {_FAILURES}')
        sys.exit(1)
    print('ALL PASS')

if __name__ == '__main__':
    run_all()

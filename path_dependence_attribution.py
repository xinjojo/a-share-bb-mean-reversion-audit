#!/usr/bin/env python3
"""PATH DEPENDENCE ATTRIBUTION — 股票PnL变化小 vs 组合收益变化大的精确归因
任务A Equity Identity / 任务B 7项Attribution / 任务C First Divergence Trace / 任务D CF_FIXED_ETF_PATH
不改策略/不调参/不开Validation/不改Registry. 复用 STRICT_C_EXECUTABLE_TICK 引擎(flow_sink只读埋点).
"""
import sys, os
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import full_stats
from run_strict_c import run_fast_multi_strict_c
from stress_test_v2 import prepare_v51_pert

SC = [('S0', 0.0, 1.0)] + [
    (f'S{ {0.00002:"1", 0.0001:"2", 0.0005:"3"}[e] }{sgn}', e, sgn)
    for e in (0.00002, 0.0001, 0.0005) for sgn in (1.0, -1.0)]

def run_one(eps, sign):
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51_pert(eps, sign)
    flows = []
    eq, tr, ac, pa = run_fast_multi_strict_c(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', day_range=(0, len(days)),
        record_actions=True, flow_sink=flows)
    return eq, tr, ac, pd.DataFrame(flows), days

def identity_check(eq):
    err = (eq['equity'] - (eq['cash'] + eq['stock_val'] + eq['etf_val'])).abs()
    return float(err.max()), float(err.mean())

def attribution(fl, eq, initial=1_000_000):
    s_buy = fl[(fl.leg=='stock') & (fl.action=='buy')]
    s_sell = fl[(fl.leg=='stock') & (fl.action.isin(['sell','settle']))]
    e_buy = fl[(fl.leg=='etf') & (fl.action=='buy')]
    e_sell = fl[(fl.leg=='etf') & (fl.action.isin(['sell','settle']))]
    d = dict(
        stock_realized_gross = float(s_sell.gross.sum() - s_buy.gross.sum()),
        stock_cost = -float(s_buy.fee.sum() + s_sell.fee.sum()),
        stock_unrealized_final = 0.0,          # 期末全清
        etf_realized_gross = float(e_sell.gross.sum() - e_buy.gross.sum()),
        etf_cost = -float(e_buy.fee.sum() + e_sell.fee.sum()),
        etf_final_holding = 0.0,               # 期末全清
        cash_diff = 0.0,
    )
    stock_net = float(s_sell.net.sum() + s_buy.net.sum())
    etf_net = float(e_sell.net.sum() + e_buy.net.sum())
    final_equity = float(eq['equity'].iloc[-1])
    recon = sum(d.values())
    # 交叉验证: 净现金流和 == final - initial
    return d, stock_net, etf_net, final_equity, recon, float(stock_net + etf_net - (final_equity - initial))

def first_divergence(eq0, eq1):
    m = eq0[['date','equity','cash','stock_val','etf_sh','etf_val']].merge(
        eq1[['date','equity','cash','stock_val','etf_sh','etf_val']], on='date', suffixes=('_0','_1'))
    diff = m[np.abs(m.equity_0 - m.equity_1) > 1e-4]
    if len(diff) == 0:
        return None
    return diff.iloc[0].to_dict()

if __name__ == '__main__':
    res = {}
    for tag, e, s in SC:
        print(f'>>> {tag}', flush=True)
        eq, tr, ac, fl, days = run_one(e, s)
        res[tag] = dict(eq=eq, tr=tr, ac=ac, fl=fl, st=full_stats(eq, tr))
        print(f'    return={res[tag]["st"]["total"]:.2f} trades={len(tr)} flows={len(fl)}', flush=True)

    # ===== 任务A: Equity Identity =====
    print('\n===== A. Equity Identity (每日 equity == cash+stock+etf) =====')
    for tag in [t for t,_,_ in SC]:
        mx, mn = identity_check(res[tag]['eq'])
        print(f'  {tag}: max_err={mx:.6f} mean_err={mn:.8f}')

    # ===== 任务B: 7项 Attribution =====
    print('\n===== B. Attribution (vs S0) =====')
    att0, sn0, en0, fe0, rec0, bal0 = attribution(res['S0']['fl'], res['S0']['eq'])
    rowsB = []
    for tag in [t for t,_,_ in SC]:
        att, sn, en, fe, rec, bal = attribution(res[tag]['fl'], res[tag]['eq'])
        d = {k: att[k] - att0[k] for k in att}
        d['stock_net'] = sn - sn0; d['etf_net'] = en - en0
        d['final_equity'] = fe - fe0
        d['scenario'] = tag
        rowsB.append(d)
    dfB = pd.DataFrame(rowsB)
    pd.set_option('display.width', 260); pd.set_option('display.max_columns', 40)
    print(dfB[['scenario','stock_realized_gross','stock_cost','etf_realized_gross','etf_cost',
               'stock_net','etf_net','final_equity']].to_string(index=False))
    # reconciliation
    print('\nReconciliation (Δsum of 7项 vs Δfinal_equity):')
    for r in rowsB:
        s7 = r['stock_realized_gross'] + r['stock_cost'] + r['stock_unrealized_final'] + \
             r['etf_realized_gross'] + r['etf_cost'] + r['etf_final_holding'] + r['cash_diff']
        print(f'  {r["scenario"]}: Δ7项={s7:>12.2f}  Δfinal_equity={r["final_equity"]:>12.2f}  err={s7-r["final_equity"]:.8f}')

    # ===== 任务D: CF_FIXED_ETF_PATH =====
    print('\n===== D. CF_FIXED_ETF_PATH (股票腿经济差异 vs ETF路径放大) =====')
    print('scenario | comboΔ | stock-onlyΔ | ETF-path放大Δ | 方向')
    for r in rowsB:
        combo = r['final_equity']
        stock_only = r['stock_net']  # 含股票费用
        etf_amp = combo - stock_only
        print(f'  {r["scenario"]:>6} | {combo:>9.0f} | {stock_only:>9.0f} | {etf_amp:>11.0f} | {"放大" if abs(etf_amp)>abs(stock_only) else "股票主导"}')

    # ===== 任务C: First Divergence Trace =====
    print('\n===== C. First Divergence Trace (vs S0) =====')
    eq0 = res['S0']['eq']
    for tag in [t for t,_,_ in SC if t != 'S0']:
        fdv = first_divergence(eq0, res[tag]['eq'])
        if fdv is None:
            print(f'  {tag}: 无分歧'); continue
        print(f'  {tag}: first_divergence_date={fdv["date"]}')
        print(f'      baseline:  cash={fdv["cash_0"]:.0f} stock={fdv["stock_val_0"]:.0f} etf_sh={fdv["etf_sh_0"]} etf={fdv["etf_val_0"]:.0f} equity={fdv["equity_0"]:.0f}')
        print(f'      stress:    cash={fdv["cash_1"]:.0f} stock={fdv["stock_val_1"]:.0f} etf_sh={fdv["etf_sh_1"]} etf={fdv["etf_val_1"]:.0f} equity={fdv["equity_1"]:.0f}')
        # 当日及前后3日的 flows 差异
        d0 = fdv['date']
        fl0 = res['S0']['fl']; fl1 = res[tag]['fl']
        dates = sorted(set(fl0.date) | set(fl1.date))
        for dd in dates:
            if dd >= d0:
                a = fl0[fl0.date==dd][['date','leg','action','shares','px']]
                b = fl1[fl1.date==dd][['date','leg','action','shares','px']]
                ka = {tuple(x) for x in a.itertuples(index=False)}
                kb = {tuple(x) for x in b.itertuples(index=False)}
                if ka != kb:
                    print(f'      当日流水差异 {dd}:')
                    for x in sorted(ka - kb): print(f'        S0独有: {x}')
                    for x in sorted(kb - ka): print(f'        {tag}独有: {x}')
                    break

    # ===== 追踪 +1/+5/+20/+60/+120/final =====
    print('\n===== C2. 分歧传播 (equity差异 于 +1/+5/+20/+60/+120/final) =====')
    idx0 = {d: i for i, d in enumerate(res['S0']['eq']['date'])}
    for tag in [t for t,_,_ in SC if t != 'S0']:
        fdv = first_divergence(eq0, res[tag]['eq'])
        if fdv is None: continue
        d0 = fdv['date']
        i0 = idx0[d0]
        e1 = res[tag]['eq']
        print(f'  {tag}: divergence={d0}')
        for off in [1,5,20,60,120, len(e1)-1-i0]:
            ii = min(i0+off, len(e1)-1)
            dd = res['S0']['eq']['date'][ii]
            de = e1['equity'][ii] - eq0['equity'][ii]
            print(f'    +{off} ({dd}): Δequity={de:>10.0f}')

    # 保存
    out = []
    for r in rowsB:
        combo = r['final_equity']; stock_only = r['stock_net']
        out.append(dict(scenario=r['scenario'], delta_combo=combo, delta_stock_only=stock_only,
                        delta_etf_amplification=combo-stock_only,
                        delta_stock_realized_gross=r['stock_realized_gross'],
                        delta_stock_cost=r['stock_cost'],
                        delta_etf_realized_gross=r['etf_realized_gross'],
                        delta_etf_cost=r['etf_cost']))
    pd.DataFrame(out).to_csv(os.path.join(ROOT,'results','round5','adjfactor_attribution_v2.csv'), index=False)
    print('\nDONE. saved results/round5/adjfactor_attribution_v2.csv')

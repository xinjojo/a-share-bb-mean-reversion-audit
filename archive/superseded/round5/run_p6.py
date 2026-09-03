"""P6: K=3 流动性冲击分析
对实际 INITIAL_ENTRY / ADD_POSITION 读取当日 amount(千元), 计算 impact ratio
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    eq, tr, ac = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                   stamp_tax_mode='flat', record_actions=True)
    buy = ac[ac['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])].copy()
    buy['date'] = pd.to_datetime(buy['date'])
    buy = buy.rename(columns={'amount': 'trade_amount'})
    # amount 单位千元 -> 元
    amt_map = df[['date', 'ts_code', 'amount']].copy()
    amt_map['date'] = pd.to_datetime(amt_map['date'])
    amt_map = amt_map.rename(columns={'amount': 'day_amount_k'})
    m = buy.merge(amt_map, on=['date', 'ts_code'], how='left')
    m['day_amount_yuan'] = m['day_amount_k'] * 1000.0
    m['impact_ratio'] = m['trade_amount'] / m['day_amount_yuan']
    print(f"买入动作总数: {len(m)}  (缺amount匹配: {m['day_amount_yuan'].isna().sum()})")

    def report(sub, name):
        if len(sub) == 0:
            print(f"{name}: 无交易"); return
        ar = sub['impact_ratio'] * 100  # %
        print(f"\n[{name}] n={len(sub)}")
        print(f"  当日成交额(元): min={sub['day_amount_yuan'].min():,.0f} p5={sub['day_amount_yuan'].quantile(.05):,.0f} "
              f"median={sub['day_amount_yuan'].median():,.0f} p95={sub['day_amount_yuan'].quantile(.95):,.0f} max={sub['day_amount_yuan'].max():,.0f}")
        print(f"  impact ratio(%): min={ar.min():.4f} p5={ar.quantile(.05):.4f} median={ar.median():.4f} "
              f"p75={ar.quantile(.75):.4f} p95={ar.quantile(.95):.4f} max={ar.max():.4f}")
        print(f"  实际成交金额(元): min={sub['trade_amount'].min():,.0f} median={sub['trade_amount'].median():,.0f} max={sub['trade_amount'].max():,.0f}")
        for th in (0.05, 0.1, 0.5, 1.0):
            print(f"  impact<{th}%: {(ar < th).sum()}/{len(ar)}")
        return ar

    all_ar = report(m, 'ALL')
    ent = report(m[m['action'] == 'INITIAL_ENTRY'], 'INITIAL_ENTRY')
    add = report(m[m['action'] == 'ADD_POSITION'], 'ADD_POSITION')

    res = {'n_all': int(len(m)), 'n_entry': int((m['action']=='INITIAL_ENTRY').sum()), 'n_add': int((m['action']=='ADD_POSITION').sum())}
    for nm, sub in (('ALL', m), ('ENTRY', m[m['action']=='INITIAL_ENTRY']), ('ADD', m[m['action']=='ADD_POSITION'])):
        if len(sub):
            ar = sub['impact_ratio']*100
            res[nm] = {'impact_median_pct': round(float(ar.median()),4), 'impact_p95_pct': round(float(ar.quantile(.95)),4),
                       'impact_max_pct': round(float(ar.max()),4),
                       'impact_all_lt_0_05pct': bool((ar < 0.05).all()),
                       'day_amt_median': round(float(sub['day_amount_yuan'].median()),0)}
    with open(f'{OUT}/p6_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    m[['date','ts_code','action','trade_amount','day_amount_yuan','impact_ratio']].to_csv(f'{OUT}/p6_liquidity.csv', index=False)
    print('\nP6 done.')

if __name__ == '__main__':
    main()

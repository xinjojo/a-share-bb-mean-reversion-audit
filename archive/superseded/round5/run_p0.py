"""P0: BB上轨止盈未来信息验证 - V0(current) vs V1(prev_bb) vs V2(close_confirm_next)
K=1, K=3 全跑。用 etf_mark='close'（严格场内口径）与 'nav'（原口径）分别报告。
"""
import sys, time, json
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'

def run_one(K, exit_mode, etf_mark, stamp='flat'):
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=K,
                               exit_bb_mode=exit_mode, buy_mode='close', etf_mark=etf_mark,
                               stamp_tax_mode=stamp)
    s = full_stats(eq, tr)
    stock_pnl = tr['pnl'].sum() if len(tr) else 0.0
    return eq, tr, s, stock_pnl

def main():
    os.makedirs(OUT, exist_ok=True)
    results = []
    # 先加载一次数据复用
    for K in (1, 3):
        for mode in ('current', 'prev', 'close_confirm_next'):
            for mark in ('close', 'nav'):
                eq, tr, s, spnl = run_one(K, mode, mark)
                results.append({'K': K, 'exit_mode': mode, 'etf_mark': mark,
                                'total': round(s['total'], 2), 'ann': round(s['ann'], 2),
                                'mdd': round(s['mdd'], 2), 'sharpe': round(s['sharpe'], 3),
                                'trades': s['n'], 'wr': round(s['wr'], 2), 'stock_pnl': round(spnl, 0)})
                print(f"K={K} {mode} {mark}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% "
                      f"sharpe={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={spnl:,.0f}")
    dfr = pd.DataFrame(results)
    dfr.to_csv(f'{OUT}/p0_matrix.csv', index=False)

    # V0 vs V1 差异明细 (K=3, close口径)
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    eq0, tr0, s0, sp0 = run_one(3, 'current', 'close')
    eq1, tr1, s1, sp1 = run_one(3, 'prev', 'close')
    # 按 round 对齐（同 ts_code+entry_date）
    tr0['key'] = tr0['ts_code'] + '|' + tr0['entry_date']
    tr1['key'] = tr1['ts_code'] + '|' + tr1['entry_date']
    m = pd.merge(tr0, tr1, on='key', suffixes=('_v0', '_v1'), how='outer', indicator=True)
    both = m[m['_merge'] == 'both'].copy()
    print(f"\n[K=3 V0 vs V1] 共同交易: {len(both)} / V0独有: {(m['_merge']=='left_only').sum()} / V1独有: {(m['_merge']=='right_only').sum()}")
    both['exit_date_diff'] = both['exit_date_v0'] != both['exit_date_v1']
    print(f"退出日期不同笔数: {both['exit_date_diff'].sum()} / {len(both)}")
    # 退出价格差：v5 trades 没有直接 exit_price，用 pnl/return 反推成本，这里用 pnl 差与日期差衡量
    both['pnl_diff'] = both['pnl_v0'] - both['pnl_v1']
    print(f"V0-V1 股票PnL差(共同): {both['pnl_diff'].sum():,.0f} 元")
    print(f"平均每笔pnl差: {both['pnl_diff'].mean():,.0f} 元")
    both = both.sort_values('pnl_diff', key=lambda s: s.abs(), ascending=False)
    top = both.head(10)[['ts_code_v0', 'entry_date_v0', 'exit_date_v0', 'exit_date_v1', 'pnl_v0', 'pnl_v1', 'pnl_diff']]
    top.columns = ['ts_code', 'entry_date', 'exit_date_v0', 'exit_date_v1', 'pnl_v0', 'pnl_v1', 'pnl_diff']
    print("\n差异最大的10笔:")
    print(top.to_string())
    top.to_csv(f'{OUT}/p0_v0_vs_v1_top10.csv', index=False)

    # 汇总
    summary = {
        'V0_CURRENT_K3_close': {'total': round(s0['total'],2), 'mdd': round(s0['mdd'],2), 'sharpe': round(s0['sharpe'],3), 'stock_pnl': round(sp0,0)},
        'V1_PREVBB_K3_close': {'total': round(s1['total'],2), 'mdd': round(s1['mdd'],2), 'sharpe': round(s1['sharpe'],3), 'stock_pnl': round(sp1,0)},
    }
    with open(f'{OUT}/p0_summary.json', 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("\nSummary:", json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    import os
    main()

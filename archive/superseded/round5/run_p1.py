"""P1: K=3 严格 next_open 全链路 vs close 全链路
close      : 信号与成交均 T 日收盘 (冻结基线逻辑, exit current + buy close)
next_open  : T 日收盘信号 -> T+1 open 成交 (买入/加仓/退出均 next_open, ETF 用 open)
"""
import sys, time, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    # K3 close: exit current + buy close（冻结基线对应, close估值严格口径）
    eq_c, tr_c = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                   stamp_tax_mode='flat')
    s_c = full_stats(eq_c, tr_c)
    spn_c = tr_c['pnl'].sum()
    print(f"K3_close: total={s_c['total']:.2f}% ann={s_c['ann']:.2f}% mdd={s_c['mdd']:.2f}% "
          f"sharpe={s_c['sharpe']:.3f} n={s_c['n']} wr={s_c['wr']:.1f}% stock_pnl={spn_c:,.0f}")

    # K3 next_open: exit close_confirm_next + buy next_open
    eq_n, tr_n = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   exit_bb_mode='close_confirm_next', buy_mode='next_open', etf_mark='close',
                                   stamp_tax_mode='flat')
    s_n = full_stats(eq_n, tr_n)
    spn_n = tr_n['pnl'].sum()
    print(f"K3_next_open: total={s_n['total']:.2f}% ann={s_n['ann']:.2f}% mdd={s_n['mdd']:.2f}% "
          f"sharpe={s_n['sharpe']:.3f} n={s_n['n']} wr={s_n['wr']:.1f}% stock_pnl={spn_n:,.0f}")

    # 逐笔差异（按 ts_code+entry_date 对齐）
    tr_c['key'] = tr_c['ts_code'] + '|' + tr_c['entry_date']
    tr_n['key'] = tr_n['ts_code'] + '|' + tr_n['entry_date']
    m = pd.merge(tr_c, tr_n, on='key', suffixes=('_c', '_n'), how='outer', indicator=True)
    both = m[m['_merge'] == 'both'].copy()
    print(f"\n共同: {len(both)} / close独有: {(m['_merge']=='left_only').sum()} / next_open独有: {(m['_merge']=='right_only').sum()}")
    both['date_diff'] = both['exit_date_c'] != both['exit_date_n']
    print(f"退出日期不同: {both['date_diff'].sum()}/{len(both)}")
    both['pnl_diff'] = both['pnl_c'] - both['pnl_n']
    print(f"股票PnL差(close-next_open): {both['pnl_diff'].sum():,.0f} 元")

    # 汇总输出
    res = {
        'K3_close': {'total': round(s_c['total'],2), 'ann': round(s_c['ann'],2), 'mdd': round(s_c['mdd'],2),
                     'sharpe': round(s_c['sharpe'],3), 'trades': int(s_c['n']), 'wr': round(s_c['wr'],2),
                     'stock_pnl': round(spn_c,0)},
        'K3_next_open': {'total': round(s_n['total'],2), 'ann': round(s_n['ann'],2), 'mdd': round(s_n['mdd'],2),
                         'sharpe': round(s_n['sharpe'],3), 'trades': int(s_n['n']), 'wr': round(s_n['wr'],2),
                         'stock_pnl': round(spn_n,0)},
    }
    with open(f'{OUT}/p1_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print('\nP1 Summary:', json.dumps(res, ensure_ascii=False))
    pd.DataFrame([res['K3_close'], res['K3_next_open']]).to_csv(f'{OUT}/p1_matrix.csv', index=False)

if __name__ == '__main__':
    main()

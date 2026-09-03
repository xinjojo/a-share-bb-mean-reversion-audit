"""STRICT_V1 OOS + ETF贡献拆解 + 分年稳定性
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='correct')
    dts = [d.strftime('%Y-%m-%d') for d in days]
    train_end = dts.index('2023-12-29') + 1

    def run(buy, slip, stamp, etf_on, day_range=None, etf_mark='close'):
        eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   exit_bb_mode='close_confirm_next', buy_mode=buy, etf_mark=etf_mark,
                                   slippage_bp=slip, stamp_tax_mode=stamp,
                                   execution_constraints=True, etf_enabled=etf_on, day_range=day_range)
        return eq, tr

    # STRICT_V1 (close买入) 全样本 + OOS
    rows = []
    for name, buy, slip, stamp, etf_on, rng in [
        ('STRICT_V1', 'close', 10, 'flat', True, None),
        ('STRICT_V1_train', 'close', 10, 'flat', True, (0, train_end)),
        ('STRICT_V1_test', 'close', 10, 'flat', True, (train_end, len(days))),
        ('STRICT_V1_full', 'next_open', 10, 'historical', True, None),
        ('STRICT_V1_full_train', 'next_open', 10, 'historical', True, (0, train_end)),
        ('STRICT_V1_full_test', 'next_open', 10, 'historical', True, (train_end, len(days))),
        ('STRICT_V1_stock_only', 'close', 10, 'flat', False, None),
        ('STRICT_V1_nextopen_stock_only', 'next_open', 10, 'historical', False, None),
    ]:
        eq, tr = run(buy, slip, stamp, etf_on, rng)
        s = full_stats(eq, tr)
        rows.append({'version': name, 'total': round(s['total'],2), 'ann': round(s['ann'],2),
                     'mdd': round(s['mdd'],2), 'sharpe': round(s['sharpe'],3), 'trades': s['n'],
                     'wr': round(s['wr'],2), 'stock_pnl': round(tr['pnl'].sum(),0)})
        print(f"{name}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% shp={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={tr['pnl'].sum():,.0f}")

    # 分年收益 (STRICT_V1)
    eq, tr = run('close', 10, 'flat', True)
    eq['year'] = pd.to_datetime(eq['date']).dt.year
    yearly = []
    for y, g in eq.groupby('year'):
        yret = g['equity'].iloc[-1] / g['equity'].iloc[0] - 1
        yearly.append({'year': int(y), 'ret': round(yret*100,2)})
    print("\nSTRICT_V1 分年收益:", yearly)
    rows.append({'version': 'yearly', 'detail': yearly})

    with open(f'{OUT}/strict_oos.json', 'w') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    print('\nSTRICT OOS done.')

if __name__ == '__main__':
    main()

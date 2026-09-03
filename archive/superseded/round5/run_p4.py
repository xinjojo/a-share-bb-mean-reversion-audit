"""P4: K=3 时间止损
全区间扫描 time_stop ∈ {None,10,15,20,30,40} trading days (K=3, 其他冻结)
OOS: Train 2020-2023 选最佳 time_stop -> Test 2024-2026 报告该参数表现
注: 这是研究实验, 不允许直接挑全样本最高参数作为新策略
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    # 找到 2023-12-31 和 2024-01-01 的索引
    dts = [d.strftime('%Y-%m-%d') for d in days]
    train_end = dts.index('2023-12-29') + 1 if '2023-12-29' in dts else None
    test_start = dts.index('2024-01-02') if '2024-01-02' in dts else None
    print(f'train_end_idx={train_end}, test_start_idx={test_start}')
    n = len(days)

    rows = []
    # 全区间
    for ts in (None, 10, 15, 20, 30, 40):
        eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   time_stop_days=ts, exit_bb_mode='current', buy_mode='close',
                                   etf_mark='close', stamp_tax_mode='flat')
        s = full_stats(eq, tr)
        sp = tr['pnl'].sum()
        rows.append({'time_stop': str(ts), 'total': round(s['total'],2), 'ann': round(s['ann'],2),
                     'mdd': round(s['mdd'],2), 'sharpe': round(s['sharpe'],3), 'trades': s['n'],
                     'wr': round(s['wr'],2), 'stock_pnl': round(sp,0)})
        print(f"time_stop={ts}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% "
              f"sharpe={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={sp:,.0f}")

    # OOS: Train 2020-2023 (best on train), Test 2024-2026
    oos_rows = []
    for ts in (None, 10, 15, 20, 30, 40):
        # train
        eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   time_stop_days=ts, exit_bb_mode='current', buy_mode='close',
                                   etf_mark='close', stamp_tax_mode='flat', day_range=(0, train_end))
        s_tr = full_stats(eq, tr, initial_cash=1_000_000)
        # test (独立, 从 test_start 开始新账户)
        eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   time_stop_days=ts, exit_bb_mode='current', buy_mode='close',
                                   etf_mark='close', stamp_tax_mode='flat', day_range=(test_start, n))
        s_te = full_stats(eq, tr, initial_cash=1_000_000)
        oos_rows.append({'time_stop': str(ts), 'train_total': round(s_tr['total'],2),
                         'train_n': s_tr['n'], 'train_wr': round(s_tr['wr'],2),
                         'test_total': round(s_te['total'],2), 'test_n': s_te['n'],
                         'test_wr': round(s_te['wr'],2), 'test_sharpe': round(s_te['sharpe'],3)})
        print(f"OOS ts={ts}: train={s_tr['total']:.2f}%(n={s_tr['n']}) test={s_te['total']:.2f}%(n={s_te['n']}, shp={s_te['sharpe']:.2f})")

    # 选出 train 最优
    best = max([r for r in oos_rows if r['time_stop'] != 'None'], key=lambda r: r['train_total'])
    base_none = next(r for r in oos_rows if r['time_stop'] == 'None')
    print(f"\nTrain最优: time_stop={best['time_stop']} (train={best['train_total']}%)")
    print(f"Test表现: {best['time_stop']} -> {best['test_total']}% vs None(冻结) -> {base_none['test_total']}%")

    res = {'full_scan': rows, 'oos': oos_rows,
           'train_best': best['time_stop'], 'test_train_best': best['test_total'],
           'test_none': base_none['test_total']}
    with open(f'{OUT}/p4_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    pd.DataFrame(rows).to_csv(f'{OUT}/p4_time_stop_scan.csv', index=False)
    pd.DataFrame(oos_rows).to_csv(f'{OUT}/p4_oos.csv', index=False)
    print('\nP4 done.')

if __name__ == '__main__':
    main()

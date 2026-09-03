"""STRICT_V2 OOS + 分年 + ETF归因
"""
import sys, os, json
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round51_audit import prepare_v51, run_fast_multi_v51, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = prepare_v51(limit_down_mode='correct', st_mode='pit')
    dts = [d.strftime('%Y-%m-%d') for d in days]
    train_end = dts.index('2023-12-29') + 1

    def run(exit_mode, etf_on, day_range=None):
        eq, tr, ac = run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off, K=3,
                                        exit_bb_mode=exit_mode, open_fill='limit_conservative',
                                        etf_enabled=etf_on, day_range=day_range)
        return eq, tr

    rows = []
    for tag, exit_mode in (('A_prev', 'prev'), ('B_confirm', 'close_confirm_next')):
        for etf_on, etf_tag in ((True, 'etf_on'), (False, 'stock_only')):
            for rng, rtag in ((None, 'full'), ((0, train_end), 'train'), ((train_end, len(days)), 'test')):
                eq, tr = run(exit_mode, etf_on, rng)
                s = full_stats(eq, tr)
                rows.append({'version': f'STRICT_V2_{tag}_{etf_tag}_{rtag}', 'exit': tag, 'etf': etf_tag, 'range': rtag,
                             'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                             'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                             'stock_pnl': round(tr['pnl'].sum(),0) if len(tr) else 0})
                print(f"STRICT_V2_{tag}_{etf_tag}_{rtag}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% shp={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={tr['pnl'].sum():,.0f}")

    # 分年 (STRICT_V2 A/B, ETF on)
    for tag, exit_mode in (('A_prev', 'prev'), ('B_confirm', 'close_confirm_next')):
        eq, tr = run(exit_mode, True)
        eq['year'] = pd.to_datetime(eq['date']).dt.year
        for y, g in eq.groupby('year'):
            yret = g['equity'].iloc[-1] / g['equity'].iloc[0] - 1
            rows.append({'version': f'STRICT_V2_{tag}_yearly_{int(y)}', 'year': int(y), 'total': round(yret*100,2)})
            print(f"STRICT_V2_{tag} {int(y)}: {yret*100:.2f}%")

    # ETF buy&hold (全区间)
    p0 = etf_px[etf_idx.get(days[0])]
    p1 = etf_px[etf_idx.get(days[-1])]
    print(f"\nETF buy&hold: {(p1/p0-1)*100:.2f}%")
    rows.append({'version': 'ETF_BUYHOLD', 'total': round((p1/p0-1)*100,2)})

    pd.DataFrame(rows).to_csv(f'{OUT}/strict_v2_oos.csv', index=False)
    with open(f'{OUT}/strict_v2_oos.json', 'w') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    print('\nSTRICT_V2 OOS done.')

if __name__ == '__main__':
    main()

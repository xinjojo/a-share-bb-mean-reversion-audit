"""STRICT_V2 矩阵: A/B 退出 × open_fill 上下界 × PIT/snapshot ST
"""
import sys, os, json
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round51_audit import prepare_v51, run_fast_multi_v51, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = prepare_v51(limit_down_mode='correct', st_mode='pit')
    print('prepare OK, days=', len(days), 'offset=', offset)
    days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, first_eli2, offset2 = prepare_v51(limit_down_mode='correct', st_mode='snapshot')

    def run(dd, DD, ei, epx, eopx, enav, fel, off, exit_mode, open_fill, etf_on=True, st_tag='pit'):
        eq, tr, ac = run_fast_multi_v51(dd, DD, ei, epx, eopx, enav, fel, off, K=3,
                                        exit_bb_mode=exit_mode, open_fill=open_fill,
                                        etf_enabled=etf_on, record_actions=False)
        s = full_stats(eq, tr)
        return s, tr, eq

    rows = []
    for st_tag, (dd, DD, ei, epx, eopx, enav, fel, off) in {'pit': (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset),
                                                             'snapshot': (days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, first_eli2, offset2)}.items():
        for exit_mode in ('prev', 'close_confirm_next'):
            for open_fill in ('optimistic', 'limit_conservative'):
                s, tr, eq = run(dd, DD, ei, epx, eopx, enav, fel, off, exit_mode, open_fill, True, st_tag)
                name = f"STRICT_V2_{'A' if exit_mode=='prev' else 'B'}_{open_fill}_{st_tag}"
                rows.append({'version': name, 'exit': exit_mode, 'open_fill': open_fill, 'st': st_tag,
                             'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                             'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                             'stock_pnl': round(tr['pnl'].sum(),0) if len(tr) else 0})
                print(f"{name}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% shp={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={tr['pnl'].sum():,.0f}")

    # 纯股票 (ETF off)
    for exit_mode, tag in (('prev', 'A'), ('close_confirm_next', 'B')):
        for open_fill in ('optimistic', 'limit_conservative'):
            s, tr, eq = run(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, exit_mode, open_fill, False)
            name = f"STRICT_V2_{tag}_{open_fill}_stock_only"
            rows.append({'version': name, 'exit': exit_mode, 'open_fill': open_fill, 'st': 'pit',
                         'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                         'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                         'stock_pnl': round(tr['pnl'].sum(),0) if len(tr) else 0})
            print(f"{name}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% shp={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={tr['pnl'].sum():,.0f}")

    # ETF buy&hold
    ei = etf_idx.get(days[0])
    p0 = etf_px[ei]
    ei2 = etf_idx.get(days[-1])
    p1 = etf_px[ei2]
    etf_bh = p1 / p0 - 1
    print(f"\nETF 513500 buy&hold 2020-01-02~2026-08-25: {etf_bh*100:.2f}%")
    rows.append({'version': 'ETF_BUYHOLD', 'total': round(etf_bh*100,2), 'note': f'close {p0:.3f}->{p1:.3f}'})

    pd.DataFrame(rows).to_csv(f'{OUT}/strict_v2_matrix.csv', index=False)
    with open(f'{OUT}/strict_v2_summary.json', 'w') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    print('\nSTRICT_V2 done.')

if __name__ == '__main__':
    main()

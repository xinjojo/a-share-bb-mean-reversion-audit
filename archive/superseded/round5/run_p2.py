"""P2: ETF 会计与滑点修复
- ensure_cash 卖 ETF 按 etf_px*(1-slip) 进入现金 (v5 已修复)
- ETF 买入按 etf_px*(1+slip) 扣现金 (v5 已修复)
- 期末清仓费用同步到 equity 最后一行 (v5 已修复)
- 估值口径: NAV(unit_nav) vs close(场内价)
- 滑点敏感性: 0/10/20/50 bp (股票+ETF两腿都计入)
K=3, exit current (冻结退出逻辑), 隔离 ETF 会计影响。
"""
import sys, time, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    rows = []
    for mark in ('close', 'nav'):
        for bp in (0, 10, 20, 50):
            eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                       exit_bb_mode='current', buy_mode='close', etf_mark=mark,
                                       slippage_bp=bp, stamp_tax_mode='flat')
            s = full_stats(eq, tr)
            sp = tr['pnl'].sum()
            rows.append({'etf_mark': mark, 'slippage_bp': bp, 'total': round(s['total'],2),
                         'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2), 'sharpe': round(s['sharpe'],3),
                         'trades': s['n'], 'wr': round(s['wr'],2), 'stock_pnl': round(sp,0)})
            print(f"etf_mark={mark} slip={bp}bp: total={s['total']:.2f}% ann={s['ann']:.2f}% "
                  f"mdd={s['mdd']:.2f}% sharpe={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={sp:,.0f}")
    dfr = pd.DataFrame(rows)
    dfr.to_csv(f'{OUT}/p2_etf_slip_matrix.csv', index=False)
    print('\nP2 done. 说明: 原版354.9%使用NAV(unit_nav)估值ETF, close交易, 期末未同步清仓(混合口径,低估)。')

if __name__ == '__main__':
    main()

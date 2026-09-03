"""P3: K=3 max_levels=4 vs 5 + 第5层边际贡献
- max_levels=4 vs 5 完整组合对比 (K=3, ETF full, 其他冻结)
- 第5层边际: 对真实触发第5层的交易, 构造"有第5层" vs "第5层不买"(skip_level5) 相同路径
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    # max_levels 对比
    rows = []
    for ml in (4, 5):
        eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                   max_levels=ml, exit_bb_mode='current', buy_mode='close',
                                   etf_mark='close', stamp_tax_mode='flat')
        s = full_stats(eq, tr)
        sp = tr['pnl'].sum()
        n5 = (tr['levels_used'] >= 5).sum() if len(tr) else 0
        rows.append({'max_levels': ml, 'total': round(s['total'],2), 'ann': round(s['ann'],2),
                     'mdd': round(s['mdd'],2), 'sharpe': round(s['sharpe'],3), 'trades': s['n'],
                     'wr': round(s['wr'],2), 'stock_pnl': round(sp,0), 'n_level5_trades': int(n5)})
        print(f"max_levels={ml}: total={s['total']:.2f}% ann={s['ann']:.2f}% mdd={s['mdd']:.2f}% "
              f"sharpe={s['sharpe']:.3f} n={s['n']} wr={s['wr']:.1f}% stock_pnl={sp:,.0f} n_5l={n5}")

    # 第5层边际贡献: 对比 max_levels=5 vs max_levels=5+skip_level5
    eq5, tr5 = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                 max_levels=5, exit_bb_mode='current', buy_mode='close',
                                 etf_mark='close', stamp_tax_mode='flat')
    eqs, trs = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                 max_levels=5, exit_bb_mode='current', buy_mode='close',
                                 etf_mark='close', stamp_tax_mode='flat', skip_level5=True)
    s5 = full_stats(eq5, tr5); ss = full_stats(eqs, trs)
    sp5 = tr5['pnl'].sum(); sps = trs['pnl'].sum()
    # 触发第5层的交易数
    n_l5 = (tr5['levels_used'] >= 5).sum()
    # 第5层边际 PnL = 有5层 - 无5层（整体）
    print(f"\n[第5层边际]")
    print(f"有5层: total={s5['total']:.2f}% stock_pnl={sp5:,.0f} n={s5['n']}")
    print(f"无5层(skip): total={ss['total']:.2f}% stock_pnl={sps:,.0f} n={ss['n']}")
    print(f"触发第5层交易数: {n_l5}")
    print(f"第5层边际股票PnL(有-无): {sp5-sps:,.0f} 元")
    print(f"第5层边际组合收益: {s5['total']-ss['total']:.2f}pp")
    print(f"第5层对MaxDD影响: {ss['mdd']-s5['mdd']:.2f}pp")
    res = {'max_levels_4': rows[0], 'max_levels_5': rows[1],
           'l5_marginal': {'n_l5_trades': int(n_l5), 'stock_pnl_diff': round(sp5-sps,0),
                           'total_pp_diff': round(s5['total']-ss['total'],2),
                           'mdd_pp_diff': round(ss['mdd']-s5['mdd'],2)}}
    with open(f'{OUT}/p3_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print('\nP3 Summary:', json.dumps(res, ensure_ascii=False))

if __name__ == '__main__':
    main()

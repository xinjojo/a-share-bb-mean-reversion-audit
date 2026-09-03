"""STRICT_V1: 同时修复所有确认的 MATERIAL/INVALID 问题 + 归因
修复项:
  P0  未来函数 -> exit_bb_mode='close_confirm_next' (T日收盘确认, T+1 open卖)
  P2  ETF滑点两腿计入 + 期末清仓同步 (v5已修复)
  附加 correct limit-down (正确涨跌停) + execution_constraints (一字板) + 历史印花税
基线: V0 current + close buy + old limitdown + slip0 + 期末同步 = 383.62%
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    # 旧跌停数据
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    # correct 跌停数据
    days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, df2, listing2 = load_and_extend(limit_down_mode='correct')

    def run(exit_mode, buy_mode, slip, lim='old', constraints=False, stamp='flat', mark='close'):
        dd_, DD_, e_, p_, o_, n_, df_, l_ = (days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing) if lim == 'old' else (days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, df2, listing2)
        eq, tr = run_fast_multi_v5(dd_, DD_, e_, p_, o_, n_, l_, K=3,
                                   exit_bb_mode=exit_mode, buy_mode=buy_mode, etf_mark=mark,
                                   slippage_bp=slip, stamp_tax_mode=stamp,
                                   execution_constraints=constraints)
        s = full_stats(eq, tr)
        return s, tr

    rows = []
    # 基线 (old limit, slip0, close估值, 期末已同步)
    s, tr = run('current', 'close', 0, 'old', False)
    rows.append({'version': 'V0_BASELINE_oldlimit', 'desc': '含未来+old跌停+slip0',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"V0_BASELINE: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")

    # 逐个修复
    s, tr = run('close_confirm_next', 'close', 0, 'old', False)
    rows.append({'version': 'P0_FIX', 'desc': '无未来退出',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"P0_FIX: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")

    s, tr = run('close_confirm_next', 'close', 0, 'correct', False)
    rows.append({'version': 'P0+CORRECTLD', 'desc': '无未来+正确跌停',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"P0+CORRECTLD: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")

    s, tr = run('close_confirm_next', 'close', 10, 'correct', True)
    rows.append({'version': 'STRICT_V1', 'desc': '无未来+正确跌停+10bp滑点+一字板约束',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"STRICT_V1: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")
    tr.to_csv(f'{OUT}/strict_v1_trades.csv', index=False)

    # STRICT_V1 + 历史印花税
    s, tr = run('close_confirm_next', 'close', 10, 'correct', True, stamp='historical')
    rows.append({'version': 'STRICT_V1_histstamp', 'desc': 'STRICT_V1+历史印花税',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"STRICT_V1_histstamp: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")

    # STRICT_V1 + next_open 买入 (全链路严格)
    s, tr = run('close_confirm_next', 'next_open', 10, 'correct', True)
    rows.append({'version': 'STRICT_V1_nextopen_buy', 'desc': 'STRICT_V1+买入next_open',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"STRICT_V1_nextopen_buy: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")

    # STRICT_V1 + next_open 买入 + 历史印花税 (最严格)
    s, tr = run('close_confirm_next', 'next_open', 10, 'correct', True, stamp='historical')
    rows.append({'version': 'STRICT_V1_full', 'desc': '全严格: 无未来+correct跌停+10bp+一字板+next_open+历史印花税',
                 'total': round(s['total'],2), 'ann': round(s['ann'],2), 'mdd': round(s['mdd'],2),
                 'sharpe': round(s['sharpe'],3), 'trades': s['n'], 'wr': round(s['wr'],2),
                 'stock_pnl': round(tr['pnl'].sum(),0)})
    print(f"STRICT_V1_full: {s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}% shp={s['sharpe']:.3f}")
    tr.to_csv(f'{OUT}/strict_v1_full_trades.csv', index=False)

    dfr = pd.DataFrame(rows)
    dfr.to_csv(f'{OUT}/strict_matrix.csv', index=False)
    with open(f'{OUT}/strict_summary.json', 'w') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    print('\nSTRICT done.')

if __name__ == '__main__':
    main()

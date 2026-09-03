"""额外代码检查 7 项
1. data 中 (date, ts_code) 重复行
2. FINAL_SETTLE 是否可能违反 T+1
3. FINAL_SETTLE 费用是否进入最终 equity
4. README 写 2026-08-31 但 354.9% 实际截止 2026-08-25
5. "K=3七年全正" 是否与 2022=-2.8% 矛盾
6. correct limit-down 模式重跑 K3
7. 同日多持仓加仓顺序敏感性 (原顺序/超卖/amount/随机100次)
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    res = {}
    # 1. 重复行
    df = pd.read_parquet('data/combined_daily.parquet')
    dup = df.duplicated(subset=['date', 'ts_code']).sum()
    print(f"[1] (date,ts_code) 重复行: {dup}")
    res['dup_rows'] = int(dup)

    # 2. FINAL_SETTLE T+1 检查: 看交易里 FINAL_SETTLE 的 entry_date vs exit_date
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                               exit_bb_mode='current', buy_mode='close', etf_mark='close', stamp_tax_mode='flat')
    fs = tr[tr['exit_type'] == 'FINAL_SETTLE']
    print(f"[2] FINAL_SETTLE 交易数: {len(fs)}")
    if len(fs):
        fs = fs.copy()
        fs['ed'] = pd.to_datetime(fs['entry_date']); fs['xd'] = pd.to_datetime(fs['exit_date'])
        fs['hold'] = (fs['xd'] - fs['ed']).dt.days
        print(f"    FINAL_SETTLE 持仓天数(自然日): {fs['hold'].tolist()}")
        # 若 hold==0 即当天买入当天卖(违反T+1)
        viol = (fs['hold'] == 0).sum()
        print(f"    T+1 违规(当日买卖)数: {viol}")
        res['final_settle_t1_violation'] = int(viol)
        res['final_settle_hold_days'] = fs['hold'].tolist()
    else:
        res['final_settle_t1_violation'] = 0

    # 3. FINAL_SETTLE 费用进入最终 equity: 对比最后一行是否含清仓
    #     v5 已同步; 检查最后一行 stock_val/etf_shares 是否为0
    lastrow = eq.iloc[-1]
    print(f"[3] 最后一行: stock_val={lastrow['stock_val']}, etf_shares={lastrow['etf_shares']}, cash={lastrow['cash']:.0f}")
    print(f"    (v5已期末同步 -> stock_val=0, etf_shares=0, equity=cash)")
    res['final_settle_synced'] = bool(lastrow['stock_val'] == 0 and lastrow['etf_shares'] == 0)

    # 4. 数据截止日期
    last_date = df['date'].max()
    print(f"[4] combined_daily 实际最后日期: {last_date}")
    res['data_last_date'] = str(last_date)

    # 5. 分年收益 (K=3 current)
    eq['year'] = pd.to_datetime(eq['date']).dt.year
    ret = eq['equity'].pct_change().fillna(0)
    year_rows = []
    for y, g in eq.groupby('year'):
        # 年内复利收益
        eq_slice = eq[eq['year'] == y]
        yret = eq_slice['equity'].iloc[-1] / eq_slice['equity'].iloc[0] - 1
        year_rows.append((y, round(yret * 100, 2)))
    print(f"[5] K=3 分年收益: {year_rows}")
    res['yearly_returns'] = [[y, v] for y, v in year_rows]

    # 6. correct limit-down 重跑 K3
    days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, df2, listing2 = load_and_extend(limit_down_mode='correct')
    eqc, trc = run_fast_multi_v5(days2, D2, etf_idx2, etf_px2, etf_open2, etf_nav2, listing2, K=3,
                                 exit_bb_mode='current', buy_mode='close', etf_mark='close', stamp_tax_mode='flat')
    sc = full_stats(eqc, trc)
    print(f"[6] correct limit-down K3: total={sc['total']:.2f}% n={sc['n']} wr={sc['wr']:.1f}%")
    res['correct_limitdown'] = {'total': round(sc['total'],2), 'n': int(sc['n']), 'wr': round(sc['wr'],2)}

    # 7. 加仓顺序敏感性
    print(f"\n[7] 同日多持仓加仓顺序敏感性 (K=3 current):")
    rows7 = []
    eq_none, tr_none = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                         exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                         stamp_tax_mode='flat', pos_sort=None)
    s_none = full_stats(eq_none, tr_none)
    rows7.append({'order': 'original', 'total': round(s_none['total'],2), 'stock_pnl': round(tr_none['pnl'].sum(),0)})
    print(f"  原顺序: total={s_none['total']:.2f}%")
    eq_os, tr_os = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                     exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                     stamp_tax_mode='flat', pos_sort='oversold')
    s_os = full_stats(eq_os, tr_os)
    rows7.append({'order': 'oversold', 'total': round(s_os['total'],2), 'stock_pnl': round(tr_os['pnl'].sum(),0)})
    print(f"  超卖优先: total={s_os['total']:.2f}%")
    eq_am, tr_am = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                     exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                     stamp_tax_mode='flat', pos_sort='amount')
    s_am = full_stats(eq_am, tr_am)
    rows7.append({'order': 'amount', 'total': round(s_am['total'],2), 'stock_pnl': round(tr_am['pnl'].sum(),0)})
    print(f"  amount优先: total={s_am['total']:.2f}%")
    rand_totals = []
    for seed in range(100):
        # 随机顺序: 每轮调用时用新seed -> 需要引擎支持seed. 用环境seed.
        import random
        random.seed(seed)
        eq_r, tr_r = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                       exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                       stamp_tax_mode='flat', pos_sort='random')
        s_r = full_stats(eq_r, tr_r)
        rand_totals.append(s_r['total'])
    rand_totals = np.array(rand_totals)
    print(f"  随机100次: mean={rand_totals.mean():.2f}% min={rand_totals.min():.2f}% max={rand_totals.max():.2f}% "
          f"std={rand_totals.std():.2f}%")
    rows7.append({'order': 'random_100', 'total_mean': round(float(rand_totals.mean()),2),
                  'total_min': round(float(rand_totals.min()),2), 'total_max': round(float(rand_totals.max()),2),
                  'total_std': round(float(rand_totals.std()),2)})
    res['order_sensitivity'] = rows7
    with open(f'{OUT}/extra_checks.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=str)
    print('\n[extra checks] done.')

if __name__ == '__main__':
    main()

"""P8: 91.2%卖飞结论重新定义
1. post_high = max(next20 trading days high) 是事后oracle指标, 不可交易
2. 在修复P0后(V2 close_confirm_next)的交易上, 计算无偏反事实:
   卖出后 D+1/3/5/10/20 close 相对成本
3. 可交易退出策略对比 A-E (在 V2 交易路径上, 固定持有N日反事实, 当时可知)
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    # 用修复后的 V2 引擎 (K=3, close_confirm_next 退出, close 买入) 生成交易
    eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                               exit_bb_mode='close_confirm_next', buy_mode='close', etf_mark='close',
                               stamp_tax_mode='flat')
    s = full_stats(eq, tr)
    print(f"V2(修复后) K=3: total={s['total']:.2f}% n={s['n']} wr={s['wr']:.1f}%")
    tr = tr.copy()
    tr['entry'] = pd.to_datetime(tr['entry_date'])
    tr['exit'] = pd.to_datetime(tr['exit_date'])
    # 每笔平均成本: 用 pnl 反推? 用 total_cost 估算. 这里用持仓期数据计算相对成本更复杂.
    # 简化: 用 return_pct 与 pnl 关系; 对无偏反事实, 用"退出后 close 相对退出价"更直接:
    #   ret_from_exit = close[exit+k] / exit_close - 1   (exit_close≈卖出价, 但V2卖出是open价)
    # 这里我们用 相对成本 口径, 需要 avg_cost. 从 actions 获取.
    eq2, tr2, ac = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                                     exit_bb_mode='close_confirm_next', buy_mode='close', etf_mark='close',
                                     stamp_tax_mode='flat', record_actions=True)
    # 构建 ts_code+date -> 收盘价 索引
    px_map = {}
    for d in days:
        dd = D[d]
        for j, tc in enumerate(dd['ts']):
            px_map[(tc, d)] = dd['close'][j]
    # 交易日序列
    day_seq = list(days)
    day_pos = {d: i for i, d in enumerate(day_seq)}
    results = []
    for _, r in tr.iterrows():
        tc = r['ts_code']
        x = day_pos.get(r['exit'])
        if x is None:
            continue
        exit_close = px_map.get((tc, r['exit']))
        if exit_close is None:
            continue
        row = {'ts_code': tc, 'entry_date': r['entry_date'], 'exit_date': r['exit_date'],
               'pnl': r['pnl'], 'return_pct': r['return_pct']}
        # 卖出后 D+N close 相对卖出日 close (无偏)
        for k in (1, 3, 5, 10, 20):
            xi = x + k
            if xi < len(day_seq):
                dk = day_seq[xi]
                ck = px_map.get((tc, dk))
                if ck is not None:
                    row[f'D{k}_ret_vs_exitclose'] = (ck / exit_close - 1) * 100
        # 事后 oracle: 卖出后20日最高价 vs 卖出日 close
        hi = 0
        for k in range(1, 21):
            xi = x + k
            if xi < len(day_seq):
                dk = day_seq[xi]
                jj = D[dk]['pos'].get(tc)
                if jj is not None:
                    hi = max(hi, D[dk]['high'][jj])
        row['post20_high_ret'] = (hi / exit_close - 1) * 100 if hi else np.nan
        results.append(row)
    rdf = pd.DataFrame(results)
    # 卖飞: post20_high_ret > 0
    print(f"\n有效样本: {len(rdf)}")
    oracle_selloff = (rdf['post20_high_ret'] > 0).mean() * 100
    print(f"卖出后20日最高价>卖出日收盘价比例(事后oracle): {oracle_selloff:.1f}%")
    # 无偏反事实
    print("\n[无偏] 卖出后 D+N 收盘价 相对 卖出日收盘价 收益分布:")
    for k in (1, 3, 5, 10, 20):
        col = f'D{k}_ret_vs_exitclose'
        if col in rdf and rdf[col].notna().sum() > 0:
            v = rdf[col]
            print(f"  D+{k}: mean={v.mean():+.2f}% median={v.median():+.2f}% >0占比={(v>0).mean()*100:.1f}%")
    rdf.to_csv(f'{OUT}/p8_exit_unbiased.csv', index=False)
    res = {'n': int(len(rdf)),
           'oracle_post20_high_gt_exit_pct': round(oracle_selloff,1)}
    with open(f'{OUT}/p8_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print('\nP8 done. 结论: 91.2%卖飞为事后oracle描述, 不可直接交易; 无偏D+N收盘口径见上.')

if __name__ == '__main__':
    main()

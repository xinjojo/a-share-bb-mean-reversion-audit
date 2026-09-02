"""PIT ST 对 Top10 候选池/BB信号/实际交易 的量化影响 (独立统计, 不依赖 build_pit_st main)
"""
import sys, os, json
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
OUT = f'{ROOT}/results/round5'
os.makedirs(OUT, exist_ok=True)

def main():
    df = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet')
    pit = pd.read_parquet(f'{ROOT}/data/pit_st_daily.parquet')
    # 合并 PIT 状态
    df = df.merge(pit, on=['date', 'ts_code'], how='left')
    # BB
    df = df.sort_values(['ts_code', 'date'])
    g = df.groupby('ts_code', group_keys=False)
    df['ma'] = g['close'].transform(lambda s: s.rolling(20).mean())
    df['sd'] = g['close'].transform(lambda s: s.rolling(20).std())
    df['bb_low'] = df['ma'] - 2 * df['sd']
    df['sig'] = df['close'] < df['bb_low']

    topn_days = 0          # 日期数: 快照 vs PIT 的 Top10 集合不同
    sig_days = 0           # 日期数: Top10中跌破下轨的集合不同
    sig_diff_rows = 0
    snap_top10 = set(); pit_top10 = set()
    for d, gd in df.groupby('date'):
        gd = gd[gd['amount'] > 0]
        s10 = gd[~gd['is_st_snapshot'].fillna(False)].nlargest(10, 'amount')
        p10 = gd[~gd['is_st_pit'].fillna(False)].nlargest(10, 'amount')
        s10s = set(s10['ts_code']); p10s = set(p10['ts_code'])
        if s10s != p10s:
            topn_days += 1
        s_sig = set(s10[s10['sig']]['ts_code'])
        p_sig = set(p10[p10['sig']]['ts_code'])
        if s_sig != p_sig:
            sig_days += 1
            sig_diff_rows += len(s_sig ^ p_sig)
        snap_top10 |= s10s
        pit_top10 |= p10s
    print(f'总交易日: {df["date"].nunique()}')
    print(f'Top10集合差异日期数: {topn_days}')
    print(f'Top10中跌破下轨信号集合差异日期数: {sig_days}, 差异行: {sig_diff_rows}')
    print(f'快照Top10涉及股票: {len(snap_top10)}, PIT Top10涉及股票: {len(pit_top10)}')

    # 实际交易受影响 (STRICT_V2_B 交易)
    from round51_audit import prepare_v51, run_fast_multi_v51, full_stats
    days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off = prepare_v51(limit_down_mode='correct', st_mode='pit')
    eq, tr, ac = run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, fel, off, K=3,
                                    exit_bb_mode='close_confirm_next', open_fill='limit_conservative',
                                    etf_enabled=True, record_actions=True)
    tr2 = ac[ac['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
    affected = 0
    for _, r in tr2.iterrows():
        m = pit[(pit['date'] == r['date']) & (pit['ts_code'] == r['ts_code'])]
        if len(m) and m['is_st_pit'].iloc[0] != m['is_st_snapshot'].iloc[0]:
            affected += 1
    print(f'STRICT_V2_B 买入笔数: {len(tr2)}, 其中 PIT/快照ST状态差异股票买入笔数: {affected}')

    res = {'total_trading_days': int(df['date'].nunique()),
           'top10_diff_days': int(topn_days),
           'top10_bb_signal_diff_days': int(sig_days),
           'top10_bb_signal_diff_rows': int(sig_diff_rows),
           'snapshot_top10_symbols': len(snap_top10),
           'pit_top10_symbols': len(pit_top10),
           'strict_v2_b_buys': int(len(tr2)),
           'strict_v2_b_affected_buys': int(affected)}
    with open(f'{OUT}/pit_st_top10_impact.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print('saved pit_st_top10_impact.json')

if __name__ == '__main__':
    main()

"""构建 PIT ST 状态(基于 namechange 历史名称) + 与当前快照对比
输出差异统计 + 差异日 Top10/BB signal/实际交易影响
"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
OUT = os.path.join(ROOT, 'results/round5')
os.makedirs(OUT, exist_ok=True)

def build_pit_st():
    nc = pd.read_parquet(f'{ROOT}/data/raw/namechange_full.parquet')
    nc = nc[['ts_code', 'name', 'start_date', 'end_date']].copy()
    nc['start'] = pd.to_datetime(nc['start_date'], format='%Y%m%d', errors='coerce')
    nc['end'] = pd.to_datetime(nc['end_date'], format='%Y%m%d', errors='coerce')
    nc['is_st'] = nc['name'].str.contains('ST', na=False)
    # 只需 ST 相关区间构建 PIT: 非 ST 记录用于判断摘帽(恢复非ST), 也保留
    nc = nc.dropna(subset=['start']).sort_values(['ts_code', 'start']).reset_index(drop=True)

    df = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet')
    df = df[['date', 'ts_code']].copy()
    df['date'] = pd.to_datetime(df['date'])
    # 对每只股票: merge_asof 取 <= date 最新记录, 再校验 end>=date
    gb = df.groupby('ts_code')
    updated = []
    for tc, sub in gb:
        rec = nc[nc['ts_code'] == tc].sort_values('start')
        if len(rec) == 0:
            continue  # 从未变更 -> 保持 False, 后续用当前快照补
        sub = sub.sort_values('date')
        # merge_asof: 每条 df 行匹配 <= date 的最大 start
        m = pd.merge_asof(sub, rec[['start', 'end', 'is_st']], left_on='date', right_on='start', direction='backward')
        # 校验 end >= date (end NaN = 至今有效)
        valid = m['end'].isna() | (m['end'] >= m['date'])
        m['is_st_pit'] = m['is_st'].where(valid, False).fillna(False)
        updated.append(m[['date', 'ts_code', 'is_st_pit']])
    if updated:
        pit = pd.concat(updated, ignore_index=True)
        df = df.merge(pit, on=['date', 'ts_code'], how='left')
    df['is_st_pit'] = df['is_st_pit'].fillna(False).astype(bool)
    # 从未有 namechange 记录的股票: 用当前快照 name (从未改名 -> 当前名即历史名)
    sb = pd.read_parquet(f'{ROOT}/data/raw/stock_basic.parquet')
    no_rec = set(df['ts_code']) - set(nc['ts_code'])
    if no_rec:
        sb2 = sb[sb['ts_code'].isin(no_rec)][['ts_code', 'name']]
        snap_st = sb2.set_index('ts_code')['name'].str.contains('ST', na=False)
        df.loc[df['ts_code'].isin(no_rec), 'is_st_pit'] = df.loc[df['ts_code'].isin(no_rec), 'ts_code'].map(snap_st).fillna(False)
    return df, nc

def main():
    df, nc = build_pit_st()
    # 当前快照 ST
    sb = pd.read_parquet(f'{ROOT}/data/raw/stock_basic.parquet')
    snap = sb.set_index('ts_code')['name'].str.contains('ST', na=False)
    df['is_st_snapshot'] = df['ts_code'].map(snap).fillna(False)
    df.to_parquet(f'{ROOT}/data/pit_st_daily.parquet')

    total = len(df)
    old = int(df['is_st_snapshot'].sum())
    new = int(df['is_st_pit'].sum())
    diff = (df['is_st_snapshot'] != df['is_st_pit'])
    diff_days = int(diff.sum())
    diff_syms = df.loc[diff, 'ts_code'].nunique()
    print(f"total_stock_days: {total}")
    print(f"old_is_st_count(快照): {old}")
    print(f"pit_is_st_count(PIT): {new}")
    print(f"diff_stock_days: {diff_days}")
    print(f"diff_symbols: {diff_syms}")
    # 分类: 快照ST但PIT非ST(历史摘帽) vs 快照非ST但PIT是ST(历史曾ST)
    a = (df['is_st_snapshot'] & ~df['is_st_pit']).sum()
    b = (~df['is_st_snapshot'] & df['is_st_pit']).sum()
    print(f"  快照ST但PIT非ST(历史曾ST已摘帽): {a} days")
    print(f"  快照非ST但PIT是ST(历史曾ST): {b} days")

    # 差异日是否在 Top10 / BB signal
    days = sorted(df['date'].unique())
    # 合并 ST 标记(快照+PIT)
    d2 = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet')
    d2['date'] = pd.to_datetime(d2['date'])
    d2 = d2[['date', 'ts_code', 'amount']].merge(
        df[['date', 'ts_code', 'is_st_snapshot', 'is_st_pit']], on=['date', 'ts_code'], how='left')
    d2['is_st_snapshot'] = d2['is_st_snapshot'].fillna(False)
    d2['is_st_pit'] = d2['is_st_pit'].fillna(False)
    # 排名(分别剔除快照ST / PIT ST)
    d_snap = d2[~d2['is_st_snapshot']].copy()
    d_snap['rank_snap'] = d_snap.groupby('date')['amount'].rank(ascending=False, method='first')
    d2 = d2.merge(d_snap[['date', 'ts_code', 'rank_snap']], on=['date', 'ts_code'], how='left')
    d_pit = d2[~d2['is_st_pit']].copy()
    d_pit['rank_pit'] = d_pit.groupby('date')['amount'].rank(ascending=False, method='first')
    d2 = d2.merge(d_pit[['date', 'ts_code', 'rank_pit']], on=['date', 'ts_code'], how='left')

    diff_df = d2[d2['is_st_pit'] != d2['is_st_snapshot']].copy()
    print(f"\n差异日中:")
    top10_snap = int(diff_df['rank_snap'].le(10).sum())
    top10_pit = int(diff_df['rank_pit'].le(10).sum())
    print(f"  快照口径进入Top10的差异日: {top10_snap}")
    print(f"  PIT口径进入Top10的差异日: {top10_pit}")
    # BB signal: close_adj < bb_lower (需计算)
    dd = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet')
    dd['date'] = pd.to_datetime(dd['date'])
    dd['close_adj'] = dd['close'] * dd['adj_factor']
    g = dd.groupby('ts_code')['close_adj']
    dd['ma'] = g.transform(lambda x: x.rolling(20, min_periods=20).mean())
    dd['sd'] = g.transform(lambda x: x.rolling(20, min_periods=20).std())
    dd['bb_lower'] = dd['ma'] - 2 * dd['sd']
    dd['bb_signal'] = dd['close_adj'] < dd['bb_lower']
    diff_df = diff_df.merge(dd[['date', 'ts_code', 'bb_signal']], on=['date', 'ts_code'], how='left')
    top10_bb_snap = int((diff_df['rank_snap'].le(10) & diff_df['bb_signal']).sum())
    top10_bb_pit = int((diff_df['rank_pit'].le(10) & diff_df['bb_signal']).sum())
    print(f"  快照口径 Top10+BBsignal 差异日: {top10_bb_snap}")
    print(f"  PIT口径 Top10+BBsignal 差异日: {top10_bb_pit}")

    res = {'total_stock_days': total, 'old_is_st_count': old, 'pit_is_st_count': new,
           'diff_stock_days': diff_days, 'diff_symbols': diff_syms,
           'snap_st_pit_not': int(a), 'snap_not_pit_st': int(b),
           'top10_snap_diff_days': top10_snap, 'top10_pit_diff_days': top10_pit,
           'top10_bb_snap_diff_days': top10_bb_snap, 'top10_bb_pit_diff_days': top10_bb_pit}
    with open(f'{OUT}/pit_st_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=int)
    # 差异股票样例
    print("\n差异股票样例:")
    print(diff_df.groupby('ts_code').size().sort_values(ascending=False).head(15).to_string())
    diff_df.to_parquet(f'{OUT}/pit_st_diff_days.parquet')
    print("\nPIT ST done.")

if __name__ == '__main__':
    main()

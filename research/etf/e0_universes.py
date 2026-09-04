#!/usr/bin/env python3
"""E0 STEP 5-6: Universe A（Current Representative）+ Universe B（PIT Representative）
输出:
  results/etf/e0_current_representatives.csv
  results/etf/e0_pit_universe_summary.csv
选择规则（预注册两条，不选优胜，E1 前冻结）:
  B1: 每个交易日 t，同指数内选择 PIT AUM（fd_share(t)*close(t)）最大且已上市的 ETF（2018-06 起可用）
  B2: 每个交易日 t，同指数内选择 trailing ADV60(t-1) 最大且已上市的 ETF（上市满 60 日后可用）
  PIT 约束: list_date<=t 且 (delist_date 为空或 delist_date>t)；同一指数多 ETF 去重
"""
import os
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
print('master rows:', len(master))

# 指数键：优先 index_code（唯一），否则 bench_idx_name
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)

# ============ Universe A: 当前代表 ============
# 每个指数（bench_idx_name 键）当前规模最大 ETF（L 状态优先，fund_size 最大）
cur = master[master['status'] == 'L'].copy()
cur['fund_size'] = pd.to_numeric(cur['fund_size'], errors='coerce')
def pick_current(g):
    g2 = g.dropna(subset=['fund_size'])
    if len(g2) == 0:
        # 无 AUM 的用 adv60
        g3 = g.dropna(subset=['adv60'])
        if len(g3) == 0:
            return g.iloc[0] if len(g) else None
        return g3.sort_values('adv60', ascending=False).iloc[0]
    return g2.sort_values('fund_size', ascending=False).iloc[0]

ua = cur.groupby('index_key', dropna=False).apply(pick_current, include_groups=False).reset_index()

ua = ua.drop_duplicates(subset=['index_key'])
ua.to_csv(os.path.join(OUT, 'e0_current_representatives.csv'), index=False)
print('Universe A 当前代表（指数键）:', len(ua))
print('  CSI 核心指数（代表，is_csi & eligible）:', ((ua['is_csi_publisher']) & (ua['eligible'])).sum())

# ============ Universe B: PIT Representative ============
# 只对 eligible 的 ETF 构建
elig = master[master['eligible']].copy()
elig['list_date_dt'] = pd.to_datetime(elig['list_date'], errors='coerce')
elig['delist_date_dt'] = pd.to_datetime(elig['delist_date'], errors='coerce')

# 交易日历（ETF 交易日 = 全市场交易日）
tc = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'trade_cal_full.parquet'))
cal = pd.to_datetime(tc['date']).sort_values()
cal = cal[(cal >= '2004-01-01') & (cal <= '2026-09-03')]
print('交易日历范围:', cal.min(), '->', cal.max(), 'n=', len(cal))

# 收集每只 eligible ETF 的 daily（close/amount）并计算 ADV60 与 PIT AUM
# 用月度快照 + 年末快照计算 PIT 结构（全交易日逐日计算内存过大，月度代表足以反映 PIT 结构变化；
# 但 signal-density 将用全交易日）
snapshot_dates = cal[cal.isin(pd.date_range('2004-01-01', '2026-09-03', freq='ME').normalize())]
snap = sorted(set(cal[cal.dt.is_month_end]))  # 月末
print('月度快照数:', len(snap))

# 对每只 ETF 读 daily 并算 rolling ADV60（用全历史交易日对齐）
# 为控制内存，只对 eligible ETF 逐只处理，汇总为 index-day 选择
records = []
idx_meta = {}
for i, r in elig.iterrows():
    tc_ = r['etf_code']
    p = os.path.join(RAWDIR, 'fund_daily', tc_.replace('.', '_') + '.parquet')
    if not os.path.exists(p):
        continue
    fd = pd.read_parquet(p)
    if len(fd) == 0:
        continue
    fd['trade_date'] = pd.to_datetime(fd['trade_date'])
    fd = fd.sort_values('trade_date')
    amt = pd.to_numeric(fd['amount'], errors='coerce')
    close = pd.to_numeric(fd['close'], errors='coerce')
    fd['amt'] = amt
    fd['close'] = close
    # ADV60 at t = 过去60日 mean(amount)，t-1 即 shift(1)
    fd['adv60'] = fd['amt'].rolling(60, min_periods=20).mean().shift(1)
    fd['close_t'] = close
    idx_key = r['index_key']
    if idx_key not in idx_meta:
        idx_meta[idx_key] = {'etfs': set(), 'publisher': r['index_publisher'], 'is_csi': r['is_csi_publisher']}
    idx_meta[idx_key]['etfs'].add(tc_)
    # 份额（PIT AUM）
    sp = os.path.join(RAWDIR, 'fund_share', tc_.replace('.', '_') + '.parquet')
    share = None
    if os.path.exists(sp):
        fs = pd.read_parquet(sp)
        if len(fs):
            fs['trade_date'] = pd.to_datetime(fs['trade_date'])
            fs = fs.sort_values('trade_date').set_index('trade_date')['fd_share']
            share = fs
    records.append((idx_key, tc_, r['list_date_dt'], r['delist_date_dt'], fd, share))

# 月末快照选择
rows = []
for d in snap:
    # 当日可用 ETF：已上市且未清盘，且有当日数据
    for idx_key, tc_, ld, dd_, fd, share in records:
        if ld is not None and pd.notna(ld) and ld > d:
            continue
        if dd_ is not None and pd.notna(dd_) and dd_ <= d:
            continue
        day = fd[fd['trade_date'] <= d]
        if len(day) == 0:
            continue
        last = day.iloc[-1]
        amt60 = last['adv60'] if pd.notna(last['adv60']) else np.nan
        close_t = last['close_t'] if pd.notna(last['close_t']) else np.nan
        if pd.isna(close_t):
            continue
        share_t = None
        if share is not None:
            sh = share[share.index <= d]
            if len(sh):
                share_t = float(sh.iloc[-1])
        aum_t = (share_t * 10000 * close_t) if share_t is not None else np.nan
        rows.append((d, idx_key, tc_, amt60, aum_t, close_t))

if rows:
    pit = pd.DataFrame(rows, columns=['date', 'index_key', 'etf_code', 'adv60_t', 'aum_t', 'close_t'])
    # B2: 每 index-day 选 adv60 最大
    b2 = pit.dropna(subset=['adv60_t']).sort_values('adv60_t', ascending=False).drop_duplicates(['date', 'index_key'])
    # B1: 每 index-day 选 aum 最大（2018 后有份额）
    b1 = pit.dropna(subset=['aum_t']).sort_values('aum_t', ascending=False).drop_duplicates(['date', 'index_key'])
    b2['rule'] = 'B2_ADV60'
    b1['rule'] = 'B1_AUM'
    pit_out = pd.concat([b1, b2], ignore_index=True)
    pit_out.to_csv(os.path.join(OUT, 'e0_pit_universe_selection_detail.csv'), index=False)

    # 汇总: 每个指数 PIT 可用区间
    summ = []
    for idx_key, g in pit.groupby('index_key'):
        first = g['date'].min()
        last = g['date'].max()
        n_months = len(g['date'].unique())
        n_etf = g['etf_code'].nunique()
        # B2 覆盖月数
        b2g = b2[b2['index_key'] == idx_key]
        n_b2 = len(b2g)
        meta = idx_meta.get(idx_key, {})
        summ.append(dict(index_key=idx_key, publisher=meta.get('publisher'),
                         is_csi=meta.get('is_csi'), n_etfs_ever=meta.get('n_etfs', n_etf),
                         pit_first_month=first, pit_last_month=last, n_months=n_months,
                         b2_months=n_b2, b1_months=len(b1[b1['index_key'] == idx_key])))
    su = pd.DataFrame(summ)
    su.to_csv(os.path.join(OUT, 'e0_pit_universe_summary.csv'), index=False)
    print('\nUniverse B PIT 汇总（指数键）:', len(su))
    print('  B1(AUM) 有覆盖的指数:', su['b1_months'].gt(0).sum())
    print('  B2(ADV60) 有覆盖的指数:', su['b2_months'].gt(0).sum())
    print('  PIT 最早月份:', su['pit_first_month'].min())
else:
    print('no pit rows')
    pd.DataFrame().to_csv(os.path.join(OUT, 'e0_pit_universe_summary.csv'), index=False)

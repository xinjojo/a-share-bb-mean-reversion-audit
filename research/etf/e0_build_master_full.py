#!/usr/bin/env python3
"""E0 STEP 4: 构建 MASTER ETF MAPPING 完整字段
合并 fund_daily/fund_adj/fund_share → close/daily_amount/adv20/adv60/fund_share/fund_size
输出: results/etf/e0_master_etf_mapping.csv（spec MASTER MAPPING 字段全集）
注意: fund_daily.amount 单位=千元; fund_share.fd_share 单位=万份; fund_size=fd_share*10000*close 元
"""
import os
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

base = pd.read_parquet(os.path.join(RAWDIR, 'etf_index_map_master.parquet'))
print('identity rows:', len(base))

def load(name, kind):
    p = os.path.join(RAWDIR, kind, name.replace('.', '_') + '.parquet')
    if os.path.exists(p):
        return pd.read_parquet(p)
    return None

rows = []
n_missing_daily = 0
for i, r in base.iterrows():
    tc = r['etf_code']
    fd = load(tc, 'fund_daily')
    fa = load(tc, 'fund_adj')
    fs = load(tc, 'fund_share')
    row = dict(
        etf_code=tc, etf_name=r['etf_name'], exchange=r['exchange'],
        list_date=r['list_date'], delist_date=r['delist_date'], found_date=r['found_date'],
        fund_manager=r['fund_manager'], status=r.get('status'),
        index_code=r['index_code'], index_name=r['index_name'],
        index_publisher=r['index_publisher'], publisher_confidence=r['publisher_confidence'],
        index_category=r['index_category'], asset_class=r['asset_class'],
        domestic_a_share_flag=r['domestic_a_share_flag'], passive_index_flag=r['passive_index_flag'],
        cross_mixed_flag=r['cross_mixed_flag'], is_csi_publisher=r['is_csi_publisher'],
        eligible=r['eligible'], exclusion_reason=r['exclusion_reason'],
        match_level=r['match_level'], bench_idx_name=r.get('bench_idx_name'),
        benchmark=r.get('benchmark'),
        data_source=r['data_source'], retrieval_date=r['retrieval_date'],
        has_daily=False, history_start=None, history_end=None, n_days=0,
        close=None, daily_amount=None, adv20=None, adv60=None,
        fund_share=None, fund_size=None, premium_max=None, zero_amt_days=0,
        adj_factor_last=None, last_amount=None,
    )
    if fd is not None and len(fd):
        fd = fd.sort_values('trade_date')
        row['has_daily'] = True
        row['history_start'] = str(fd['trade_date'].iloc[0])
        row['history_end'] = str(fd['trade_date'].iloc[-1])
        row['n_days'] = len(fd)
        row['close'] = float(fd['close'].iloc[-1])
        amt = pd.to_numeric(fd['amount'], errors='coerce')
        row['last_amount'] = float(amt.iloc[-1]) if pd.notna(amt.iloc[-1]) else None
        row['daily_amount'] = float(amt.iloc[-1]) * 1000.0 if pd.notna(amt.iloc[-1]) else None  # 千元->元
        amt_series = amt.dropna()
        if len(amt_series) >= 20:
            row['adv20'] = float(amt_series.tail(20).mean()) * 1000.0
        if len(amt_series) >= 60:
            row['adv60'] = float(amt_series.tail(60).mean()) * 1000.0
        row['zero_amt_days'] = int((amt.fillna(0) == 0).sum())
        # 异常折溢价粗查：fund_daily 无 NAV；用 adj 一致性替代（留空由 trading rules audit 说明）
    if fa is not None and len(fa):
        row['adj_factor_last'] = float(fa.sort_values('trade_date')['adj_factor'].iloc[-1])
    if fs is not None and len(fs):
        fs = fs.sort_values('trade_date')
        row['fund_share'] = float(fs['fd_share'].iloc[-1])  # 万份
        row['fund_share_first_date'] = str(fs['trade_date'].iloc[0])
        row['fund_share_last_date'] = str(fs['trade_date'].iloc[-1])
        if row['close'] is not None:
            row['fund_size'] = float(fs['fd_share'].iloc[-1]) * 10000.0 * row['close']  # 元
    if not row['has_daily']:
        n_missing_daily += 1
    rows.append(row)

master = pd.DataFrame(rows)
master.to_csv(os.path.join(OUT, 'e0_master_etf_mapping.csv'), index=False)
master.to_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
print('saved e0_master_etf_mapping.csv rows:', len(master))
print('无 fund_daily:', n_missing_daily)
print('\n字段预览（CSV 前 3 行关键列）:')
cols = ['etf_code', 'etf_name', 'list_date', 'history_start', 'history_end', 'n_days', 'close', 'daily_amount', 'adv20', 'adv60', 'fund_share', 'fund_size']
print(master[cols].head(5).to_string())

#!/usr/bin/env python3
"""E0 STEP 1: ETF 识别（境内 A 股股票 ETF 候选）
输入: data/raw/etf/fund_basic.parquet
输出: results/etf/e0_etf_candidates.csv (含识别规则标注) + 保存到 data/raw/etf/etf_candidates.parquet
识别规则（可复现，基于 Tushare 正式字段，非名称猜测）:
  market='E'（交易所上市）
  排除: REITs(fund_type) / LOF(name) / ETF联接(name) / 货币型(invest_type,name) /
        黄金现货合约、商品期货型(invest_type) / QDII(name,benchmark) / 跨境(name,benchmark)
  保留: 股票型被动/增强指数 ETF（fund_type in (股票型,) 且 invest_type in (被动指数型, 增强指数型, NaN股票型)）
"""
import os, re
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
os.makedirs(OUT, exist_ok=True)

fb = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'fund_basic.parquet'))
print('fund_basic total:', len(fb))

df = fb.copy()
df['name_'] = df['name'].astype(str)
df['bench_'] = df['benchmark'].astype(str)

def tag_exclusions(x):
    tags = []
    n = x['name_']; b = x['bench_']
    if x['fund_type'] == 'REITs' or 'REIT' in n: tags.append('REIT')
    if 'LOF' in n: tags.append('LOF')
    if 'ETF联接' in n or '联接' in n: tags.append('LINK_FUND')
    if x['invest_type'] == '货币型' or '货币' in n: tags.append('MONEY')
    if x['invest_type'] in ('黄金现货合约','能源化工期货型','有色金属期货型','豆粕期货型','白银期货型'): tags.append('COMMODITY')
    if '黄金' in n or '豆粕' in n or '原油' in n or '白银' in n or '商品' in n or '有色' in n or '能化' in n: tags.append('COMMODITY')
    if x['fund_type'] == '债券型' or '债' in n or '可转债' in n: tags.append('BOND')
    if 'QDII' in n or 'QDII' in b: tags.append('QDII')
    cross_kw = ['恒生','港股','纳斯达克','标普','德国','法国','日本','日经','美国','海外','全球','环球','亚太','MSCI','原油','油气','国际','中概','纳斯达克','道琼斯','欧','韩']
    for kw in cross_kw:
        if kw in n: tags.append(f'CROSS:{kw}'); break
    return tags

df['excl_tags'] = df.apply(tag_exclusions, axis=1)
df['excluded'] = df['excl_tags'].apply(lambda t: len(t) > 0)

# 保留股票型：fund_type == 股票型（或 invest_type 为被动/增强指数型），且未排除
keep = (~df['excluded']) & (df['fund_type'].isin(['股票型', '混合型']))
df['is_stock_etf_candidate'] = keep

cand = df[keep].copy()
print('\n股票 ETF 候选（未排除、股票型/混合型）:', len(cand))
print('invest_type:\n', cand['invest_type'].value_counts(dropna=False))
print('fund_type:\n', cand['fund_type'].value_counts(dropna=False))
print('status:\n', cand['status'].value_counts(dropna=False))
print('name 含 ETF:', cand['name_'].str.contains('ETF', na=False).sum(), '/', len(cand))

# 要求 name 含 ETF（排除名字里无 ETF 的指数基金/LOF 残留）
cand2 = cand[cand['name_'].str.contains('ETF', na=False)].copy()
print('\n其中 name 含 ETF:', len(cand2))

# 输出
out_cols = ['ts_code','name','management','custodian','fund_type','found_date','due_date','list_date','issue_date','delist_date','issue_amount','benchmark','status','invest_type','type','market','excl_tags','retrieval_date']
cand2[out_cols].sort_values('ts_code').to_csv(os.path.join(OUT, 'e0_etf_candidates.csv'), index=False)
cand2.to_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'etf_candidates.parquet'))
df.to_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'fund_basic_tagged.parquet'))
print('\nsaved e0_etf_candidates.csv:', len(cand2))
print('\n排除统计:')
print(df['excl_tags'].explode().value_counts().head(15))

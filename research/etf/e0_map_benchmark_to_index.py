#!/usr/bin/env python3
"""E0 STEP 2: benchmark → CSI 指数 映射（ETF → tracking index → publisher）
输入: data/raw/etf/etf_candidates.parquet, index_basic.parquet
输出: results/etf/e0_etf_to_index_map_raw.csv（含匹配状态 REVIEW/UNMATCHED/OK）
规则: 从 fund_basic.benchmark（基金合同业绩比较基准，正式披露字段）解析指数名，
      与 index_basic.name 匹配，publisher 验证是否中证指数有限公司。
      benchmark 非名称猜测，是基金合同业绩比较基准的正式披露。
"""
import os, re
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
os.makedirs(OUT, exist_ok=True)

cand = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'etf_candidates.parquet'))
ib = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'index_basic.parquet'))

# ---------- benchmark 指数名提取 ----------
def extract_index_name(bench):
    if pd.isna(bench):
        return None
    s = str(bench).strip()
    if not s or '暂无' in s or '不设' in s or '未披露' in s or '没有' in s:
        return None
    # 取第一个 'XX指数' 模式（含中文+字母数字+括号）
    m = re.search(r'([\u4e00-\u9fa5A-Za-z0-9]+(?:指数|指数P|全收益指数))', s)
    if not m:
        return None
    name = m.group(1)
    # 清理
    name = name.replace('指数收益率', '').replace('收益率', '').replace('全收益', '')
    name = re.sub(r'指数P$', '', name)
    name = re.sub(r'指数$', '', name)
    return name

cand['bench_idx_name'] = cand['benchmark'].apply(extract_index_name)
print('benchmark 可解析出指数名的候选:', cand['bench_idx_name'].notna().sum(), '/', len(cand))
print('未解析:', cand['bench_idx_name'].isna().sum())
print()
print('解析出的指数名示例（前30）:')
print(cand['bench_idx_name'].dropna().unique()[:30])

# ---------- 与 index_basic.name 匹配 ----------
ib_name = ib.drop_duplicates(subset=['name'])
print('\nindex_basic 中 name 唯一值:', len(ib_name))

def first_row(df):
    return df.iloc[0]

def match_index(bench_idx):
    if bench_idx is None:
        return {'matched': False, 'status': 'NO_BENCH', 'index_code': None,
                'index_name': None, 'publisher': None, 'category': None, 'n_match': 0}
    # 1. 精确
    exact = ib_name[ib_name['name'] == bench_idx]
    if len(exact) >= 1:
        r = first_row(exact)
        return {'matched': True, 'status': 'OK_EXACT', 'index_code': r['ts_code'],
                'index_name': r['name'], 'publisher': r['publisher'], 'category': r['category'], 'n_match': len(exact)}
    # 2. 子串匹配（name 包含 bench_idx）
    pat = re.escape(str(bench_idx))
    hits = ib_name[ib_name['name'].str.contains(pat, regex=True, na=False)]
    if len(hits) == 1:
        r = first_row(hits)
        return {'matched': True, 'status': 'OK_SUBSTR', 'index_code': r['ts_code'],
                'index_name': r['name'], 'publisher': r['publisher'], 'category': r['category'], 'n_match': 1}
    if len(hits) > 1:
        return {'matched': True, 'status': 'MULTI', 'index_code': hits['ts_code'].tolist(),
                'index_name': hits['name'].tolist(), 'publisher': hits['publisher'].iloc[0],
                'category': hits['category'].iloc[0], 'n_match': len(hits)}
    # 3. 反向：bench_idx 包含 name（如 bench='中证小盘500' name='中证500'）
    hits2 = ib_name[ib_name['name'].str.len() >= 4]
    hits2 = hits2[hits2['name'].apply(lambda n: n in str(bench_idx))]
    if len(hits2) == 1:
        r = first_row(hits2)
        return {'matched': True, 'status': 'OK_REVSUB', 'index_code': r['ts_code'],
                'index_name': r['name'], 'publisher': r['publisher'], 'category': r['category'], 'n_match': 1}
    return {'matched': False, 'status': 'UNMATCHED', 'index_code': None,
            'index_name': None, 'publisher': None, 'category': None, 'n_match': 0}

res = pd.DataFrame(cand['bench_idx_name'].map(match_index).tolist())
res.columns = ['map_' + c for c in res.columns]
mapped = pd.concat([cand.reset_index(drop=True), res.reset_index(drop=True)], axis=1)

print('\n匹配状态分布:')
print(mapped['map_status'].value_counts(dropna=False))
print()
print('MULTI 样本:')
print(mapped[mapped['map_status']=='MULTI'][['ts_code','name','bench_idx_name','map_index_name']].head(10).to_string())
print()
print('UNMATCHED 样本:')
print(mapped[mapped['map_status']=='UNMATCHED'][['ts_code','name','benchmark','bench_idx_name']].head(20).to_string())

# 保存原始映射
mapped.to_csv(os.path.join(OUT, 'e0_etf_to_index_map_raw.csv'), index=False)
mapped.to_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'etf_index_map_raw.parquet'))
print('\nsaved e0_etf_to_index_map_raw.csv')

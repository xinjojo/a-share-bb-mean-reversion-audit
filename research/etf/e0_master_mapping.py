#!/usr/bin/env python3
"""E0 STEP 2c: MASTER ETF→指数 MAPPING（identity 部分，含 publisher 判定）
最终字段（行情/流动性类在数据下载完成后由 e0_build_master_full.py 补齐）:
  etf_code, etf_name, exchange, list_date, delist_date, fund_manager, fund_type,
  index_code, index_name, index_publisher, index_category,
  domestic_a_share_flag, passive_index_flag, asset_class, eligible, exclusion_reason,
  match_level, match_status, data_source, retrieval_date, bench_idx_name
判定规则:
  match_level L1/L2/L2B: 交易所指数(.SH/.SZ)权威匹配 → publisher/category 来自 Tushare
  match_level L3: CSI 指数(.CSI)匹配 → publisher=中证
  match_level L5: 规则归属（benchmark 前缀）→ publisher_confidence=RULE_BASED
  MIXED 判定: benchmark 含 港股/沪港深/恒生/沪深港/中华交易 等跨境成分
"""
import os, re
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
os.makedirs(OUT, exist_ok=True)

cand = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'etf_candidates.parquet'))
ib_csi = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'index_basic.parquet'))
ib_ex = pd.read_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'index_basic_exchange.parquet'))

def extract_index_name(bench):
    if pd.isna(bench):
        return None
    s = str(bench).strip()
    if not s or any(k in s for k in ['暂无', '不设', '未披露', '没有']):
        return None
    m = re.search(r'([\u4e00-\u9fa5A-Za-z0-9]+(?:指数|指数P|全收益指数))', s)
    if not m:
        return None
    name = m.group(1).replace('指数收益率', '').replace('收益率', '').replace('全收益', '')
    name = re.sub(r'指数P$', '', name)
    name = re.sub(r'指数$', '', name)
    name = name.replace('（人民币）', '').replace('(人民币)', '').replace('(简称:', '').replace(')', '')
    return name

cand['bench_idx_name'] = cand['benchmark'].apply(extract_index_name)

# 归一化（去常见前后缀/修饰词）用于近似匹配
PREFIXES = ['中证全指', '中证', '上证', '深证', '国证', '创业板', '沪深', '中华交易服务']
SUFFIXES = ['主题', '行业', '产业', '指数', '成份', '成分', '综合', '龙头', '等权', '质量', '红利', '低波', '策略']

def normalize(name):
    s = str(name)
    for p in PREFIXES:
        s = s.replace(p, '')
    for su in SUFFIXES:
        if s.endswith(su):
            s = s[: -len(su)]
            break
    return s

# 匹配层级
def match(bench):
    if bench is None or not isinstance(bench, str):
        return dict(match_level='NO_BENCH', index_code=None, index_name=None, publisher=None,
                    category=None, n_match=0, match_status='NO_BENCH')
    # L1 EX 精确
    e = ib_ex[ib_ex['name'] == bench]
    if len(e) >= 1:
        r = e.iloc[0]
        return dict(match_level='L1_EX_EXACT', index_code=r['ts_code'], index_name=r['name'],
                    publisher=r['publisher'], category=r['category'], n_match=len(e), match_status='OK')
    # L2 EX 子串（唯一）
    hits = ib_ex[ib_ex['name'].str.contains(re.escape(bench), regex=True, na=False)]
    if len(hits) == 1:
        r = hits.iloc[0]
        return dict(match_level='L2_EX_SUBSTR', index_code=r['ts_code'], index_name=r['name'],
                    publisher=r['publisher'], category=r['category'], n_match=1, match_status='OK')
    # L2B EX 反向包含（唯一）
    hits2 = ib_ex[ib_ex['name'].str.len() >= 3]
    hits2 = hits2[hits2['name'].apply(lambda n: n in bench)]
    if len(hits2) == 1:
        r = hits2.iloc[0]
        return dict(match_level='L2B_EX_REVSUB', index_code=r['ts_code'], index_name=r['name'],
                    publisher=r['publisher'], category=r['category'], n_match=1, match_status='OK')
    # L3 CSI 精确/子串
    c3 = ib_csi[ib_csi['name'] == bench]
    if len(c3) >= 1:
        r = c3.iloc[0]
        return dict(match_level='L3_CSI_EXACT', index_code=r['ts_code'], index_name=r['name'],
                    publisher=r['publisher'], category=r['category'], n_match=len(c3), match_status='OK')
    hits3 = ib_csi[ib_csi['name'].str.contains(re.escape(bench), regex=True, na=False)]
    if len(hits3) == 1:
        r = hits3.iloc[0]
        return dict(match_level='L3_CSI_SUBSTR', index_code=r['ts_code'], index_name=r['name'],
                    publisher=r['publisher'], category=r['category'], n_match=1, match_status='OK')
    # L4 归一化近似（核心词包含，唯一）
    nb = normalize(bench)
    if len(nb) >= 3:
        n_ex = ib_ex[ib_ex['name'].apply(lambda n: nb in normalize(n))]
        if len(n_ex) == 1:
            r = n_ex.iloc[0]
            return dict(match_level='L4_NORM_EX', index_code=r['ts_code'], index_name=r['name'],
                        publisher=r['publisher'], category=r['category'], n_match=1, match_status='OK_NORM')
        n_csi = ib_csi[ib_csi['name'].apply(lambda n: nb in normalize(n))]
        if len(n_csi) == 1:
            r = n_csi.iloc[0]
            return dict(match_level='L4_NORM_CSI', index_code=r['ts_code'], index_name=r['name'],
                        publisher=r['publisher'], category=r['category'], n_match=1, match_status='OK_NORM')
    # L5 规则归属
    return dict(match_level='L5_RULE', index_code=None, index_name=bench, publisher=None,
                category=None, n_match=0, match_status='RULE')

res = pd.DataFrame(cand['bench_idx_name'].map(match).tolist())
res.columns = ['map_' + c for c in res.columns]
m = pd.concat([cand.reset_index(drop=True), res.reset_index(drop=True)], axis=1)

# ---------- publisher 归属（L5 兜底 + MIXED 判定） ----------
def final_publisher(row):
    if row['map_publisher'] is not None and pd.notna(row['map_publisher']) and str(row['map_publisher']) != 'nan':
        return str(row['map_publisher'])
    b = str(row['bench_idx_name'])
    if '中证' in b: return '中证指数有限公司'
    if '上证' in b or '科创' in b: return '中证指数有限公司/上海证券交易所'
    if '深证' in b or '创业板' in b: return '深圳证券信息有限公司'
    if '国证' in b: return '深圳证券信息有限公司'
    if '富时' in b: return 'FTSE Russell'
    if '中华' in b or '沪深港' in b: return '中华交易服务有限公司'
    return 'UNKNOWN'

m['index_publisher'] = m.apply(final_publisher, axis=1)
m['publisher_confidence'] = m.apply(
    lambda r: 'INDEX_BASIC' if (r['map_publisher'] is not None and str(r['map_publisher']) != 'nan') else 'RULE_BASED', axis=1)

# ---------- 各类 flag ----------
CROSS_KW = ['港股', '沪港深', '沪深港', '恒生', '恒指', 'H股', '中华交易', '港币', 'HKD', 'MSCI', '海外', '全球']
def flags(row):
    bench = str(row['bench_idx_name']) if pd.notna(row['bench_idx_name']) else ''
    name = str(row['name'])
    bm = str(row['benchmark']) if pd.notna(row['benchmark']) else ''
    # 被动指数型
    passive = (row['invest_type'] == '被动指数型')
    # 境内 A 股: 非跨境、非商品/债券
    cross = any(k in bench + bm + name for k in CROSS_KW)
    domestic = (not cross) and (row['fund_type'] in ('股票型', '混合型'))
    return pd.Series({
        'passive_index_flag': passive,
        'cross_mixed_flag': cross,
        'domestic_a_share_flag': domestic and (not cross),
    })

fl = m.apply(flags, axis=1)
m = pd.concat([m, fl], axis=1)

# ---------- eligible / exclusion_reason ----------
def eligibility(row):
    reasons = []
    if not row['passive_index_flag']:
        reasons.append('NOT_PASSIVE')
    if row['cross_mixed_flag']:
        reasons.append('CROSS/MIXED')
    if not row['domestic_a_share_flag']:
        reasons.append('NOT_DOMESTIC_A_SHARE')
    if '黄金' in str(row['bench_idx_name']) or '商品' in str(row['bench_idx_name']):
        reasons.append('COMMODITY')
    # CSI 核心：publisher 含中证指数有限公司
    pub = str(row['index_publisher'])
    is_csi = ('中证指数有限公司' in pub)
    eligible = (row['passive_index_flag'] and row['domestic_a_share_flag'] and not row['cross_mixed_flag'])
    return pd.Series({
        'is_csi_publisher': is_csi,
        'eligible': eligible,
        'exclusion_reason': ';'.join(reasons) if reasons else '',
    })

el = m.apply(eligibility, axis=1)
m = pd.concat([m, el], axis=1)

# ---------- 静态字段组装 ----------
out = pd.DataFrame({
    'etf_code': m['ts_code'],
    'etf_name': m['name'],
    'exchange': m['ts_code'].str[-2:],
    'list_date': m['list_date'],
    'delist_date': m['delist_date'],
    'found_date': m['found_date'],
    'fund_manager': m['management'],
    'fund_type': m['fund_type'],
    'invest_type': m['invest_type'],
    'status': m['status'],
    'index_code': m['map_index_code'],
    'index_name': m['bench_idx_name'],
    'index_publisher': m['index_publisher'],
    'publisher_confidence': m['publisher_confidence'],
    'index_category': m['map_category'],
    'passive_index_flag': m['passive_index_flag'],
    'domestic_a_share_flag': m['domestic_a_share_flag'],
    'cross_mixed_flag': m['cross_mixed_flag'],
    'is_csi_publisher': m['is_csi_publisher'],
    'asset_class': 'EQUITY',
    'eligible': m['eligible'],
    'exclusion_reason': m['exclusion_reason'],
    'match_level': m['map_match_level'],
    'match_status': m['map_match_status'],
    'bench_idx_name': m['bench_idx_name'],
    'benchmark': m['benchmark'],
    'data_source': 'Tushare fund_basic.benchmark + index_basic',
    'retrieval_date': m['retrieval_date'],
})
out.to_csv(os.path.join(OUT, 'e0_etf_to_index_map_raw.csv'), index=False)
out.to_parquet(os.path.join(DATA_ROOT, 'data', 'raw', 'etf', 'etf_index_map_master.parquet'))
print('saved e0_etf_to_index_map_raw.csv rows:', len(out))

print('\n=== 汇总 ===')
print('match_level 分布:')
print(out['match_level'].value_counts().to_dict())
print('\npublisher_confidence:')
print(out['publisher_confidence'].value_counts().to_dict())
print('\nis_csi_publisher:')
print(out['is_csi_publisher'].value_counts().to_dict())
print('\neligible:')
print(out['eligible'].value_counts().to_dict())
print('\nCSi 核心（is_csi_publisher & eligible）:', ((out['is_csi_publisher']) & (out['eligible'])).sum())
print('status 分布（eligible 内）:')
print(out[out['eligible']]['status'].value_counts().to_dict())

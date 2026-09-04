#!/usr/bin/env python3
"""E0 STEP 7: ETF Trading Rules Audit（数据驱动 + 静态规则）
输出: results/etf/e0_trading_rules_audit.md + results/etf/e0_price_limit_rule.csv
规则事实（来源见 audit md 中的 source 标注）:
  T+1: 境内 A 股股票 ETF 二级市场 T+1（当日买入当日不可卖）；
       债券/黄金/货币/商品期货/跨境 ETF 为 T+0（本 universe 不涉及，仅披露）。
  申报单位: 100 份整数倍；零股卖出一次性。
  tick: 0.001 元（基金最小价格变动单位，区别于 A 股 0.01）。
  涨跌幅: 深交所2023修订交易规则: 基金默认10%；跟踪成分股仅为创业板/20%股票的指数型 ETF 为20%。
          上交所科创板相关基金20%。创业板 ETF 2020-08-24 起 20%。
  成本: ETF 二级市场无印花税、无过户费；佣金（含经手费/证管费）baseline 0.025% 最低5元。
  复权: fund_daily raw close × fund_adj(adj_factor) = close_adj。
  停牌/无成交: amount==0 或 volume==0 时不可成交。
"""
import os, json
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
print('master rows:', len(master))

# ---------- 涨跌幅规则推断（逐 ETF） ----------
def price_limit_rule(row):
    name = str(row['etf_name'])
    idx = str(row['index_name']) if pd.notna(row['index_name']) else ''
    bm = str(row['benchmark']) if pd.notna(row['benchmark']) else ''
    all_s = name + idx + bm
    if any(k in all_s for k in ['科创', '双创']):
        return '20PCT_STAR'
    if any(k in all_s for k in ['创业板', '创业']):
        return '20PCT_GEM_20200824'
    return '10PCT'

master['price_limit_rule'] = master.apply(price_limit_rule, axis=1)
master['t_plus_rule'] = 'T+1'
master['tick_size'] = 0.001
master['lot_size'] = 100

# 2020-08-24 后 20% 的创业板规则：创业板 ETF 需要按时间分段的 PIT 规则（10% 前 / 20% 后）
master['price_limit_pit'] = master['price_limit_rule'].apply(
    lambda r: '10PCT_until_2020-08-23_then_20PCT' if r == '20PCT_GEM_20200824' else r)

master[['etf_code', 'etf_name', 'index_name', 'price_limit_rule', 'price_limit_pit', 't_plus_rule', 'tick_size', 'lot_size']].to_csv(
    os.path.join(OUT, 'e0_price_limit_rule.csv'), index=False)

print('price_limit_rule 分布:')
print(master['price_limit_rule'].value_counts().to_dict())

# ---------- 数据驱动的规则核验（amount==0 / volume==0 停牌日、tick 分辨率、价格最小变动） ----------
n_zero_amt = 0
n_zero_vol = 0
n_tick_irreg = 0
n_no_daily = 0
examples = []
for i, r in master.iterrows():
    tc = r['etf_code']
    p = os.path.join(RAWDIR, 'fund_daily', tc.replace('.', '_') + '.parquet')
    if not os.path.exists(p):
        n_no_daily += 1
        continue
    fd = pd.read_parquet(p)
    if len(fd) == 0:
        n_no_daily += 1
        continue
    amt = pd.to_numeric(fd['amount'], errors='coerce')
    vol = pd.to_numeric(fd['vol'], errors='coerce')
    n_zero_amt += int((amt.fillna(0) == 0).sum())
    n_zero_vol += int((vol.fillna(0) == 0).sum())
    # tick 检查：close 的小数位数是否通常为 3 位（0.001 tick）
    close = fd['close'].dropna()
    if len(close):
        dec = (close * 1000).apply(lambda x: abs(x - round(x)) < 1e-6)
        if dec.mean() < 0.9:
            n_tick_irreg += 1
            if len(examples) < 5:
                examples.append((tc, round(float(dec.mean()), 3)))

print('\n数据驱动规则核验:')
print(f'  ETF 无 fund_daily: {n_no_daily}')
print(f'  amount==0 交易日总数: {n_zero_amt}')
print(f'  vol==0 交易日总数: {n_zero_vol}')
print(f'  close 非 0.001 tick 分辨率 ETF 数: {n_tick_irreg} (示例: {examples})')

# ---------- 成本模型基线（审计结论写入 md） ----------
cost_model = {
    'commission_rate': 0.00025,
    'min_commission': 5.0,
    'stamp_duty': 0.0,          # ETF 无印花税
    'transfer_fee': 0.0,        # ETF 无过户费（披露：部分券商文档称沪市ETF收万分0.1，sensitivity）
    'slippage_bp': 10,
    'slippage_sensitivity_bp': [5, 10, 20],
    'note': '佣金含经手费/证管费; 无印花税; 无过户费(baseline); slippage baseline 10bp'
}
with open(os.path.join(OUT, 'e0_cost_model.json'), 'w') as f:
    json.dump(cost_model, f, ensure_ascii=False, indent=2)

print('\n成本模型已写入 e0_cost_model.json')

# ---------- 停牌/无成交 ETF 级别统计 ----------
zero = master.copy()
zero['has_daily'] = master['etf_code'].apply(
    lambda c: os.path.exists(os.path.join(RAWDIR, 'fund_daily', c.replace('.', '_') + '.parquet')))
print('\neligible 且有 daily 数据:', ((zero['eligible']) & (zero['has_daily'])).sum())

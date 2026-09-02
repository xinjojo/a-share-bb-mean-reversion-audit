"""生成 HYPOTHESIS_REGISTRY.csv (104 行 PRIMARY 预注册) + 更新 TEMPLATE。
纯预注册, 不读取任何 2020-2022 收益/统计结果。
"""
import csv, hashlib

F = {
 'TREND': {
   'var': 'ret20',
   'formula': 'ret20=idx[T]除以idx[T-20]后减1; idx=全A等权净值(§4); UP=ret20>+0.03; SIDEWAYS=-0.03<=ret20<=+0.03; DOWN=ret20<-0.03; 信息集=T日收盘含T',
   'bins': ['UP','SIDEWAYS','DOWN']},
 'BREADTH': {
   'var': 'ma20_above_ratio',
   'formula': 'ratio=n_above除以denom; denom=|universe[T]|(PIT eligible且非ST); n_above=count(close_adj>MA20); LOW<0.30; MID 0.30-0.70; HIGH>0.70; 信息集=T日收盘含T',
   'bins': ['LOW','MID','HIGH']},
 'VOLATILITY': {
   'var': 'rv20_pctile',
   'formula': 'rv20=std(mkt_ret[T-19..T])乘以sqrt(245); pctile=mean(rv20[T-252..T-1]小于rv20[T]); min_periods=100否则WARMUP; LOW<=0.20; NORMAL 0.20-0.60; HIGH 0.60-0.90; EXTREME>0.90; 信息集=T日收盘含T, 仅用T前历史',
   'bins': ['LOW','NORMAL','HIGH','EXTREME']},
 'LIQUIDITY': {
   'var': 'amt_ratio',
   'formula': 'amt_ratio=market_amount[T]除以MA20(market_amount)[T]; market_amount=sum(amount,PIT eligible且非ST,千元); LOW<0.80; NORMAL 0.80-1.20; HIGH>1.20; 信息集=T日收盘含T',
   'bins': ['LOW','NORMAL','HIGH']},
}
OVERSOLD_BINS = [('B1','-2.0<z<=-1.5'),('B2','-2.5<z<=-2.0'),('B3','-3.0<z<=-2.5'),('B4','z<=-3.0')]
HORIZONS = ['5D','10D']

rows = []
hid = 0
for dim, spec in F.items():
    for b in spec['bins']:
        for ob, orng in OVERSOLD_BINS:
            for hz in HORIZONS:
                hid += 1
                rows.append({
                    'hypothesis_id': f'P{hid:04d}',
                    'family': 'PRIMARY',
                    'regime_dimension': dim,
                    'regime_variable': spec['var'],
                    'regime_formula': spec['formula'],
                    'regime_bin': b,
                    'oversold_feature': 'BB_zscore',
                    'oversold_bin': ob,
                    'oversold_range': orng,
                    'forward_horizon': hz,
                    'outcome_type': 'otc',
                    'benchmark': 'same_oversold_unconditional',
                    'test': 't_HAC+FDR(BH)_q005+block_bootstrap',
                    'fdr_family': 'PRIMARY',
                })

assert hid == 104, f'expected 104, got {hid}'
# 校验无未冻结字段
bad = ['/', '任选', '候选', 'x待定', '历史分位但无lookback']
for r in rows:
    for k, v in r.items():
        for bd in bad:
            assert bd not in v, f'{r["hypothesis_id"]} {k} contains {bd}'
assert all(r['benchmark'] == 'same_oversold_unconditional' for r in rows)

fields = ['hypothesis_id','family','regime_dimension','regime_variable','regime_formula','regime_bin',
          'oversold_feature','oversold_bin','oversold_range','forward_horizon','outcome_type',
          'benchmark','test','fdr_family']

out = 'HYPOTHESIS_REGISTRY.csv'
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

with open(out, 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
print(f'rows={len(rows)} sha256={h}')
print('by dimension:', {d: sum(1 for r in rows if r["regime_dimension"]==d) for d in F})
print('benchmark unique:', set(r['benchmark'] for r in rows))

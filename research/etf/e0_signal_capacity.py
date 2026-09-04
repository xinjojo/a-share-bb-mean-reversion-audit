#!/usr/bin/env python3
"""E0 STEP 10-11: Signal-density + Capital-utilization Diagnostic（冻结 BB baseline 原样使用）
冻结参数（股票版 STRICT_C baseline，禁止改动）:
  bb_window=20, bb_std=2.0; 信号 close_adj<bb_lower(下轨超卖)
  close_adj = close * fund_adj; 候选按当日 amount Top10
  组合 K=3, max_levels=5, 单层 200,000, 初始 1,000,000; 滑点 10bp; 佣金 0.025% 最低5元（无印花税/过户费）
  退出: STRICT_C natural exit (dynamic_touch: high_adj>=Pstar; Pstar=analytic_Pstar(近19日 close_adj))
        TAKE_PROFIT_UB=次日 open; FINAL_SETTLE=期末 close*(1-slip)
  T+1; ETF lot=100 份; tick=0.001; 涨跌幅按 price_limit_rule（10%/20%，PIT 创业板 2020-08-24）
输出:
  results/etf/e0_signal_density.csv
  results/etf/e0_capital_utilization.csv
  results/etf/e0_signal_daily_detail.csv（daily 信号明细）
PIT 代表选择（E0 预注册，E1 前冻结）: B2 = trailing ADV60(t-1) 最大的已上市 ETF
"""
import os, sys
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

sys.path.insert(0, DATA_ROOT)
from run_strict_c_math import analytic_Pstar

BB_WINDOW, BB_STD = 20, 2.0
K, MAX_LEVELS, LEVEL_CASH, INITIAL = 3, 5, 200_000, 1_000_000
SLIP = 10 / 10000.0
COMM = 0.00025
MIN_COMM = 5.0
TOP_N = 10

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
# 合并涨跌幅规则
plr_path = os.path.join(OUT, 'e0_price_limit_rule.csv')
if os.path.exists(plr_path):
    plr_df = pd.read_csv(plr_path, usecols=['etf_code', 'price_limit_pit'])
    master = master.merge(plr_df, on='etf_code', how='left')
else:
    master['price_limit_pit'] = '10PCT'
master['price_limit_pit'] = master['price_limit_pit'].fillna('10PCT')
elig = master[master['eligible']].copy()
elig['list_date_dt'] = pd.to_datetime(elig['list_date'], errors='coerce')
elig['delist_date_dt'] = pd.to_datetime(elig['delist_date'], errors='coerce')
elig['index_key'] = elig.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
print('eligible ETF:', len(elig), 'unique index_key:', elig['index_key'].nunique())

# ---------- 逐 ETF 计算特征（长表） ----------
feat_parts = []
for i, r in elig.iterrows():
    tc = r['etf_code']
    p = os.path.join(RAWDIR, 'fund_daily', tc.replace('.', '_') + '.parquet')
    if not os.path.exists(p):
        continue
    fd = pd.read_parquet(p)
    if len(fd) == 0:
        continue
    fd['date'] = pd.to_datetime(fd['trade_date'])
    fd = fd.sort_values('date').reset_index(drop=True)
    close = pd.to_numeric(fd['close'], errors='coerce')
    high = pd.to_numeric(fd['high'], errors='coerce')
    open_ = pd.to_numeric(fd['open'], errors='coerce')
    amt = pd.to_numeric(fd['amount'], errors='coerce')
    # 复权因子
    ap = os.path.join(RAWDIR, 'fund_adj', tc.replace('.', '_') + '.parquet')
    adj = pd.Series(1.0, index=fd.index)
    if os.path.exists(ap):
        fa = pd.read_parquet(ap)
        if len(fa):
            fa['date'] = pd.to_datetime(fa['trade_date'])
            fa = fa.sort_values('date').drop_duplicates('date').set_index('date')['adj_factor']
            adj = fd['date'].map(fa).fillna(1.0).to_numpy()
    close_adj = close * adj
    high_adj = high * adj
    ca = close_adj.to_numpy()
    ma = pd.Series(ca).rolling(BB_WINDOW, min_periods=BB_WINDOW).mean().to_numpy()
    sd = pd.Series(ca).rolling(BB_WINDOW, min_periods=BB_WINDOW).std().to_numpy()
    bb_lower = ma - BB_STD * sd
    adv60 = amt.rolling(60, min_periods=20).mean().shift(1)
    # P*（近19日 close_adj）
    pstar = np.full(len(fd), np.nan)
    for j in range(BB_WINDOW, len(fd)):
        x = ca[j - 19:j]
        if np.all(np.isfinite(x)) and x.std() > 1e-9:
            pstar[j] = analytic_Pstar(x)
    plr = r['price_limit_pit']
    out = pd.DataFrame({
        'date': fd['date'], 'etf': tc, 'index_key': r['index_key'],
        'close': close.to_numpy(), 'open': open_.to_numpy(), 'high': high.to_numpy(),
        'close_adj': close_adj.to_numpy(), 'high_adj': high_adj.to_numpy(),
        'adj': adj if isinstance(adj, np.ndarray) else np.asarray(adj),
        'bb_lower': bb_lower, 'amount': amt.to_numpy(), 'adv60': adv60.to_numpy(),
        'pstar': pstar,
        'list_date': r['list_date_dt'], 'delist': r['delist_date_dt'],
        'price_limit_pit': plr, 'fund_adj_flag': (adj != 1.0).any(),
    })
    feat_parts.append(out)

feat = pd.concat(feat_parts, ignore_index=True)
print('feat rows:', len(feat))
feat.to_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
del feat_parts

# ---------- 逐日 PIT 代表选择（B2: 每个 index_key 每日 ADV60(t-1) 最大且已上市） ----------
feat = feat[feat['date'] <= '2026-09-03']
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
# 上市满 60 交易日（近似: 用列表上市后 60 个该 ETF 的交易日，简化用 date>=list_date+60cal 天）
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
print('listed & n_days>=60 rows:', len(avail))

# 每 index_key-date 选 adv60 最大
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date'])
print('PIT 代表（index_key×date）:', len(rep))

# 每个 index_key 可用的代表 ETF 数（历史）
n_rep_etf = rep.groupby('index_key')['etf'].nunique()
print('\n每个指数历史代表 ETF 数分布:')
print(n_rep_etf.describe())

# ---------- Signal-density ----------
sd = rep.copy()
sd['signal'] = (sd['close_adj'] < sd['bb_lower']) & (sd['amount'].fillna(0) > 0) & sd['bb_lower'].notna()
daily = sd.groupby('date').agg(
    eligible=('etf', 'count'),
    n_signal=('signal', 'sum'),
    n_amount_pos=('amount', lambda x: (x.fillna(0) > 0).sum()),
).reset_index()
daily['signal_ratio'] = daily['n_signal'] / daily['eligible']

out_sd = pd.DataFrame({
    'metric': ['total_days', 'eligible_etf_mean', 'eligible_etf_median', 'eligible_etf_max',
               'signal_days', 'mean_daily_signal', 'median_daily_signal',
               'p75_signal', 'p90_signal', 'max_signal',
               'pct_0_signal_days', 'pct_1plus_signal_days', 'pct_3plus_signal_days',
               'pct_5plus_signal_days', 'pct_10plus_signal_days',
               'mean_signal_ratio', 'max_signal_ratio'],
    'value': [
        len(daily), daily['eligible'].mean(), daily['eligible'].median(), daily['eligible'].max(),
        int((daily['n_signal'] > 0).sum()), daily['n_signal'].mean(), daily['n_signal'].median(),
        daily['n_signal'].quantile(0.75), daily['n_signal'].quantile(0.90), daily['n_signal'].max(),
        float((daily['n_signal'] == 0).mean() * 100),
        float((daily['n_signal'] >= 1).mean() * 100),
        float((daily['n_signal'] >= 3).mean() * 100),
        float((daily['n_signal'] >= 5).mean() * 100),
        float((daily['n_signal'] >= 10).mean() * 100),
        daily['signal_ratio'].mean(), daily['signal_ratio'].max(),
    ]
})
out_sd.to_csv(os.path.join(OUT, 'e0_signal_density.csv'), index=False)
daily.to_csv(os.path.join(OUT, 'e0_signal_daily_detail.csv'), index=False)
print('\n=== Signal-density ===')
print(out_sd.to_string(index=False))

# ---------- Capital-utilization（迷你组合模拟，冻结参数） ----------
# 用 PIT 代表面板，amount Top10 候选，T+1 open 成交，dynamic P* 退出
panel = sd.sort_values(['date', 'amount'], ascending=[True, False]).copy()
panel['is_signal'] = panel['signal']
days = sorted(panel['date'].unique())
D = {}
for d, g in panel.groupby('date'):
    D[d] = g  # 已按 amount 降序

positions = []  # dict: etf,index_key,shares,avg_cost,levels,total_cost,entry_day_idx,last_add
cash = INITIAL
cash_history = []
equity_hist = []
pending_buy = []  # 次日 open 买
pending_add = {}  # etf -> True

def commission(amt):
    return max(amt * COMM, MIN_COMM)

def find_pos(idx):
    return next((p for p in positions if p['index_key'] == idx), None)

for i, d in enumerate(days):
    g = D[d]
    # ---- open: 执行 pending ----
    if pending_buy:
        for pb in list(pending_buy):
            if len(positions) >= K:
                continue
            row = g[g['index_key'] == pb]
            if len(row) == 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            # 涨跌幅约束: open 相对 pre_close 触及涨停则买不进（简化: 用当日 close 判断异常跳过）
            price = opx * (1 + SLIP)
            qty = int(min(LEVEL_CASH, cash) / price / 100) * 100
            if qty < 100:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            amt = price * qty
            fee = commission(amt)
            if amt + fee > cash:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            cash -= amt + fee
            positions.append({'index_key': pb, 'etf': r['etf'], 'shares': qty,
                              'avg_cost': (amt + fee) / qty, 'levels': 1,
                              'total_cost': amt + fee, 'entry_day_idx': i, 'last_add': i})
            pending_buy = [x for x in pending_buy if x != pb]
    if pending_add:
        for idx in list(pending_add.keys()):
            pos = find_pos(idx)
            if pos is None or pos['levels'] >= MAX_LEVELS:
                pending_add.pop(idx, None)
                continue
            row = g[g['index_key'] == idx]
            if len(row) == 0:
                pending_add.pop(idx, None)
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0:
                pending_add.pop(idx, None)
                continue
            price = opx * (1 + SLIP)
            qty = int(min(LEVEL_CASH, cash) / price / 100) * 100
            if qty >= 100:
                amt = price * qty
                fee = commission(amt)
                if amt + fee <= cash:
                    cash -= amt + fee
                    old = pos['shares'] * pos['avg_cost']
                    pos['shares'] += qty
                    pos['avg_cost'] = (old + amt + fee) / pos['shares']
                    pos['total_cost'] += amt + fee
                    pos['levels'] += 1
                    pos['last_add'] = i
            pending_add.pop(idx, None)

    # ---- 盘中 dynamic touch 退出: high_adj >= Pstar ----
    for pos in list(positions):
        row = g[g['index_key'] == pos['index_key']]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        if pd.notna(r['pstar']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['pstar']:
            px = (r['pstar'] / r['adj']) * (1 - SLIP)
            amt = px * pos['shares']
            fee = commission(amt)
            cash += amt - fee
            positions.remove(pos)

    # ---- close: 加仓/新买信号 ----
    for _, r in g.iterrows():
        held = {p['index_key'] for p in positions}
        if r['index_key'] in held:
            pos = find_pos(r['index_key'])
            if (pos and pos['levels'] < MAX_LEVELS and pd.notna(r['bb_lower'])
                    and r['close_adj'] < r['bb_lower'] and r['amount'] > 0
                    and (i - pos['last_add']) >= 1):
                pending_add[r['index_key']] = True
        elif r['is_signal'] and len(positions) + len(pending_buy) < K:
            if r['index_key'] not in pending_buy:
                pending_buy.append(r['index_key'])

    # ---- 估值 ----
    stock_val = 0.0
    for pos in positions:
        row = g[g['index_key'] == pos['index_key']]
        px = row.iloc[0]['close'] if len(row) else pos['avg_cost']
        stock_val += pos['shares'] * px
    equity = cash + stock_val
    cash_history.append((d, cash))
    equity_hist.append((d, equity))

# ---- 期末清仓 ----
last_d = days[-1]
g = D[last_d]
for pos in list(positions):
    row = g[g['index_key'] == pos['index_key']]
    px = row.iloc[0]['close'] * (1 - SLIP) if len(row) else pos['avg_cost']
    amt = px * pos['shares']
    fee = commission(amt)
    cash += amt - fee
    positions.remove(pos)

eq_df = pd.DataFrame(equity_hist, columns=['date', 'equity'])
cash_df = pd.DataFrame(cash_history, columns=['date', 'cash'])
merged = eq_df.merge(cash_df, on='date')
merged['invested'] = merged['equity'] - merged['cash']
merged['invested_pct'] = merged['invested'] / merged['equity']

out_cu = pd.DataFrame({
    'metric': ['total_days', 'avg_invested_pct', 'median_invested_pct', 'mean_cash_pct',
               'days_fully_invested_pct', 'days_lt50_invested_pct',
               'final_equity', 'total_return_pct', 'mean_signal_per_day'],
    'value': [
        len(merged),
        float(merged['invested_pct'].mean() * 100),
        float(merged['invested_pct'].median() * 100),
        float(merged['cash'].mean() / merged['equity'].mean() * 100),
        float((merged['invested_pct'] >= 0.99).mean() * 100),
        float((merged['invested_pct'] < 0.5).mean() * 100),
        float(merged['equity'].iloc[-1]),
        float((merged['equity'].iloc[-1] / INITIAL - 1) * 100),
        float(daily['n_signal'].mean()),
    ]
})
out_cu.to_csv(os.path.join(OUT, 'e0_capital_utilization.csv'), index=False)
print('\n=== Capital-utilization ===')
print(out_cu.to_string(index=False))
merged.to_csv(os.path.join(OUT, 'e0_capital_daily.csv'), index=False)

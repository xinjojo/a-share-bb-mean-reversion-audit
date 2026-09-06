"""EARLY-EXIT 综合分析 — 任务B: 2020-2024选参区间指标 + 交易级救单/截断分解 + 集中度 + 亿纬案例
选参只依据 2020-01-01 ~ 2024-12-31; 2025-2026 已暴露数据仅单独展示。
"""
import os
import numpy as np, pandas as pd

OUT = os.path.join('/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat', 'audit_package', 'github_repo',
                   'results', 'evidence', 'ee_audit')
XS = [0.0, 0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]
XLBL = {0.0: '0.00', 0.001: '0.10', 0.002: '0.20', 0.003: '0.30', 0.005: '0.50',
        0.0075: '0.75', 0.01: '1.00', 0.015: '1.50', 0.02: '2.00'}

def metrics(equity, cutoff=None):
    e = equity.copy()
    if cutoff is not None:
        e = e[e['date'] <= cutoff].reset_index(drop=True)
    v = e['equity'].to_numpy(dtype=float)
    total = v[-1] / v[0] - 1
    ny = len(v) / 245
    ann = (1 + total) ** (1 / ny) - 1 if ny > 0 else 0
    peak = np.maximum.accumulate(v)
    mdd = ((v - peak) / peak).min()
    r = np.diff(v) / v[:-1]
    sh = float(np.mean(r) / np.std(r) * np.sqrt(245)) if np.std(r) > 0 else 0
    return total * 100, ann * 100, mdd * 100, sh

rows = []
for x in XS:
    stem = 'base' if x == 0 else f'ee_{XLBL[x]}'
    eq = pd.read_csv(os.path.join(OUT, f'base_equity.csv' if x == 0 else f'equity_{stem}.csv'))
    tr = pd.read_csv(os.path.join(OUT, f'base_trades.csv' if x == 0 else f'trades_{stem}.csv'))
    tr['entry_date'] = tr['entry_date'].astype(str)
    t_all, a_all, m_all, s_all = metrics(eq)
    t_dev, a_dev, m_dev, s_dev = metrics(eq, '2024-12-31')
    t_25, a_25, m_25, s_25 = metrics(eq, None)
    # 2025-2026 单独区间
    eq25 = eq[eq['date'] >= '2025-01-01'].reset_index(drop=True)
    if len(eq25) > 1:
        v = eq25['equity'].to_numpy(dtype=float)
        t25 = v[-1] / v[0] - 1
    else:
        t25 = np.nan
    tr25 = tr[tr['exit_date'] >= '2025-01-01']
    rows.append(dict(threshold_pct=x * 100,
                     total_all=t_all, cagr_all=a_all, mdd_all=m_all, sharpe_all=s_all,
                     total_2020_2024=t_dev, cagr_2020_2024=a_dev, mdd_2020_2024=m_dev, sharpe_2020_2024=s_dev,
                     total_2025_2026=t25 * 100 if t25 == t25 else np.nan,
                     trades=len(tr), trades_2020_2024=int((tr['entry_date'] <= '2024-12-31').sum()),
                     trades_2025_2026=len(tr25),
                     stock_pnl=tr['pnl'].sum()))
res = pd.DataFrame(rows)
res.to_csv(os.path.join(OUT, 'early_exit_parameter_results_dev.csv'), index=False)
pd.set_option('display.width', 200)
print('=== 区间指标 (2020-2024 为选参依据) ===')
print(res.round(2).to_string(index=False))

# ===== 交易级对比 (base vs each X) =====
base = pd.read_csv(os.path.join(OUT, 'base_trades.csv'))
base['entry_date'] = base['entry_date'].astype(str)
base_key = set(zip(base['ts_code'], base['entry_date']))
cmp_rows = []
for x in XS[1:]:
    stem = f'ee_{XLBL[x]}'
    tr = pd.read_csv(os.path.join(OUT, f'trades_{stem}.csv'))
    tr['entry_date'] = tr['entry_date'].astype(str)
    merged = base.merge(tr, on=['ts_code', 'entry_date'], suffixes=('_base', '_ee'), how='outer')
    both = merged.dropna(subset=['pnl_base', 'pnl_ee'])
    early = both[both['exit_date_base'].astype(str) != both['exit_date_ee'].astype(str)]
    common = both[both['exit_date_base'].astype(str) == both['exit_date_ee'].astype(str)]
    new = merged[merged['pnl_base'].isna()]
    dropped = merged[merged['pnl_ee'].isna()]
    early_delta = (early['pnl_ee'] - early['pnl_base']).sum()
    cmp_rows.append(dict(threshold_pct=x * 100,
                         common=len(common), early=len(early),
                         new=len(new), dropped=len(dropped),
                         early_delta_pnl=round(early_delta, 2),
                         new_pnl=round(new['pnl_ee'].sum(), 2) if len(new) else 0,
                         dropped_pnl=round(dropped['pnl_base'].sum(), 2) if len(dropped) else 0,
                         early_saved=round(early[early['pnl_ee'] > early['pnl_base']]['pnl_ee'].sum() -
                                           early[early['pnl_ee'] > early['pnl_base']]['pnl_base'].sum(), 2),
                         early_truncated=round(early[early['pnl_ee'] <= early['pnl_base']]['pnl_ee'].sum() -
                                               early[early['pnl_ee'] <= early['pnl_base']]['pnl_base'].sum(), 2)))
cmpdf = pd.DataFrame(cmp_rows)
cmpdf.to_csv(os.path.join(OUT, 'early_exit_trade_level_comparison.csv'), index=False)
print('\n=== 交易级对比 ===')
print(cmpdf.to_string(index=False))

# ===== 集中度: 各版本 top1/top5 交易贡献 =====
conc = []
for x in XS:
    stem = 'base' if x == 0 else f'ee_{XLBL[x]}'
    tr = pd.read_csv(os.path.join(OUT, f'base_trades.csv' if x == 0 else f'trades_{stem}.csv'))
    s = tr['pnl'].sort_values(ascending=False).reset_index(drop=True)
    tot = s.sum()
    conc.append(dict(threshold_pct=x * 100, top1_pct=tot and s.iloc[0] / tot * 100,
                     top5_pct=tot and s.head(5).sum() / tot * 100,
                     worst1_pct=tot and s.iloc[-1] / tot * 100,
                     top1_trade=f"{tr.loc[s.index[0], 'ts_code']} {tr.loc[s.index[0], 'entry_date']}" if tot else ''))
concd = pd.DataFrame(conc)
concd.to_csv(os.path.join(OUT, 'early_exit_concentration.csv'), index=False)
print('\n=== 集中度 ===')
print(concd.round(2).to_string(index=False))

# ===== 亿纬锂能 300014.SZ 三个日期 =====
dp = pd.read_csv(os.path.join(OUT, 'all_holding_days_pstar_distance.csv'))
dp['date'] = dp['date'].astype(str)
ev = dp[(dp['ts_code'] == '300014.SZ') & (dp['date'].isin(['2023-04-18', '2023-05-15', '2023-08-04']))]
print('\n=== 亿纬锂能 点名日期 ===')
print(ev[['ts_code', 'date', 'level', 'avg_cost', 'pstar_raw', 'eff_threshold', 'high_raw',
          'gap_eff', 'pct_eff', 'pct_legal', 'triggered', 'float_pnl']].to_string(index=False))
ev_rows = []
for _, r in ev.iterrows():
    for x in XS[1:]:
        eff = np.ceil(r['pstar_raw'] * (1 - x) / 0.01) * 0.01
        hit = r['high_raw'] >= eff
        ev_rows.append(dict(date=r['date'], threshold_pct=x * 100, pstar_raw=round(r['pstar_raw'], 3),
                            eff_threshold=round(eff, 3), high_raw=round(r['high_raw'], 3),
                            gap_yuan=round(eff - r['high_raw'], 3),
                            gap_pct=round((eff - r['high_raw']) / eff * 100, 3), would_exit=bool(hit)))
evd = pd.DataFrame(ev_rows)
evd.to_csv(os.path.join(OUT, 'early_exit_yiwei_cases.csv'), index=False)
print('\n=== 亿纬 逐参数 ===')
print(evd.pivot(index='date', columns='threshold_pct', values='would_exit').to_string())
print('EVWEI DONE')

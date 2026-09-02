"""STRICT_C_CORRECTED: P0 复权口径修正 + P1 tick 双边界
- 前19日 x_k = close_adj[k] = close_raw[k]*adj_factor[k] (各日自己复权因子)
- Pstar_adj = DynamicBBRoot(x_1..x_19); Pstar_raw = Pstar_adj/adj_factor[T]
- tick: conservative(ceil, 主) / optimistic / none
- P0 影响审计 + 全量重跑 + OOS + 分年 + old vs corrected 对比
"""
import sys, os
import numpy as np, pandas as pd
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, full_stats
from run_strict_c import run_fast_multi_strict_c

days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off = prepare_v51(limit_down_mode='correct', st_mode='pit')
for d in days:
    D[d]['one_word'] = ((D[d]['open_'] == D[d]['high']) & (D[d]['low'] == D[d]['close']) & (D[d]['open_'] == D[d]['close']))
rng = (0, len(days))
i24 = next(i for i, d in enumerate(days) if str(d.date()) >= '2024-01-01')

def run(rng, etf=True, tick='conservative'):
    eq, tr, ac, pa = run_fast_multi_strict_c(
        days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', tick_mode=tick, etf_enabled=etf, day_range=rng)
    return eq, tr, pa

# ============ 1) P0 影响审计 (corrected combo, tick conservative) ============
print('===== 1) P0 复权口径影响审计 =====')
eqC, trC, pa = run(rng, etf=True, tick='conservative')
pa.to_csv(os.path.join(ROOT, 'results', 'round5', 'p0_audit.csv'), index=False)
if len(pa):
    n = len(pa)
    changed = pa['adj_changed'].sum()
    print(f'评估 stock-days 总数: {n}; 窗口内 adj_factor 变化: {int(changed)} ({changed/n*100:.2f}%)')
    sub = pa[pa['pstar_old'].notna() & pa['pstar_correct'].notna()]
    if len(sub):
        sub['d'] = sub['pstar_correct'] - sub['pstar_old']
        sub['dpct'] = sub['d'] / sub['pstar_old'].abs() * 100
        print(f'Pstar_correct - Pstar_old: mean_abs={sub["d"].abs().mean():.4f} median={sub["d"].median():.4f} '
              f'max_abs={sub["d"].abs().max():.4f} mean_pct={sub["dpct"].mean():.4f}%')
    # 触发差异
    both = pa[pa['pstar_old'].notna()]
    y_y = ((both['old_trigger']) & (both['corr_trigger'])).sum()
    y_n = ((both['old_trigger']) & (~both['corr_trigger'])).sum()
    n_y = ((~both['old_trigger']) & (both['corr_trigger'])).sum()
    n_n = ((~both['old_trigger']) & (~both['corr_trigger'])).sum()
    print(f'触发对照(旧 vs 修正): 都触发={y_y} 旧触/修不触={y_n} 旧不触/修触={n_y} 都不触={n_n}')
    print(f'  触发改变总量: {y_n+n_y} ({(y_n+n_y)/len(both)*100:.2f}%)')
trC.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_corr_trades.csv'), index=False)
eqC.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_corr_equity.csv'), index=False)

# ============ 2) corrected 收益 ============
print('\n===== 2) STRICT_C_CORRECTED 收益 =====')
def line(name, eq, tr):
    st = full_stats(eq, tr)
    print(f'{name}: total={st["total"]:.2f}% CAGR={st["ann"]:.2f}% MaxDD={st["mdd"]:.2f}% '
          f'Sharpe={st["sharpe"]:.2f} trades={st["n"]} wr={st["wr"]:.1f}% stock_pnl={tr["pnl"].sum():,.0f}')
line('CORRECTED combo (tick=conservative)', eqC, trC)
eqO, trO, _ = run(rng, etf=True, tick='optimistic')
line('CORRECTED combo (tick=optimistic )', eqO, trO)
eqP, trP, _ = run(rng, etf=False, tick='conservative')
line('CORRECTED pure  (tick=conservative)', eqP, trP)
trP.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_corr_pure_trades.csv'), index=False)

# ============ 3) OOS + 分年 ============
print('\n===== 3) OOS 与分年 (corrected combo, conservative) =====')
eq_tr, tr_tr, _ = run((0, i24), etf=True)
eq_te, tr_te, _ = run((i24, len(days)), etf=True)
print('Train 2020-2023:', full_stats(eq_tr, tr_tr))
print('Test  2024-2026:', full_stats(eq_te, tr_te))
pt_eq, pt_tr, _ = run((0, i24), etf=False)
pe_eq, pe_tr, _ = run((i24, len(days)), etf=False)
print('PURE Train:', full_stats(pt_eq, pt_tr))
print('PURE Test :', full_stats(pe_eq, pe_tr))
eq = eqC.copy(); eq['date'] = pd.to_datetime(eq['date']); eq['year'] = eq['date'].dt.year
print('分年(combo):', {int(y): round((g["equity"].iloc[-1]/g["equity"].iloc[0]-1)*100, 2) for y, g in eq.groupby('year')})

# ============ 4) old vs corrected 触发/退出日期对比 ============
print('\n===== 4) old STRICT_C vs corrected STRICT_C 对比 =====')
try:
    told = pd.read_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_trades.csv'))
    oldx = told[told['exit_type'] != 'FINAL_SETTLE'].copy()
    newx = trC[trC['exit_type'] != 'FINAL_SETTLE'].copy()
    oldx['e'] = pd.to_datetime(oldx['entry_date']); newx['e'] = pd.to_datetime(newx['entry_date'])
    oldx['x'] = pd.to_datetime(oldx['exit_date']); newx['x'] = pd.to_datetime(newx['exit_date'])
    used = set(); same = 0; changed = 0; gaps = []
    for _, a in oldx.iterrows():
        cand = newx[(newx['ts_code'] == a['ts_code']) & (newx['e'] >= a['e'] - pd.Timedelta(days=7))
                    & (newx['e'] <= a['e'] + pd.Timedelta(days=7)) & (~newx.index.isin(used))]
        if len(cand) == 0:
            continue
        best = (cand['e'] - a['e']).abs().idxmin(); used.add(best)
        b = newx.loc[best]
        if b['x'] == a['x']:
            same += 1
        else:
            changed += 1; gaps.append(int((b['x'] - a['x']).days))
    print(f'old STRICT_C 非结算交易: {len(oldx)}')
    print(f'  配对: {len(used)}  同日退出: {same}  退出日期改变: {changed}')
    if gaps:
        print(f'  退出日期差(corrected-old, 交易日天): mean={np.mean(gaps):.1f} median={np.median(gaps):.0f} min={min(gaps)} max={max(gaps)}')
    print(f'old stock_pnl={oldx["pnl"].sum():,.0f}  corrected stock_pnl={newx["pnl"].sum():,.0f}  差={newx["pnl"].sum()-oldx["pnl"].sum():,.0f}')
    # 收益差异
    sto = full_stats(pd.read_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_equity.csv')), told)
    print(f'old combo: total={sto["total"]:.2f}%  corrected combo: total={full_stats(eqC,trC)["total"]:.2f}%  diff={full_stats(eqC,trC)["total"]-sto["total"]:.2f}pp')
except Exception as ex:
    print('old 对比失败:', ex)

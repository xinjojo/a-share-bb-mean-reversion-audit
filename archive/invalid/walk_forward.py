"""Walk-Forward 滚动验证：训练窗3年选最优池宽 → 下一年样本外
参数网格：池宽 {5,10,20,30,50}，层数固定5（此前所有证据指向5层最优）
注意：切片起点用 min_listing_days=0（避免训练窗/样本外起点误判新股），已在报告注明近似。
"""
import os, sys, time
import numpy as np
import pandas as pd
import live_backtest as lb

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

t0 = time.time()
print('准备数据...', flush=True)
df = lb.prepare_data()
print(f'数据准备完成 {time.time()-t0:.0f}s', flush=True)

POOL_GRID = [5, 10, 20, 30, 50]
TRAIN_YEARS = 3
OOS_YEARS = [2023, 2024, 2025, 2026]

rows = []
oos_curves = []  # 逐年样本外净值（拼接用）
fixed_curves = []
for oos in OOS_YEARS:
    train_end = pd.Timestamp(f'{oos-1}-12-31')
    train_start = pd.Timestamp(f'{oos-TRAIN_YEARS}-01-01')
    # ---- 训练：选最优池宽 ----
    best_n, best_ret = None, -999
    train_rows = []
    for n in POOL_GRID:
        eq, tr = lb.run_backtest(df, top_n=n, max_levels=5, min_listing_days=0,
                                 start_date=train_start, end_date=train_end)
        ret = eq['equity'].iloc[-1] / 1e6 - 1
        train_rows.append(dict(n=n, ret=ret))
        if ret > best_ret:
            best_n, best_ret = n, ret
    # ---- 样本外：应用 best_n ----
    oos_end = pd.Timestamp('2026-08-25') if oos == 2026 else pd.Timestamp(f'{oos}-12-31')
    eq, tr = lb.run_backtest(df, top_n=best_n, max_levels=5, min_listing_days=0,
                             start_date=pd.Timestamp(f'{oos}-01-01'), end_date=oos_end)
    oos_ret = eq['equity'].iloc[-1] / 1e6 - 1
    oos_curves.append(eq[['date', 'equity']])
    # 固定 Top10 基准
    eqf, trf = lb.run_backtest(df, top_n=10, max_levels=5, min_listing_days=0,
                               start_date=pd.Timestamp(f'{oos}-01-01'), end_date=oos_end)
    fixed_ret = eqf['equity'].iloc[-1] / 1e6 - 1
    fixed_curves.append(eqf[['date', 'equity']])
    print(f'样本外{oos}: 训练最优池宽={best_n}(训练窗收益{best_ret*100:.1f}%) -> 样本外收益{oos_ret*100:.1f}% | 固定Top10基准{fixed_ret*100:.1f}%', flush=True)
    rows.append(dict(样本外年=oos, 训练窗最优池宽=best_n, 训练窗收益_pct=round(best_ret*100,2),
                     样本外收益_pct=round(oos_ret*100,2), 固定Top10基准_pct=round(fixed_ret*100,2)))

sm = pd.DataFrame(rows)
sm.to_csv(os.path.join(PROJECT_ROOT, 'results', 'walkforward_summary.csv'), index=False)
print(sm.to_string(index=False), flush=True)

# 拼接样本外净值，计算累计
def concat_curve(curves, label):
    parts = []
    prev_last = 1.0
    for c in curves:
        c = c.copy()
        c['ret'] = c['equity'] / c['equity'].iloc[0]
        c['equity'] = prev_last * c['ret']
        parts.append(c)
        prev_last = c['equity'].iloc[-1]
    return pd.concat(parts, ignore_index=True)

wfo = concat_curve(oos_curves, 'wf')
wff = concat_curve(fixed_curves, 'fixed')
wfo.to_parquet(os.path.join(PROJECT_ROOT, 'results', 'walkforward_oos.parquet'))
wff.to_parquet(os.path.join(PROJECT_ROOT, 'results', 'walkforward_fixed.parquet'))
print(f'\nWalk-forward累计样本外收益: {wfo.equity.iloc[-1]/1e6-1:.2%}')
print(f'固定Top10累计样本外收益: {wff.equity.iloc[-1]/1e6-1:.2%}')
print('完成', flush=True)

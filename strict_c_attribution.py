"""STRICT_C 纯股票 + 归因 + benchmark"""
import sys, os
import numpy as np, pandas as pd
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, full_stats
from round51_audit import run_fast_multi_v51
from run_strict_c import run_fast_multi_strict_c

days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off = prepare_v51(limit_down_mode='correct', st_mode='pit')
for d in days:
    dd = D[d]
    dd['one_word'] = ((dd['open_'] == dd['high']) & (dd['low'] == dd['close']) & (dd['open_'] == dd['close']))
rng = (0, len(days))

# ---- ETF buy&hold benchmark ----
m = pd.read_parquet(os.path.join(ROOT, 'data', 'etf_513500_merged.parquet'))
m['trade_date'] = pd.to_datetime(m['trade_date'])
m = m.sort_values('trade_date')
m = m[(m['trade_date'] >= pd.Timestamp('2020-01-02')) & (m['trade_date'] <= pd.Timestamp('2026-08-25'))]
bh = m['close'].iloc[-1] / m['close'].iloc[0] - 1
print(f'[Benchmark] 标普500ETF(513500) buy&hold 2020-01-02~2026-08-25: {bh*100:.2f}%')

print('\n================ PURE STOCK (etf_enabled=False) ================')
res = {}
for name, fn in [
    ('STRICT_A', lambda: run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='prev',
        open_fill='limit_conservative', etf_enabled=False, day_range=rng)),
    ('STRICT_B', lambda: run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='close_confirm_next',
        open_fill='limit_conservative', etf_enabled=False, day_range=rng)),
    ('STRICT_C', lambda: run_fast_multi_strict_c(days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', etf_enabled=False, day_range=rng)),
]:
    eq, tr, _ = fn()
    st = full_stats(eq, tr)
    res[name] = dict(stats=st, tr=tr, eq=eq)
    print(f'[PURE {name}] total={st["total"]:.2f}% ann={st["ann"]:.2f}% mdd={st["mdd"]:.2f}% '
          f'sharpe={st["sharpe"]:.2f} trades={st["n"]} wr={st["wr"]:.1f}% stock_pnl={tr["pnl"].sum():,.0f}')

# STRICT_C pure 保存
res['STRICT_C']['tr'].to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_pure_trades.csv'), index=False)
res['STRICT_C']['eq'].to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_pure_equity.csv'), index=False)

print('\n================ 组合 vs 纯股票 (STRICT_C) ================')
eqc, trc, _ = run_fast_multi_strict_c(days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off,
    K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
    slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
    open_fill='limit_conservative', etf_enabled=True, day_range=rng)
stc = full_stats(eqc, trc)
print(f'[COMBO STRICT_C] total={stc["total"]:.2f}% ann={stc["ann"]:.2f}% mdd={stc["mdd"]:.2f}% '
      f'sharpe={stc["sharpe"]:.2f} trades={stc["n"]} wr={stc["wr"]:.1f}% stock_pnl={trc["pnl"].sum():,.0f}')
print(f'[PURE  STRICT_C] total={res["STRICT_C"]["stats"]["total"]:.2f}% stock_pnl={res["STRICT_C"]["tr"]["pnl"].sum():,.0f}')

# ================= 归因: 组合 equity 拆解 =================
# combo 期末: cash + etf_val; pure 期末: cash(无ETF)
# ETF 贡献估算 = combo 期末 equity - pure 期末 equity - (股票交易在combo与pure间相同)
# 更精确: combo 里 ETF PnL = 期末 etf_val - 累计净投入ETF的现金
print('\n================ 归因: 股票 vs ETF ================')
# combo equity curve 逐日 etf_val / stock_val / cash
eqc = eqc.reset_index(drop=True)
last = eqc.iloc[-1]
print(f'combo 期末: equity={last["equity"]:,.0f} cash={last["cash"]:,.0f} etf_val={last["etf_val"]:,.0f}')
# ETF 累计 PnL: 需要累计净买入ETF现金流. 简化: 从 equity 曲线拆分不可行(需逐笔).
# 用 trade PnL: 股票已实现 PnL + ETF 估值变化
stock_pnl_combo = float(trc['pnl'].sum())
init = 1_000_000
ending = float(last['equity'])
# ETF 段贡献 = ending - init - stock_pnl_combo (近似, 未含买卖佣金)
etf_contrib = ending - init - stock_pnl_combo
print(f'股票已实现PnL(combo) = {stock_pnl_combo:,.0f}  占初始资金 {stock_pnl_combo/init*100:.1f}%')
print(f'ETF+现金贡献(含ETF买卖盈亏与费用) = {etf_contrib:,.0f}  占 {etf_contrib/init*100:.1f}%')
print(f'combo 总收益 = {ending/init*100-100:.1f}%')

# 纯股票口径: 资金利用率
pure_last = res['STRICT_C']['eq'].iloc[-1]
print(f'pure 期末 equity={pure_last["equity"]:,.0f} => 纯股票累计 {pure_last["equity"]/init*100-100:.1f}%')

# ================= 归因: exit price / exit date 拆解 =================
print('\n================ 归因: INVALID(same DS) vs STRICT_C 逐笔对比 =================')
tinv = pd.read_csv('/tmp/invalid_same_ds.csv')
tn = tinv[tinv['exit_type'] != 'FINAL_SETTLE']
tc_ = trc[trc['exit_type'] != 'FINAL_SETTLE'].copy()
print(f'INVALID(同口径)  已实现PnL合计: {tn["pnl"].sum():,.0f}  笔数:{len(tn)} 平均:{tn["pnl"].mean():,.0f} 平均持仓:{tn["hold_days"].mean():.1f}天')
print(f'STRICT_C          已实现PnL合计: {tc_["pnl"].sum():,.0f}  笔数:{len(tc_)} 平均:{tc_["pnl"].mean():,.0f} 平均持仓:{tc_["hold_days"].mean():.1f}天')
print(f'  交易数差: {len(tc_)-len(tn)} 笔   PnL差: {tc_["pnl"].sum()-tn["pnl"].sum():,.0f}')
# 盈利分布
for lbl, dfx in [('INVALID', tn), ('STRICT_C', tc_)]:
    w = dfx[dfx['pnl'] > 0]; l_ = dfx[dfx['pnl'] <= 0]
    print(f'  {lbl}: 盈利{len(w)}笔(均{w["pnl"].mean():,.0f}) 亏损{len(l_)}笔(均{l_["pnl"].mean():,.0f}) '
          f'盈亏比={abs(w["pnl"].sum()/l_["pnl"].sum()) if len(l_) and l_["pnl"].sum()!=0 else float("inf"):.2f}')
# exit price 平均差(同日触发部分已算)

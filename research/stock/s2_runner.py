#!/usr/bin/env python3
"""S2 Runner — Amount vs Random Neutral Selection Portfolio Experiment.

1. Prepare data once
2. Run Control (amount) to verify reproduction of official G0 baseline
3. Run N_SIM random simulations
4. Collect summary metrics for all runs
5. Save full trade logs for first 10 seeds
"""
import sys, os, time
import numpy as np
import pandas as pd

ETF_WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
sys.path.insert(0, os.path.join(ETF_WT, 'research', 'stock'))
from s2_engine import run_fast_multi_strict_c_s2, prepare_v51, full_stats

OUT = os.path.join(ETF_WT, 'results', 'stock')
os.makedirs(OUT, exist_ok=True)

BASE_SEED = 42
N_SIM = 200
FULL_TRADE_LOG_SEEDS = 10  # save full trade logs for first 10 seeds

print('='*60)
print('S2 AMOUNT vs RANDOM NEUTRAL SELECTION')
print(f'N_SIM={N_SIM}, BASE_SEED={BASE_SEED}')
print('='*60)

# ===== 1. Prepare data (once) =====
print('\n[1] Preparing data...')
t0 = time.time()
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
# Add one_word field (required by engine infrastructure)
for _d in days:
    _dd = D[_d]
    _dd['one_word'] = ((_dd['open_'] == _dd['high']) & (_dd['low'] == _dd['close'])
                       & (_dd['open_'] == _dd['close']))
print(f'  Data prepared in {time.time()-t0:.1f}s')
print(f'  Days: {len(days)}, from {days[0].date()} to {days[-1].date()}')

def compute_metrics(eq, tr):
    """Compute summary metrics from equity curve and trades."""
    if len(eq) == 0:
        return {}
    eq = eq.copy()
    eq['date'] = pd.to_datetime(eq['date'])
    eq = eq.set_index('date')
    total_ret = eq['equity'].iloc[-1] / eq['equity'].iloc[0] - 1
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (1 + total_ret) ** (1/n_years) - 1 if n_years > 0 else 0
    daily_ret = eq['equity'].pct_change().dropna()
    ann_vol = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 1 else 0
    sharpe = (daily_ret.mean() * 252) / ann_vol if ann_vol > 0 else 0
    cummax = eq['equity'].cummax()
    drawdown = eq['equity'] / cummax - 1
    maxdd = drawdown.min()

    if len(tr) > 0:
        n_trades = len(tr)
        wins = tr[tr['pnl'] > 0]
        losses = tr[tr['pnl'] <= 0]
        win_rate = len(wins) / n_trades
        gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        avg_winner = wins['pnl'].mean() if len(wins) > 0 else 0
        avg_loser = losses['pnl'].mean() if len(losses) > 0 else 0
        payoff = abs(avg_winner / avg_loser) if avg_loser != 0 else float('inf')
        avg_hold = tr['hold_days'].mean()
        avg_exposure = (eq['stock_val'] / eq['equity']).mean()
    else:
        n_trades = 0; win_rate = 0; pf = 0; payoff = 0
        avg_hold = 0; avg_exposure = 0

    return {
        'total_return_pct': round(total_ret * 100, 3),
        'cagr_pct': round(cagr * 100, 3),
        'sharpe': round(sharpe, 4),
        'maxdd_pct': round(maxdd * 100, 3),
        'n_trades': n_trades,
        'win_rate_pct': round(win_rate * 100, 2),
        'profit_factor': round(pf, 4),
        'payoff_ratio': round(payoff, 4),
        'avg_holding_days': round(avg_hold, 1),
        'avg_exposure_pct': round(avg_exposure * 100, 2),
    }

# ===== 2. Control (amount) =====
print('\n[2] Running Control (amount selection)...')
t0 = time.time()
eq_ctrl, tr_ctrl = run_fast_multi_strict_c_s2(
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
    K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
    slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
    open_fill='limit_conservative', selection_mode='amount', seed=BASE_SEED)
ctrl_time = time.time() - t0
ctrl_metrics = compute_metrics(eq_ctrl, tr_ctrl)
print(f'  Control done in {ctrl_time:.1f}s')
print(f'  Total Return: {ctrl_metrics["total_return_pct"]}%')
print(f'  Trades: {ctrl_metrics["n_trades"]}')
print(f'  Win Rate: {ctrl_metrics["win_rate_pct"]}%')
print(f'  PF: {ctrl_metrics["profit_factor"]}')
print(f'  MaxDD: {ctrl_metrics["maxdd_pct"]}%')
print(f'  Sharpe: {ctrl_metrics["sharpe"]}')

# Official G0 baseline: +30.30%, 76 trades, WR 68.4%, PF 1.304
print(f'\n  Official G0: TR +30.30%, 76 trades, WR 68.4%, PF 1.304, MaxDD -30.79%')
print(f'  Control:     TR {ctrl_metrics["total_return_pct"]}%, {ctrl_metrics["n_trades"]} trades, WR {ctrl_metrics["win_rate_pct"]}%, PF {ctrl_metrics["profit_factor"]}, MaxDD {ctrl_metrics["maxdd_pct"]}%')

# Save control trade log
tr_ctrl.to_csv(os.path.join(OUT, 's2_control_trades.csv'), index=False)
pd.DataFrame([ctrl_metrics]).to_csv(os.path.join(OUT, 's2_control_summary.csv'), index=False)

# ===== 3. Random simulations =====
print(f'\n[3] Running {N_SIM} random simulations...')
est_total = ctrl_time * N_SIM
print(f'  Estimated total time: {est_total/60:.1f} minutes ({est_total:.0f}s)')

all_results = []
for sim_id in range(N_SIM):
    seed = BASE_SEED + sim_id
    t1 = time.time()
    eq_r, tr_r = run_fast_multi_strict_c_s2(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', selection_mode='random', seed=seed)
    m = compute_metrics(eq_r, tr_r)
    m['sim_id'] = sim_id
    m['seed'] = seed
    all_results.append(m)

    # Save full trade log for first N seeds
    if sim_id < FULL_TRADE_LOG_SEEDS:
        tr_r.to_csv(os.path.join(OUT, f's2_random_trades_seed{seed}.csv'), index=False)

    if (sim_id + 1) % 20 == 0 or sim_id == 0:
        elapsed = time.time() - t0
        rate = (sim_id + 1) / elapsed
        eta = (N_SIM - sim_id - 1) / rate
        print(f'  [{sim_id+1}/{N_SIM}] seed={seed} TR={m["total_return_pct"]}% PF={m["profit_factor"]} '
              f'trades={m["n_trades"]} elapsed={elapsed:.0f}s ETA={eta:.0f}s')

results_df = pd.DataFrame(all_results)
results_df.to_csv(os.path.join(OUT, 's2_random_portfolio_distribution.csv'), index=False)
print(f'\n  All {N_SIM} simulations complete.')

# ===== 4. Control percentiles =====
print('\n[4] Computing Control percentiles in random distribution...')
percentile_rows = []
for metric in ['total_return_pct', 'sharpe', 'maxdd_pct', 'profit_factor', 'win_rate_pct', 'n_trades']:
    rand_vals = results_df[metric].values
    ctrl_val = ctrl_metrics[metric]
    # For maxdd, higher (less negative) is better
    if metric == 'maxdd_pct':
        pct = (rand_vals <= ctrl_val).mean() * 100  # % random worse than control
        p_random_better = (rand_vals > ctrl_val).mean() * 100
    else:
        pct = (rand_vals <= ctrl_val).mean() * 100
        p_random_better = (rand_vals > ctrl_val).mean() * 100
    percentile_rows.append({
        'metric': metric,
        'control_value': ctrl_val,
        'random_median': round(np.median(rand_vals), 4),
        'random_mean': round(np.mean(rand_vals), 4),
        'random_p5': round(np.percentile(rand_vals, 5), 4),
        'random_p25': round(np.percentile(rand_vals, 25), 4),
        'random_p75': round(np.percentile(rand_vals, 75), 4),
        'random_p95': round(np.percentile(rand_vals, 95), 4),
        'control_percentile': round(pct, 1),
        'p_random_better_pct': round(p_random_better, 1),
    })
pct_df = pd.DataFrame(percentile_rows)
print(pct_df[['metric','control_value','random_median','control_percentile','p_random_better_pct']].to_string(index=False))
pct_df.to_csv(os.path.join(OUT, 's2_control_percentiles.csv'), index=False)

# Summary
summary = {
    'control_tr': ctrl_metrics['total_return_pct'],
    'control_pf': ctrl_metrics['profit_factor'],
    'random_median_tr': round(results_df['total_return_pct'].median(), 3),
    'random_mean_tr': round(results_df['total_return_pct'].mean(), 3),
    'random_median_pf': round(results_df['profit_factor'].median(), 4),
    'p_random_tr_better': round((results_df['total_return_pct'] > ctrl_metrics['total_return_pct']).mean()*100, 1),
    'p_random_pf_better': round((results_df['profit_factor'] > ctrl_metrics['profit_factor']).mean()*100, 1),
    'control_tr_percentile': round((results_df['total_return_pct'] <= ctrl_metrics['total_return_pct']).mean()*100, 1),
    'n_sim': N_SIM,
}
pd.DataFrame([summary]).to_csv(os.path.join(OUT, 's2_random_vs_amount_summary.csv'), index=False)
print(f'\n  SUMMARY:')
print(f'  Control TR: {summary["control_tr"]}%, PF: {summary["control_pf"]}')
print(f'  Random median TR: {summary["random_median_tr"]}%, PF: {summary["random_median_pf"]}')
print(f'  P(random TR > Control): {summary["p_random_tr_better"]}%')
print(f'  P(random PF > Control): {summary["p_random_pf_better"]}%')
print(f'  Control TR percentile: {summary["control_tr_percentile"]}%')

print('\nS2 portfolio experiment complete.')

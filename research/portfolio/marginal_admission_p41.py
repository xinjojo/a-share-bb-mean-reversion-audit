#!/usr/bin/env python3
"""
PHASE P4.1 - MARGINAL ADMISSION / CAPACITY SHADOW-PRICE AUDIT

Question: relaxing K=3 (A1: K=999) raises signal capture but collapses portfolio
(A0 +30.30% vs A1 -0.23%). Why?
  H1. marginal admitted signals intrinsically worse
  H2. signals similar but enter under worse portfolio/capital states
  H3. signals retain independent edge, but shared-capital path / position dilution
      destroys portfolio value
  H4. combination

Frozen:
  A0 (K=3 ML=5) and A1 (K=999 ML=5) from P4 frozen engine (amount-top10, PURE STOCK
  2020-2024, 1M/200k/5layers, 10bp, STRICT_C_EXECUTABLE_TICK). A0 parity asserted.
  Trade key primary = (ts_code, entry_date); secondary = ts_code-only.
  Independent join = frozen SECONDARY V2A episodes by (signal_date, ts_code) exact
  key; NO_EXACT_EPISODE otherwise. No future re-signal substitution.
  Event-day aggregation + circular block bootstrap L=21 B>=2000.
  Market overlay: R01 (ALL_A_EW_RET60, neg) & R05 (LIMIT_DOWN_SHARE) descriptive only.
  2025-2026 Confirmation CLOSED.

Preregistered BEFORE any outcome run:
  research/portfolio/registries/MARGINAL_ADMISSION_P41_REGISTRY.csv
  SHA256 = 6efc564f4cee1ba094ed3ef0510e48acb882c6ded0b388b8a353924cc3d6efed
  commit c6c2865f4c2d20b05a8b312390f8e4c7caa9b2c7 (P4.1-A, pushed)
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'p41')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, 'research', 'portfolio'))

# --- registry gate (hard red line) ---
REG = os.path.join(REPO, 'research', 'portfolio', 'registries', 'MARGINAL_ADMISSION_P41_REGISTRY.csv')
REG_SHA = '6efc564f4cee1ba094ed3ef0510e48acb882c6ded0b388b8a353924cc3d6efed'
with open(REG, 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
assert h == REG_SHA, f'REGISTRY SHA MISMATCH: {h}'
print(f'[gate] registry SHA256 verified: {h}')

from portfolio_architecture_p4 import run_fast_multi_strict_c_atr, portfolio_metrics, yearly_returns
from round51_audit import prepare_v51
sys.path.insert(0, os.path.join(REPO, 'research'))
from market_state.market_state_phase_t2 import load_features, assemble_day_frame

RNG = np.random.default_rng(20260903)
BLOCK_L, BLOCK_B = 21, 2000
DEV_END = pd.Timestamp('2024-12-31')
G0_REF = dict(total=30.295093786122408, ann=5.65643037176935, mdd=-30.78972881784398,
             sharpe=0.3467648252149691, n=76, stock_pnl=302950.9378612245)

def circ_blocks(n, L, B):
    kb = int(np.ceil(n / L))
    starts = RNG.integers(0, n, size=(B, kb))
    offs = np.arange(L)[None, :]
    idx = (starts[:, :, None] + offs) % n
    idx = idx.reshape(B, kb * L)[:, :n]
    return idx

def main():
    # ---------------- frozen paths A0 / A1 ----------------
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    N2024 = sum(1 for d in days if d <= DEV_END)
    print(f'[engine] n_days={len(days)} N2024={N2024} last-dev={days[N2024-1]}', flush=True)

    res = {}
    for label, K in [('A0', 3), ('A1', 999)]:
        ledger, cand_log, day_log, exec_log = [], [], [], []
        eq, tr, ac = run_fast_multi_strict_c_atr(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=K, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, N2024), record_actions=True,
            entry_rank_mode='amount_top10', atr_lookup=None, ledger=ledger, cand_log=cand_log,
            day_log=day_log, exec_log=exec_log)
        res[label] = dict(eq=eq, tr=tr, ac=ac, ledger=ledger, cand_log=cand_log,
                          day_log=day_log, exec_log=exec_log,
                          stock_pnl=float(tr['pnl'].sum()), slot_occ=float(eq['n_pos'].sum()),
                          cap_days=float(eq['invested'].sum()))
        print(f'[PORT {label}] K={K} trades={len(tr)} stock_pnl={res[label]["stock_pnl"]:,.2f}', flush=True)

    # ---- A0 parity assert ----
    m0 = portfolio_metrics(res['A0']['eq'], res['A0']['tr'])
    ok = (abs(m0['total'] - G0_REF['total']) < 1e-6 and abs(m0['ann'] - G0_REF['ann']) < 1e-6
          and abs(m0['mdd'] - G0_REF['mdd']) < 1e-6 and abs(m0['sharpe'] - G0_REF['sharpe']) < 1e-6
          and len(res['A0']['tr']) == G0_REF['n'] and abs(res['A0']['stock_pnl'] - G0_REF['stock_pnl']) < 1e-4)
    print(f'[PARITY A0] OK={ok} total={m0["total"]:.6f} n={len(res["A0"]["tr"])} pnl={res["A0"]["stock_pnl"]:.4f}')
    assert ok, 'A0 PARITY FAIL - P0 STOP'

    trA0 = res['A0']['tr'].copy(); trA1 = res['A1']['tr'].copy()
    for df_ in (trA0, trA1):
        df_['entry_date'] = pd.to_datetime(df_['entry_date'])
        df_['sig_date'] = pd.to_datetime(df_['sig_date'])

    # ---------------- trade groups (primary key = ts_code, entry_date) ----------------
    kA0 = set(zip(trA0['ts_code'], trA0['entry_date']))
    kA1 = set(zip(trA1['ts_code'], trA1['entry_date']))
    common = kA0 & kA1
    a0_only = kA0 - kA1
    a1_only = kA1 - kA0
    def tag(df_, keys, name):
        df_['group'] = df_.apply(lambda r: name if (r['ts_code'], r['entry_date']) in keys else 'OTHER', axis=1)
    tag(trA0, common | a0_only, 'A0'); tag(trA1, common | a1_only, 'A1')
    trA0['group'] = trA0.apply(lambda r: 'COMMON' if (r['ts_code'], r['entry_date']) in common else 'A0_ONLY', axis=1)
    trA1['group'] = trA1.apply(lambda r: 'COMMON' if (r['ts_code'], r['entry_date']) in common else 'A1_ONLY', axis=1)
    # ts_code-only overlap (secondary)
    c0 = set(trA0['ts_code']); c1 = set(trA1['ts_code'])

    groups = pd.DataFrame([
        dict(group='COMMON', n=len(common)),
        dict(group='A0_ONLY', n=len(a0_only)),
        dict(group='A1_ONLY', n=len(a1_only)),
        dict(group='ts_code_common', n=len(c0 & c1)),
        dict(group='ts_code_A0_only', n=len(c0 - c1)),
        dict(group='ts_code_A1_only', n=len(c1 - c0))])
    groups.to_csv(os.path.join(OUT, 'p41_trade_groups.csv'), index=False)
    print(groups.to_string(index=False))

    # ---------------- independent episode join (frozen SECONDARY V2A) ----------------
    fm = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    fm['entry_date'] = pd.to_datetime(fm['entry_date'])
    fm_dev = fm[fm['signal_date'] <= DEV_END]
    fm_lookup = dict(zip(zip(fm_dev['signal_date'], fm_dev['ts_code']),
                         zip(fm_dev['simple_return_pct'], fm_dev['hold_days'], fm_dev['MAE_close_pct'],
                             fm_dev['MFE_close_pct'], fm_dev['levels_used'], fm_dev['entry_date'],
                             fm_dev['exit_date'], fm_dev['exit_type'])))
    cov_rows = []
    for label in ('A0', 'A1'):
        df_ = trA0 if label == 'A0' else trA1
        hit = df_.apply(lambda r: (r['sig_date'], r['ts_code']) in fm_lookup, axis=1)
        cov_rows.append(dict(arch=label, n=len(df_), covered=int(hit.sum()),
                             coverage_pct=round(float(hit.mean() * 100), 1)))
    pd.DataFrame(cov_rows).to_csv(os.path.join(OUT, 'p41_independent_coverage.csv'), index=False)
    print(pd.DataFrame(cov_rows).to_string(index=False))

    # group-level coverage + independent quality
    iq_rows = []
    for label, df_ in [('A0', trA0), ('A1', trA1)]:
        for g in ('COMMON', 'A0_ONLY' if label == 'A0' else 'A1_ONLY'):
            sub = df_[df_['group'] == g]
            hit = sub.apply(lambda r: (r['sig_date'], r['ts_code']) in fm_lookup, axis=1)
            ind = sub[hit].apply(lambda r: fm_lookup[(r['sig_date'], r['ts_code'])][0], axis=1)
            n_cov = int(hit.sum())
            iq_rows.append(dict(arch=label, group=g, n=len(sub), n_covered=n_cov,
                                cov_pct=round(float(hit.mean() * 100), 1),
                                ind_mean=round(float(ind.mean()), 2) if n_cov else np.nan,
                                ind_median=round(float(ind.median()), 2) if n_cov else np.nan,
                                ind_win=round(float((ind > 0).mean() * 100), 1) if n_cov else np.nan,
                                pf=round(float(ind[ind > 0].sum() / abs(ind[ind < 0].sum())), 3) if n_cov and (ind < 0).any() and (ind > 0).any() else np.nan))
    pd.DataFrame(iq_rows).to_csv(os.path.join(OUT, 'p41_independent_quality.csv'), index=False)
    print(pd.DataFrame(iq_rows).to_string(index=False))

    # ---- event-day aggregation + block bootstrap of A1_ONLY vs COMMON ----
    # For each A1 trade, map to its signal-date; event-day = signal date of trade.
    # Build per-signal-date mean independent return for COMMON and A1_ONLY (A1 arch).
    def eventday_series(df_, g):
        sub = df_[df_['group'] == g]
        hit = sub.apply(lambda r: (r['sig_date'], r['ts_code']) in fm_lookup, axis=1)
        s = sub[hit].copy()
        s['ret'] = s.apply(lambda r: fm_lookup[(r['sig_date'], r['ts_code'])][0], axis=1)
        return s.groupby('sig_date')['ret'].mean()
    ed_common = eventday_series(trA1, 'COMMON')   # same trades exist in A0 but use A1 rows (identical key)
    ed_a1only = eventday_series(trA1, 'A1_ONLY')
    ed_a0only = eventday_series(trA0, 'A0_ONLY')
    ed_all = pd.concat([
        pd.DataFrame(dict(ret=ed_common, grp='COMMON')),
        pd.DataFrame(dict(ret=ed_a1only, grp='A1_ONLY')),
        pd.DataFrame(dict(ret=ed_a0only, grp='A0_ONLY'))]).dropna()
    ev_rows = ed_all.groupby('grp')['ret'].agg(n='size', mean='mean', median='median',
                                               win=lambda s: (s > 0).mean() * 100)
    ev_rows.to_csv(os.path.join(OUT, 'p41_independent_eventday.csv'))
    print('--- event-day ---'); print(ev_rows.to_string())

    # block bootstrap: A1_ONLY minus COMMON mean (event-day level)
    x_c = ed_common.to_numpy(); x_a = ed_a1only.to_numpy()
    if len(x_a) >= 3 and len(x_c) >= 3:
        nc, na = len(x_c), len(x_a)
        ic_ = circ_blocks(nc, BLOCK_L, BLOCK_B); ia_ = circ_blocks(na, BLOCK_L, BLOCK_B)
        diff = x_a[ia_].mean(axis=1) - x_c[ic_].mean(axis=1)
        bs_rows = pd.DataFrame(dict(
            stat=['A1_ONLY minus COMMON event-day mean'],
            point=[float(x_a.mean() - x_c.mean())],
            bs_mean=[float(diff.mean())],
            ci_lo=[float(np.percentile(diff, 2.5))], ci_hi=[float(np.percentile(diff, 97.5))],
            pct_positive=[float((diff > 0).mean() * 100)]))
        bs_rows.to_csv(os.path.join(OUT, 'p41_independent_bootstrap.csv'), index=False)
        print(bs_rows.to_string(index=False))

    # ---------------- A1_ONLY actual portfolio PnL ----------------
    a1only_act = trA1[trA1['group'] == 'A1_ONLY']
    a1_act = pd.DataFrame(dict(
        n=[len(a1only_act)], sum_pnl=[round(float(a1only_act['pnl'].sum()), 2)],
        mean_pnl=[round(float(a1only_act['pnl'].mean()), 2)],
        median_pnl=[round(float(a1only_act['pnl'].median()), 2)],
        win_rate=[round(float((a1only_act['pnl'] > 0).mean() * 100), 1)],
        mean_hold=[round(float(a1only_act['hold_days'].mean()), 1)],
        mean_levels=[round(float(a1only_act['levels_used'].mean()), 2)]))
    a1_act.to_csv(os.path.join(OUT, 'p41_a1only_actual.csv'), index=False)
    print('--- A1_ONLY actual portfolio ---'); print(a1_act.to_string(index=False))

    # ---------------- admission-state snapshot for A1 entries ----------------
    # reconstruct per-day A1 state from equity curve (date-indexed) for the signal date
    eqA1 = res['A1']['eq'].set_index('date')
    eqA0 = res['A0']['eq'].set_index('date')
    cand_df = pd.DataFrame(res['A1']['cand_log']) if res['A1']['cand_log'] else pd.DataFrame()
    ld_df = pd.DataFrame(res['A1']['ledger']) if res['A1']['ledger'] else pd.DataFrame()
    ad_rows = []
    eqA1['dstr'] = eqA1.index.astype(str)
    eqA0['dstr'] = eqA0.index.astype(str)
    for _, t in trA1.iterrows():
        sd = t['sig_date']
        sdstr = str(sd.date())
        if sdstr not in set(eqA1['dstr']):
            continue
        stA1 = eqA1[eqA1['dstr'] == sdstr].iloc[0]
        stA0 = eqA0[eqA0['dstr'] == sdstr].iloc[0] if sdstr in set(eqA0['dstr']) else None
        cand_n = int((cand_df['sig_date'] == sdstr).sum()) if len(cand_df) else 0
        ad_rows.append(dict(
            ts_code=t['ts_code'], sig_date=sdstr, entry_date=str(t['entry_date']),
            cash_A1=float(stA1['cash']), invested_A1=float(stA1['invested']),
            npos_A1=int(stA1['n_pos']), layers_A1=int(t['levels_used']), hold_A1=int(t['hold_days']),
            av_cash_layer=float(stA1['cash'] / 200000),
            npos_A0=int(stA0['n_pos']) if stA0 is not None else np.nan))
    adf = pd.DataFrame(ad_rows)
    adf.to_csv(os.path.join(OUT, 'p41_admission_state.csv'), index=False)

    # ---------------- marginal rank (amount-priority rank among that day's candidates) ----------------
    mr_rows = []
    if len(cand_df):
        cand_df['sig_date'] = pd.to_datetime(cand_df['sig_date'])
        cand_df = cand_df.sort_values(['sig_date', 'amount_rank'])
        cand_df['marginal_rank'] = cand_df.groupby('sig_date').cumcount() + 1
        # join to A1 trades
        t1 = trA1.copy(); t1['sig_date'] = pd.to_datetime(t1['sig_date'])
        merged = t1.merge(cand_df[['sig_date', 'ts_code', 'amount_rank', 'marginal_rank']],
                          on=['sig_date', 'ts_code'], how='left')
        merged['ret'] = merged.apply(lambda r: fm_lookup[(r['sig_date'], r['ts_code'])][0]
                                     if (r['sig_date'], r['ts_code']) in fm_lookup else np.nan, axis=1)
        for bucket in ['marginal_rank']:
            g = merged.groupby(bucket)['ret'].agg(n='size', mean='mean', median='median',
                                                  win=lambda s: (s > 0).mean() * 100)
            for q, row in g.iterrows():
                mr_rows.append(dict(metric=bucket, value=int(q), n=int(row['n']),
                                    ind_mean=round(float(row['mean']), 2) if pd.notna(row['mean']) else np.nan,
                                    ind_win=round(float(row['win']), 1) if pd.notna(row['win']) else np.nan))
    pd.DataFrame(mr_rows).to_csv(os.path.join(OUT, 'p41_marginal_rank.csv'), index=False)

    # ---------------- congestion state (pre-fixed bins) ----------------
    cong_rows = []
    # candidate_count buckets (pre-fixed bins: 1 / 2 / 3+) and A0 n_pos distribution
    dl_df = pd.DataFrame(res['A1']['day_log']) if res['A1']['day_log'] else pd.DataFrame()
    if len(dl_df):
        dl_df['date'] = pd.to_datetime(dl_df['date'])
        dl_df['cc_bin'] = pd.cut(dl_df['queueable_candidates'], [-1, 1, 2, 1e9], labels=['1', '2', '3+'])
        for b, sub in dl_df.groupby('cc_bin', observed=True):
            cong_rows.append(dict(metric='queueable_candidates', bucket=str(b), days=len(sub)))
    pd.DataFrame(cong_rows).to_csv(os.path.join(OUT, 'p41_congestion.csv'), index=False)

    # ---------------- COMMON matched capital dilution ----------------
    k2 = {}
    for df_ in (trA0, trA1):
        for _, r in df_.iterrows():
            k2[(r['ts_code'], r['entry_date'])] = df_
    cm_rows = []
    for key in sorted(common):
        r0 = trA0[(trA0['ts_code'] == key[0]) & (trA0['entry_date'] == key[1])].iloc[0]
        r1 = trA1[(trA1['ts_code'] == key[0]) & (trA1['entry_date'] == key[1])].iloc[0]
        cm_rows.append(dict(
            ts_code=key[0], entry_date=str(key[1]),
            levels0=int(r0['levels_used']), levels1=int(r1['levels_used']),
            shares0=int(r0['shares']), shares1=int(r1['shares']),
            pnl0=round(float(r0['pnl']), 2), pnl1=round(float(r1['pnl']), 2),
            delta_pnl=round(float(r1['pnl'] - r0['pnl']), 2),
            hold0=int(r0['hold_days']), hold1=int(r1['hold_days']),
            ret0=float(r0['return_pct']), ret1=float(r1['return_pct']),
            same_exit=(r0['exit_date'] == r1['exit_date']),
            same_levels=(r0['levels_used'] == r1['levels_used'])))
    cm_df = pd.DataFrame(cm_rows)
    cm_sum = pd.DataFrame(dict(
        metric=['COMMON n', 'mean delta_pnl', 'median delta_pnl', 'mean delta_levels',
                'mean delta_hold', 'same_exit_share', 'same_levels_share'],
        value=[len(cm_df), round(float(cm_df['delta_pnl'].mean()), 2),
               round(float(cm_df['delta_pnl'].median()), 2),
               round(float((cm_df['levels1'] - cm_df['levels0']).mean()), 3),
               round(float((cm_df['hold1'] - cm_df['hold0']).mean()), 3),
               round(float(cm_df['same_exit'].mean()), 3),
               round(float(cm_df['same_levels'].mean()), 3)]))
    cm_df.to_csv(os.path.join(OUT, 'p41_common_matched.csv'), index=False)
    cm_sum.to_csv(os.path.join(OUT, 'p41_common_matched_summary.csv'), index=False)
    print('--- COMMON matched summary ---'); print(cm_sum.to_string(index=False))

    # ---------------- PnL bridge (exact accounting) ----------------
    pnlA0 = float(trA0['pnl'].sum()); pnlA1 = float(trA1['pnl'].sum())
    comm_pnl0 = float(trA0[trA0['group'] == 'COMMON']['pnl'].sum())
    comm_pnl1 = float(trA1[trA1['group'] == 'COMMON']['pnl'].sum())
    a0only_pnl = float(trA0[trA0['group'] == 'A0_ONLY']['pnl'].sum())
    a1only_pnl = float(trA1[trA1['group'] == 'A1_ONLY']['pnl'].sum())
    residual = pnlA1 - (comm_pnl1 + a1only_pnl)
    bridge = pd.DataFrame(dict(
        component=['A0 stock pnl', 'COMMON A0 pnl', 'COMMON A1 pnl', 'COMMON delta',
                   'A0_ONLY pnl', 'A1_ONLY pnl', 'A1 stock pnl (recomputed)',
                   'A0_ONLY contribution to bridge (A1 - A0)', 'residual (A1 - comm - a1only)'],
        value=[round(pnlA0, 2), round(comm_pnl0, 2), round(comm_pnl1, 2),
               round(comm_pnl1 - comm_pnl0, 2), round(a0only_pnl, 2), round(a1only_pnl, 2),
               round(comm_pnl1 + a1only_pnl, 2), round(-a0only_pnl, 2), round(residual, 4)]))
    bridge.to_csv(os.path.join(OUT, 'p41_pnl_bridge.csv'), index=False)
    print('--- PnL bridge ---'); print(bridge.to_string(index=False))
    assert abs(residual) < 1e-4, f'P0 STOP: PnL bridge residual {residual} != 0'

    # ---------------- temporal concentration of A1_ONLY ----------------
    a1o = trA1[trA1['group'] == 'A1_ONLY'].copy()
    a1o['year'] = a1o['sig_date'].dt.year
    a1o['month'] = a1o['sig_date'].dt.strftime('%Y-%m')
    date_share = a1o['sig_date'].dt.strftime('%Y-%m-%d').value_counts(normalize=True).sort_values(ascending=False)
    tc_rows = [dict(metric='A1_ONLY n', value=int(len(a1o))),
               dict(metric='top5 dates share', value=round(float(date_share.head(5).sum()), 3)),
               dict(metric='top10 dates share', value=round(float(date_share.head(10).sum()), 3)),
               dict(metric='n distinct signal dates', value=int(a1o['sig_date'].nunique()))]
    by_year = a1o.groupby('year')['pnl'].agg(n='size', sum='sum')
    for y, r in by_year.iterrows():
        tc_rows.append(dict(metric=f'year {y} pnl', value=round(float(r['sum']), 0)))
    pd.DataFrame(tc_rows).to_csv(os.path.join(OUT, 'p41_temporal_concentration.csv'), index=False)
    print('--- A1_ONLY temporal ---'); print(pd.DataFrame(tc_rows).to_string(index=False))

    # ---------------- market-state overlay (R01 / R05, descriptive) ----------------
    day_feats, days, offset = load_features()
    ix = assemble_day_frame(day_feats, days)
    ix = ix[ix.index <= DEV_END]
    for lbl, col in [('R01_ret60', 'ret60_ea'), ('R05_limitdown', 'limit_down')]:
        if lbl not in ix.columns:
            ix[lbl] = ix[col]
    overlay_rows = []
    for g, df_ in [('COMMON', trA1[trA1['group'] == 'COMMON']),
                   ('A1_ONLY', trA1[trA1['group'] == 'A1_ONLY']),
                   ('A0_ONLY', trA0[trA0['group'] == 'A0_ONLY'])]:
        s = df_.merge(ix[['ret60_ea', 'limit_down']], left_on='sig_date', right_index=True, how='left')
        overlay_rows.append(dict(group=g, n=len(s),
                                 r01_mean=round(float(s['ret60_ea'].mean()), 2),
                                 r01_p75=round(float(s['ret60_ea'].quantile(0.75)), 2),
                                 r05_gt0=round(float((s['limit_down'] > 0).mean() * 100), 1)))
    pd.DataFrame(overlay_rows).to_csv(os.path.join(OUT, 'p41_market_state_overlay.csv'), index=False)
    print('--- market overlay ---'); print(pd.DataFrame(overlay_rows).to_string(index=False))

    # ---------------- MAE / holding burden ----------------
    mh_rows = []
    for g, df_ in [('COMMON', trA1[trA1['group'] == 'COMMON']),
                   ('A1_ONLY', trA1[trA1['group'] == 'A1_ONLY']),
                   ('A0_ONLY', trA0[trA0['group'] == 'A0_ONLY'])]:
        hit = df_.apply(lambda r: (r['sig_date'], r['ts_code']) in fm_lookup, axis=1)
        sub = df_[hit]
        sub['mae'] = sub.apply(lambda r: fm_lookup[(r['sig_date'], r['ts_code'])][2], axis=1)
        sub['ind_hold'] = sub.apply(lambda r: fm_lookup[(r['sig_date'], r['ts_code'])][1], axis=1)
        mh_rows.append(dict(group=g, n=len(df_), n_covered=len(sub),
                            deep_mae_rate=round(float((sub['mae'] <= -20).mean() * 100), 1),
                            mean_mae=round(float(sub['mae'].mean()), 2),
                            mean_hold_actual=round(float(df_['hold_days'].mean()), 1),
                            mean_levels=round(float(df_['levels_used'].mean()), 2),
                            mean_ind_hold=round(float(sub['ind_hold'].mean()), 1) if len(sub) else np.nan,
                            slot_days=round(float(df_['hold_days'].sum()), 0),
                            total_pnl=round(float(df_['pnl'].sum()), 0)))
    pd.DataFrame(mh_rows).to_csv(os.path.join(OUT, 'p41_mae_holding.csv'), index=False)
    print('--- MAE / holding ---'); print(pd.DataFrame(mh_rows).to_string(index=False))

    # ---------------- capacity shadow price ----------------
    n_extra = len(trA1) - len(trA0)
    slot_extra = res['A1']['slot_occ'] - res['A0']['slot_occ']
    cap_extra = res['A1']['cap_days'] - res['A0']['cap_days']
    shadow = pd.DataFrame(dict(
        metric=['pnl delta (A1 - A0)', 'extra executed trades', 'extra slot-days', 'extra capital-days',
                'shadow pnl per extra trade', 'shadow pnl per extra slot-day', 'shadow pnl per extra capital-day'],
        value=[round(pnlA1 - pnlA0, 2), int(n_extra), round(float(slot_extra), 0),
               round(float(cap_extra), 0),
               round(float((pnlA1 - pnlA0) / n_extra), 2) if n_extra else np.nan,
               round(float((pnlA1 - pnlA0) / slot_extra), 2) if slot_extra else np.nan,
               round(float((pnlA1 - pnlA0) / cap_extra), 6) if cap_extra else np.nan]))
    shadow.to_csv(os.path.join(OUT, 'p41_capacity_shadow.csv'), index=False)
    print('--- capacity shadow price ---'); print(shadow.to_string(index=False))

    # ---------------- summary json ----------------
    summary = dict(
        a0=dict(total=float(m0['total']), n=len(trA0), pnl=float(pnlA0)),
        a1=dict(total=float((res['A1']['eq']['equity'].iloc[-1] / 1e6 - 1) * 100), n=len(trA1), pnl=float(pnlA1)),
        groups=dict(common=len(common), a0_only=len(a0_only), a1_only=len(a1_only)),
        bridge_residual=float(residual),
        a1only_actual_pnl=float(a1only_pnl),
        a0only_pnl=float(a0only_pnl),
        common_delta_pnl=float(comm_pnl1 - comm_pnl0),
        parity_ok=bool(ok))
    with open(os.path.join(OUT, 'p41_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print('[DONE] P4.1 outputs written to', OUT)

if __name__ == '__main__':
    main()

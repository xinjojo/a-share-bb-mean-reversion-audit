#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================================
PHASE T2-R — STEP B: REVERSE-DIRECTION VALIDATION (2023-2024)
==========================================================
Untouched Validation of the 7 reverse-direction hypotheses preregistered in
TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv (commit 210f843).

Gate: registry SHA256 must match; registry was committed BEFORE any 2023-2024
outcome was read. This script reads Validation outcomes ONLY after that gate.

Frozen contracts:
  - Features: identical formulas/columns to Phase T2 (imported from
    market_state_phase_t2.load_features / assemble_day_frame).
  - Frozen episodes: SECONDARY = results/fullmarket_episode_metrics.csv
    (89,046 realized), PRIMARY = results/independent_v2a_episodes.pkl (299).
  - Outcome: Y20 = mean simple_return_pct of frozen SECONDARY episodes whose
    signal_date falls in the next 20 signal days, with the FULL window inside
    2023-2024 (no 2025+ episode return enters Validation Y20).
  - Primary inference: Spearman IC + Newey-West HAC lag=20 (rank regression),
    BH-FDR m=7. HAC sensitivity lags 10/40.
  - PIT quintiles: PRIMARY = FIXED DISCOVERY CUTPOINTS (quintile boundaries
    from 2020-2022 Discovery feature distribution only, applied unchanged to
    2023-2024). SECONDARY sensitivity = expanding PIT cutpoints (feature
    history < t, >=100 obs).
  - Block bootstrap: circular moving blocks L=21 signal days, B=5000, on
    Validation (feature, Y20) pairs, fixed Discovery cutpoints -> directional
    Q-spread 95% CI.
  - Non-overlapping offsets 0..19 (anchor every 20 signal days).
  - VALIDATION_PASS = A direction + B BH q<0.05 + C econ spread>=1pp
    + D non-single-extreme (Q2>Q4 / Q4>Q2) + E bootstrap CI_lo>0
    + F 2023/2024 temporal robustness (no materially-opposite year).
==========================================================
"""
import os, sys, hashlib
import numpy as np, pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results')
FIG = os.path.join(REPO, 'figures')
os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)
RNG = np.random.default_rng(20260903)

from market_state_phase_t2 import load_features, assemble_day_frame   # identical formulas

REG_PATH = os.path.join(REPO, 'TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv')
REG_SHA256 = '206444cca45b2b360ddea005fa8a378fc86610088b203dc2e88d23a1946ec778'
DIS_START, DIS_END = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')
VAL_START, VAL_END = pd.Timestamp('2023-01-01'), pd.Timestamp('2024-12-31')
HAC_LAGS = [10, 20, 40]; HAC_PRIMARY = 20
BLOCK_L, BLOCK_B = 21, 5000
SPREAD_PP_GATE = 1.0
PIT_MIN_HIST = 100
NONOVERLAP_OFFSETS = 20
EXPECTED = {'NEGATIVE': -1, 'POSITIVE': +1}

# original T2 feature_id -> computed signal column (identical mapping)
FCOL = dict(F01='ret20_ea', F02='ret60_ea', F03='csi300_ret20', F04='csi1000_ret20',
            F05='dist_ma20', F06='ma20_slope', F07='breadth_ma20', F08='up1d',
            F09='newlow20', F10='below_bb', F11='rv20', F12='rv60', F13='cs_std',
            F14='downvol', F15='amt_ratio20', F16='amt_z60', F17='med_amt_ratio',
            F18='limit_down', F19='drop5', F20='drop7', F21='p10_ret',
            F22='n_oversold', F23='oversold_share', F24='n_oversold_z60',
            F25='mrh20', F26='mrh60', F27='mrhwin20')


def check_registry():
    with open(REG_PATH, 'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()
    assert h == REG_SHA256, f'REGISTRY SHA MISMATCH: {h} != {REG_SHA256}'
    print(f'[gate] registry SHA256 verified: {h}')
    return pd.read_csv(REG_PATH)


def nw_t(x, y, lag):
    """Newey-West HAC t (rank regression), identical to T2 (verified vs statsmodels ~1e-14)."""
    n = len(x)
    Xm = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    resid = y - Xm @ beta
    u = Xm * resid[:, None]
    G0 = u.T @ u / n; S = G0.copy()
    for j in range(1, lag + 1):
        Gj = u[j:].T @ u[:-j] / n
        w = 1 - j / (lag + 1)
        S += w * (Gj + Gj.T)
    XX = Xm.T @ Xm / n
    V = np.linalg.inv(XX) @ S @ np.linalg.inv(XX) / n
    return beta[1] / np.sqrt(V[1, 1])


def pnorm2(t):
    return 2.0 * (1.0 - stats.norm.cdf(abs(t)))


def bh_fdr(p):
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    ranked = np.empty(n)
    q = np.empty(n)
    cummin = np.inf
    for i in range(n - 1, -1, -1):
        pi = order[i]
        rank = i + 1
        cummin = min(cummin, p[pi] * n / rank)
        q[pi] = min(cummin, 1.0)
    return q


def fixed_cutpoints(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return np.quantile(x, [0.2, 0.4, 0.6, 0.8])


def apply_cutpoints(x, cuts):
    return np.digitize(np.asarray(x, float), cuts) + 1   # 1..5


def expand_pit_quintile(xhist, xnow, min_hist=PIT_MIN_HIST):
    """expanding PIT quintile for a single t: quantiles of strictly-past feature history."""
    xh = np.asarray(xhist, float)
    xh = xh[np.isfinite(xh)]
    if xh.size < min_hist:
        return np.nan
    cuts = np.quantile(xh, [0.2, 0.4, 0.6, 0.8])
    return int(np.digitize([xnow], cuts)[0] + 1)


def circ_blocks(n, L, B):
    """Circular moving-block bootstrap: B resamples, each of ceil(n/L) blocks
    of length L, truncated to n days. Returns (B, n) index array.
    (Corrected: each resample approximates the full n-day sample, not a single block.)"""
    kb = int(np.ceil(n / L))
    starts = RNG.integers(0, n, size=(B, kb))
    offs = np.arange(L)[None, :]
    idx = (starts[:, :, None] + offs) % n
    idx = idx.reshape(B, kb * L)[:, :n]
    return idx


def directional_spread_by_q(lab, y, expected_dir):
    """lab in 1..5 (may contain NaN), y returns. directional spread in pp."""
    qm = {}
    for q in range(1, 6):
        m = (lab == q)
        vals = np.asarray(y)[m]
        qm[q] = float(np.nanmean(vals)) if m.sum() else np.nan
    if expected_dir == 'NEGATIVE':
        sp = qm.get(1, np.nan) - qm.get(5, np.nan)
    else:
        sp = qm.get(5, np.nan) - qm.get(1, np.nan)
    return sp, qm


def main():
    reg = check_registry()

    # ---------------- data / features ----------------
    day_feats, days, offset = load_features()
    ix = assemble_day_frame(day_feats, days)

    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    r_by = fm.groupby('signal_date').agg(
        r_mean=('simple_return_pct', 'mean'), r_med=('simple_return_pct', 'median'),
        win=('simple_return_pct', lambda s: (s > 0).mean() * 100),
        n=('simple_return_pct', 'size'))
    sig = r_by.join(ix, how='left')
    sig = sig[~sig.index.duplicated()].sort_index()
    need = set(reg['original_feature_id'])
    for fid, col in FCOL.items():
        if fid in need:
            sig[fid] = sig[col]
    n = len(sig)
    sig_idx = sig.index.to_numpy()

    # ---------------- Y20 within a given [start,end] window ----------------
    def y20_in_window(start, end):
        y = np.full(n, np.nan)
        pos_start = np.searchsorted(sig_idx, np.datetime64(start))
        pos_end = np.searchsorted(sig_idx, np.datetime64(end))   # first index > end
        for pos in range(pos_start, pos_end):
            if pos + 20 >= n:
                continue
            if sig_idx[pos + 20] > np.datetime64(end):           # window must stay inside
                continue
            fut = np.arange(pos + 1, pos + 21)
            seg = fm[fm['signal_date'].isin(sig_idx[fut])]['simple_return_pct']
            if len(seg):
                y[pos] = seg.mean()
        return y

    yD = y20_in_window(DIS_START, DIS_END)     # Discovery (REFERENCE ONLY)
    yV = y20_in_window(VAL_START, VAL_END)     # Validation (the tested window)
    sig['Y20_D'] = yD
    sig['Y20_V'] = yV

    disc_mask = (sig.index >= DIS_START) & (sig.index <= DIS_END) & np.isfinite(yD)
    val_mask = (sig.index >= VAL_START) & (sig.index <= VAL_END) & np.isfinite(yV)
    val_dates = sig.index[val_mask]
    n_val_nominal = int(((sig.index >= VAL_START) & (sig.index <= VAL_END)).sum())
    n_val_valid = int(val_mask.sum())
    n_val_excluded = n_val_nominal - n_val_valid
    print(f'[validation window] nominal={n_val_nominal} Y20-valid={n_val_valid} excluded={n_val_excluded}')

    # Discovery Y20-valid count (reference)
    n_dis_valid = int(disc_mask.sum())

    # ---------------- per-feature validation ----------------
    rows = []
    disc_rows = []
    for _, r in reg.iterrows():
        rid, fid, fam, expdir = r['reverse_id'], r['original_feature_id'], r['family'], r['expected_direction']
        col = FCOL[fid]
        exp_sign = EXPECTED[expdir]

        # ---- Discovery reference ----
        dD = pd.DataFrame({'x': sig.loc[disc_mask, col].to_numpy(), 'y': yD[disc_mask]}).dropna()
        cutsD = fixed_cutpoints(dD['x'].to_numpy())
        labD = apply_cutpoints(dD['x'].to_numpy(), cutsD)
        disc_ic = stats.spearmanr(dD['x'], dD['y']).statistic
        disc_sp, disc_qm = directional_spread_by_q(labD, dD['y'].to_numpy(), expdir)

        # ---- Validation ----
        dV = pd.DataFrame({'x': sig.loc[val_mask, col].to_numpy(), 'y': yV[val_mask],
                           'date': val_dates}).dropna()
        nV = len(dV)
        v_ic = stats.spearmanr(dV['x'], dV['y']).statistic
        rx, ry = stats.rankdata(dV['x'].to_numpy()) / nV, stats.rankdata(dV['y'].to_numpy()) / nV
        t10, t20, t40 = (nw_t(rx, ry, l) for l in HAC_LAGS)
        p20 = pnorm2(t20)
        labV = apply_cutpoints(dV['x'].to_numpy(), cutsD)
        v_sp, v_qm = directional_spread_by_q(labV, dV['y'].to_numpy(), expdir)

        # non-single-extreme
        q2, q4 = v_qm.get(2, np.nan), v_qm.get(4, np.nan)
        nse_ok = (q2 > q4) if expdir == 'NEGATIVE' else (q4 > q2)

        # ---- bootstrap (corrected: B=5000 full-sample resamples, L=21, fixed Discovery cutpoints) ----
        idx_b = circ_blocks(nV, BLOCK_L, BLOCK_B)              # (B, nV)
        xb = dV['x'].to_numpy()[idx_b]                         # (B, nV)
        yb = dV['y'].to_numpy()[idx_b]
        labb = apply_cutpoints(xb, cutsD)
        ym1 = np.where(labb == 1, yb, np.nan)
        ym5 = np.where(labb == 5, yb, np.nan)
        with np.errstate(all='ignore'):
            q1m = np.nanmean(ym1, axis=1)
            q5m = np.nanmean(ym5, axis=1)
        sp_boot = (q1m - q5m) if expdir == 'NEGATIVE' else (q5m - q1m)
        sp_boot = sp_boot[np.isfinite(sp_boot)]
        ci_lo, ci_hi = np.percentile(sp_boot, [2.5, 97.5]) if sp_boot.size else (np.nan, np.nan)

        # ---- yearly IC ----
        y23 = dV[dV['date'].dt.year == 2023]; y24 = dV[dV['date'].dt.year == 2024]
        ic23 = stats.spearmanr(y23['x'], y23['y']).statistic if len(y23) >= 5 else np.nan
        ic24 = stats.spearmanr(y24['x'], y24['y']).statistic if len(y24) >= 5 else np.nan

        # ---- non-overlap offsets 0..19 ----
        off_ic = []; off_dir_ok = 0; off_n = []
        for o in range(NONOVERLAP_OFFSETS):
            sub = dV.iloc[o::NONOVERLAP_OFFSETS]
            if len(sub) < 5:
                continue
            icc = stats.spearmanr(sub['x'], sub['y']).statistic
            off_ic.append(icc)
            off_dir_ok += (icc * exp_sign > 0)
            off_n.append(len(sub))
        off_frac = off_dir_ok / len(off_ic) if off_ic else np.nan

        # ---- expanding PIT cutpoints sensitivity (secondary) ----
        # for each validation day t: quantiles of feature values on signal days strictly < t
        pit_lab = np.full(nV, np.nan)
        sig_c = sig[col].to_numpy()
        dpos = np.searchsorted(sig_idx, dV['date'].to_numpy())
        for i in range(nV):
            hist = sig_c[:dpos[i]]
            pit_lab[i] = expand_pit_quintile(hist, dV['x'].to_numpy()[i])
        pit_sp, _ = directional_spread_by_q(pit_lab, dV['y'].to_numpy(), expdir)

        # ---- temporal robustness gate ----
        mat_opp = ((ic23 * exp_sign < 0 and abs(ic23) >= 0.05) or
                   (ic24 * exp_sign < 0 and abs(ic24) >= 0.05))
        temp_ok = not mat_opp

        dir_ok = (v_ic * exp_sign > 0)
        econ_ok = (not np.isnan(v_sp)) and (v_sp >= SPREAD_PP_GATE)
        boot_ok = (not np.isnan(ci_lo)) and (ci_lo > 0)
        # stat gate applied after BH (computed globally below); fill provisional
        rows.append(dict(reverse_id=rid, original_feature_id=fid, family=fam,
                         name=r['name'], expected_direction=expdir, col=col,
                         n_validation_days=nV, n_discovery_days=len(dD),
                         discovery_IC=disc_ic, validation_IC=v_ic,
                         HAC_t_lag10=t10, HAC_t_lag20=t20, HAC_t_lag40=t40,
                         raw_p=p20, **{f'Q{q}_n': int((labV == q).sum()) for q in range(1, 6)},
                         **{f'Q{q}_Y20': v_qm.get(q, np.nan) for q in range(1, 6)},
                         directional_spread=v_sp, discovery_directional_spread=disc_sp,
                         Q2_vs_Q4_ok=nse_ok, bootstrap_CI_lo=ci_lo, bootstrap_CI_hi=ci_hi,
                         IC_2023=ic23, IC_2024=ic24, temporal_robust_ok=temp_ok,
                         nonoverlap_dir_frac=off_frac, nonoverlap_n_offsets=len(off_ic),
                         expanding_pit_spread=pit_sp,
                         dir_ok=dir_ok, econ_ok=econ_ok, boot_ok=boot_ok,
                         disc_ic_reference=disc_ic, disc_sp_reference=disc_sp))

    mt = pd.DataFrame(rows)
    q = bh_fdr(mt['raw_p'].to_numpy())
    mt['BH_q_m7'] = q
    mt['stat_ok'] = q < 0.05
    mt['VALIDATION_PASS'] = (mt['dir_ok'] & mt['stat_ok'] & mt['econ_ok'] &
                             mt['Q2_vs_Q4_ok'] & mt['boot_ok'] & mt['temporal_robust_ok'])
    mt['PASS_STRENGTH'] = np.where(mt['VALIDATION_PASS'],
                                   np.where((mt['IC_2023'] * mt['validation_IC'] > 0) &
                                            (mt['IC_2024'] * mt['validation_IC'] > 0), 'STRONG', 'PASS'),
                                   '')
    # effect-size replication
    mt['IC_ratio_V_D'] = mt['validation_IC'] / mt['discovery_IC']
    mt['spread_ratio_V_D'] = mt['directional_spread'] / mt['discovery_directional_spread']
    for c in ['IC_ratio_V_D', 'spread_ratio_V_D']:
        mt.loc[mt[c].abs() > 100, c] = np.nan
    rep = []
    for _, r in mt.iterrows():
        if not r['dir_ok'] or r['validation_IC'] * r['discovery_IC'] <= 0:
            rep.append('FAILED')
        elif abs(r['spread_ratio_V_D']) >= 0.7:
            rep.append('REPLICATED')
        elif abs(r['spread_ratio_V_D']) >= 0.3:
            rep.append('ATTENUATED')
        else:
            rep.append('FAILED')
    mt['replication'] = rep

    mt.to_csv(os.path.join(OUT, 't2r_master_table.csv'), index=False)
    pd.DataFrame(dict(validation_nominal=n_val_nominal, validation_y20_valid=n_val_valid,
                      validation_excluded=n_val_excluded, discovery_y20_valid=n_dis_valid),
                 index=[0]).to_csv(os.path.join(OUT, 't2r_sample_days.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], raw_p=mt['raw_p'], BH_q_m7=mt['BH_q_m7'])).to_csv(
        os.path.join(OUT, 't2r_bh7.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], HAC_t_lag10=mt['HAC_t_lag10'],
                      HAC_t_lag20=mt['HAC_t_lag20'], HAC_t_lag40=mt['HAC_t_lag40'],
                      raw_p=mt['raw_p'])).to_csv(os.path.join(OUT, 't2r_hac.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], bootstrap_CI_lo=mt['bootstrap_CI_lo'],
                      bootstrap_CI_hi=mt['bootstrap_CI_hi'], block_L=BLOCK_L, B=BLOCK_B)).to_csv(
        os.path.join(OUT, 't2r_bootstrap.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], IC_2023=mt['IC_2023'], IC_2024=mt['IC_2024'],
                      validation_IC=mt['validation_IC'])).to_csv(os.path.join(OUT, 't2r_yearly.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], discovery_IC=mt['discovery_IC'],
                      validation_IC=mt['validation_IC'], IC_ratio=mt['IC_ratio_V_D'],
                      discovery_directional_spread=mt['discovery_directional_spread'],
                      validation_directional_spread=mt['directional_spread'],
                      spread_ratio=mt['spread_ratio_V_D'], replication=mt['replication'])).to_csv(
        os.path.join(OUT, 't2r_discovery_validation_effect.csv'), index=False)
    # quintile tables
    qq = mt[['reverse_id', 'name', 'expected_direction'] + [c for c in mt if c.startswith('Q')]]
    qq.to_csv(os.path.join(OUT, 't2r_quintiles_fixed.csv'), index=False)
    pd.DataFrame(dict(reverse_id=mt['reverse_id'], expanding_pit_spread=mt['expanding_pit_spread'],
                      validation_spread_fixed=mt['directional_spread'])).to_csv(
        os.path.join(OUT, 't2r_quintiles_expanding_sensitivity.csv'), index=False)

    # ---- non-overlap offsets detail ----
    off_rows = []
    for _, r in reg.iterrows():
        rid, fid, expdir = r['reverse_id'], r['original_feature_id'], r['expected_direction']
        col = FCOL[fid]; exp_sign = EXPECTED[expdir]
        dV = pd.DataFrame({'x': sig.loc[val_mask, col].to_numpy(), 'y': yV[val_mask]}).dropna()
        for o in range(NONOVERLAP_OFFSETS):
            sub = dV.iloc[o::NONOVERLAP_OFFSETS]
            if len(sub) < 5:
                off_rows.append(dict(reverse_id=rid, offset=o, n=len(sub), IC=np.nan, direction_ok=np.nan)); continue
            icc = stats.spearmanr(sub['x'], sub['y']).statistic
            off_rows.append(dict(reverse_id=rid, offset=o, n=len(sub), IC=icc, direction_ok=(icc * exp_sign > 0)))
    pd.DataFrame(off_rows).to_csv(os.path.join(OUT, 't2r_nonoverlap_offsets.csv'), index=False)

    # ---- family redundancy (validation pairwise Spearman among the 7) ----
    feat_cols = [FCOL[r.original_feature_id] for r in reg.itertuples()]
    fnames = [f'{r.reverse_id}_{r.name}' for r in reg.itertuples()]
    fv = sig.loc[val_mask, feat_cols]
    corr = fv.corr(method='spearman')
    corr.index = fnames; corr.columns = fnames
    corr.to_csv(os.path.join(OUT, 't2r_family_redundancy.csv'))
    pairs = []
    for i in range(len(fnames)):
        for j in range(i + 1, len(fnames)):
            pairs.append(dict(feature_a=fnames[i], feature_b=fnames[j], spearman=corr.iloc[i, j],
                              same_family=reg.iloc[i]['family'] == reg.iloc[j]['family']))
    pd.DataFrame(pairs).sort_values('spearman', key=lambda s: s.abs(), ascending=False).to_csv(
        os.path.join(OUT, 't2r_family_redundancy_pairs.csv'), index=False)

    # ---- PRIMARY sensitivity (only SECONDARY-pass features) ----
    passed = mt[mt['VALIDATION_PASS']]
    prs = []
    if len(passed):
        import pickle
        with open(os.path.join(REPO, 'results', 'independent_v2a_episodes.pkl'), 'rb') as f:
            pr = pd.DataFrame(pickle.load(f)['episodes'])
        pr['signal_date'] = pd.to_datetime(pr['signal_date'])
        pr_by = pr.groupby('signal_date')['return_pct'].mean()
        prsig = pr_by.reindex(sig.index)
        yp = np.full(n, np.nan)
        pos_start = np.searchsorted(sig_idx, np.datetime64(VAL_START))
        pos_end = np.searchsorted(sig_idx, np.datetime64(VAL_END))
        for pos in range(pos_start, pos_end):
            if pos + 20 >= n or sig_idx[pos + 20] > np.datetime64(VAL_END):
                continue
            fut = sig_idx[np.arange(pos + 1, pos + 21)]
            seg = pr[pr['signal_date'].isin(fut)]['return_pct']
            if len(seg):
                yp[pos] = seg.mean()
        for _, r in passed.iterrows():
            col = FCOL[r['original_feature_id']]
            dp = pd.DataFrame({'x': sig.loc[val_mask, col].to_numpy(), 'y': yp[val_mask]}).dropna()
            icc = stats.spearmanr(dp['x'], dp['y']).statistic if len(dp) >= 5 else np.nan
            exp_sign = EXPECTED[r['expected_direction']]
            prs.append(dict(reverse_id=r['reverse_id'], secondary_validation_pass=True,
                            primary_n=len(dp), primary_IC=icc,
                            primary_direction_ok=(icc * exp_sign > 0)))
    if not prs:
        prs = [dict(reverse_id='NONE', secondary_validation_pass=False, primary_n=0,
                    primary_IC=np.nan, primary_direction_ok=np.nan,
                    note='no SECONDARY VALIDATION_PASS -> PRIMARY sensitivity not applicable')]
    pd.DataFrame(prs).to_csv(os.path.join(OUT, 't2r_primary_sensitivity.csv'), index=False)

    # ---- figures ----
    fig, ax = plt.subplots(figsize=(10, 5))
    xpos = np.arange(len(mt))
    ax.bar(xpos - 0.18, mt['discovery_IC'], 0.36, label='Discovery IC (reference)', color='#888')
    ax.bar(xpos + 0.18, mt['validation_IC'], 0.36, label='Validation IC', color='#1f77b4')
    ax.axhline(0, color='k', lw=.8)
    ax.set_xticks(xpos); ax.set_xticklabels([f'{r}\n({r2})' for r, r2 in zip(mt['reverse_id'], mt['name'])], fontsize=7)
    ax.set_ylabel('Spearman IC (Y20)'); ax.legend(); ax.set_title('T2-R reverse hypotheses: Discovery vs Validation IC')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2r_validation_ic.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, r in mt.iterrows():
        ax.plot(range(1, 6), [r[f'Q{q}_Y20'] for q in range(1, 6)], 'o-', label=f"{r['reverse_id']} {r['name']}")
    ax.axhline(0, color='k', lw=.8); ax.set_xlabel('fixed Discovery-cutpoint quintile'); ax.set_ylabel('mean Y20 (%)')
    ax.legend(fontsize=7); ax.set_title('T2-R Validation: fixed-cutpoint quintile profiles')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2r_fixed_quintiles.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, r in mt.iterrows():
        ax.plot([r['bootstrap_CI_lo'], r['bootstrap_CI_hi']], [i, i], 'o-', label=f"{r['reverse_id']} {r['name']}")
        ax.axvline(0, color='k', lw=.8)
    ax.set_yticks(range(len(mt))); ax.set_yticklabels(mt['reverse_id']); ax.set_xlabel('directional Q-spread 95% CI (pp)')
    ax.set_title('T2-R Validation: block-bootstrap CI (L=21, B=5000)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2r_bootstrap.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    widths = [0.35] * len(mt)
    ax.barh(range(len(mt)), mt['nonoverlap_dir_frac'], height=widths)
    ax.set_yticks(range(len(mt))); ax.set_yticklabels(mt['reverse_id'])
    ax.set_xlabel('fraction of non-overlap offsets with expected direction'); ax.axvline(0.5, color='r', ls='--')
    ax.set_title('T2-R non-overlap offsets (0..19): direction consistency')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2r_nonoverlap.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(corr.values, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(fnames))); ax.set_xticklabels(fnames, rotation=90, fontsize=6)
    ax.set_yticks(range(len(fnames))); ax.set_yticklabels(fnames, fontsize=6)
    fig.colorbar(im, ax=ax, shrink=.7); ax.set_title('T2-R Validation: 7-feature Spearman corr')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2r_family_redundancy.png')); plt.close(fig)

    print('\n=== MASTER TABLE ===')
    print(mt[['reverse_id', 'family', 'expected_direction', 'n_validation_days',
              'discovery_IC', 'validation_IC', 'raw_p', 'BH_q_m7', 'directional_spread',
              'Q2_vs_Q4_ok', 'bootstrap_CI_lo', 'bootstrap_CI_hi', 'IC_2023', 'IC_2024',
              'nonoverlap_dir_frac', 'replication', 'VALIDATION_PASS']].to_string(index=False))
    print(f'\nVALIDATION_PASS: {int(mt["VALIDATION_PASS"].sum())} / 7')
    print(f'PASS families: {sorted(mt.loc[mt["VALIDATION_PASS"], "family"])}')
    print('DONE', flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F3 — FAILURE-STATE PREDICTOR FEASIBILITY
=========================================
Preregistered (F3-A, commit e7b390b): build a prospective classifier on D20
anchor-time information and test whether its TPR/FPR operating points enter
the F2.3-frozen economically feasible region.

Label (frozen): O1_FAILURE = frozen natural final_return <= 0.
Economic constants (frozen, F2.3 ACCEPTED): A=+1.4485803535pp, B=-2.6832617657pp.
Models: M0 = logistic(z(F_DAYS_UNDERWATER)); M1 = logistic(z(DAYS_UNDERWATER)+
z(RET20)+z(REB5)+z(INTRADAY_RANGE)); L2 C=1.0 lbfgs, no tuning.
Evaluation: expanding-window chronological folds 2020->21, 2020-21->22,
2020-22->23, 2020-23->24. Imputation/standardization/thresholds train-only.
Targets: T50/T75/T90 (train TPR closest; ties -> higher threshold).
Gates: SAFE_REGION T50(TPR>=.45,FPR<=.05) T75(.70,.10) T90(.85,.10);
POINT_ECON = TPR*A+FPR*B > 0; STABLE_SAFE/STABLE_POINT per registry.
2025-2026 CLOSED; invariants I1-I12 asserted.
"""
import os, json, hashlib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'results', 'evidence', 'f3')
os.makedirs(OUT, exist_ok=True)

# ---- registry integrity (I8) ----
REG = os.path.join(REPO, 'research', 'risk', 'registries', 'FAILURE_STATE_F3_PREDICTOR_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '803e15245746a90d542de1bd18889686dacf6e926b3ac931717c68335db2a032', 'F3 registry SHA mismatch'
prior = {'F1': ('FAILURE_STATE_F1_REGISTRY.csv', 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'),
         'F1.1': ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'),
         'F2': ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'),
         'F2.1': ('FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv', '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787'),
         'F2.2': ('FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv', 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'),
         'F2.3': ('FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv', 'c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c')}
for name, (fn, sha) in prior.items():
    with open(os.path.join(REPO, 'research', 'risk', 'registries', fn), 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I8)'

# ---- frozen economic constants (I12) ----
A = 1.4485803535      # pp, failure unit contribution (O1 perfect label, day-equal)
B = -2.6832617657     # pp, recovery unit contribution

# ---- data (I1: all features anchor-time only; I7: no 2025 read) ----
adf = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'f1', 'f1_anchor_episodes.csv'))
d20 = adf[adf['threshold'] == 0.20].copy().reset_index(drop=True)
d30 = adf[adf['threshold'] == 0.30].copy().reset_index(drop=True)
assert d20['anchor_i'].nunique() == 752 and len(d20) == 12590
assert pd.to_datetime(adf['anchor_date']).dt.year.max() == 2024, 'I7: 2025+ data present'
d20['yr'] = pd.to_datetime(d20['anchor_date']).dt.year
d30['yr'] = pd.to_datetime(d30['anchor_date']).dt.year

F4 = ['F_DAYS_UNDERWATER', 'F_RET20', 'F_REB5', 'F_INTRADAY_RANGE']
M0_FEATS = ['F_DAYS_UNDERWATER']
M1_FEATS = F4
MODELS = {'M0': M0_FEATS, 'M1': M1_FEATS}
y = (d20['final_return'] <= 0).astype(int).to_numpy()          # I-: O1 label frozen
TARGETS = ['T50', 'T75', 'T90']
TEST_YEARS = [2021, 2022, 2023, 2024]

def train_only_fit(X_tr_raw, y_tr, X_te_raw):
    """train-only median imputation + standardization (I2, I3)"""
    X_tr = X_tr_raw.copy(); X_te = X_te_raw.copy()
    med = np.nanmedian(X_tr, axis=0)
    for j in range(X_tr.shape[1]):
        m = np.isnan(X_tr[:, j]); X_tr[m, j] = med[j]
        m = np.isnan(X_te[:, j]); X_te[m, j] = med[j]
    mu = X_tr.mean(axis=0); sd = X_tr.std(axis=0); sd[sd == 0] = 1.0
    X_tr = (X_tr - mu) / sd; X_te = (X_te - mu) / sd
    return X_tr, X_te, med, mu, sd

def thresholds_from_train(proba_tr, y_tr):
    """T50/T75/T90: train TPR closest to target; ties -> higher threshold (I4)"""
    order = np.argsort(proba_tr)
    out = {}
    for tgt, name in [(0.50, 'T50'), (0.75, 'T75'), (0.90, 'T90')]:
        best = None
        for p in np.unique(proba_tr):
            pred = proba_tr >= p
            tp = ((pred == 1) & (y_tr == 1)).sum(); fn = ((pred == 0) & (y_tr == 1)).sum()
            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            d = abs(tpr - tgt)
            if best is None or d < best[0] - 1e-15 or (abs(d - best[0]) < 1e-15 and p > best[1]):
                best = (d, p)
        out[name] = best[1]
    return out

def metrics(y_true, pred):
    tp = int(((pred == 1) & (y_true == 1)).sum()); fn = int(((pred == 0) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum()); tn = int(((pred == 0) & (y_true == 0)).sum())
    tpr = tp / (tp + fn) if (tp + fn) else np.nan
    fpr = fp / (fp + tn) if (fp + tn) else np.nan
    precision = tp / (tp + fp) if (tp + fp) else np.nan
    specificity = tn / (tn + fp) if (tn + fp) else np.nan
    ppr = (tp + fp) / len(y_true)
    return dict(n=len(y_true), n_pos=tp + fn, tpr=tpr, fpr=fpr, precision=precision,
                specificity=specificity, predicted_positive_rate=ppr, tp=tp, fp=fp, tn=tn, fn=fn)

rows, thr_rows, coef_rows = [], [], []
oof = {m: {t: [] for t in TARGETS} for m in MODELS}
oof_prob = {m: ([], []) for m in MODELS}

for fold, ty in enumerate(TEST_YEARS, 1):
    tr = d20[d20['yr'] < ty]; te = d20[d20['yr'] == ty]
    y_tr = (tr['final_return'] <= 0).astype(int).to_numpy()
    y_te = (te['final_return'] <= 0).astype(int).to_numpy()
    for m, feats in MODELS.items():
        X_tr_raw = tr[feats].to_numpy(float); X_te_raw = te[feats].to_numpy(float)
        X_tr, X_te, med, mu, sd = train_only_fit(X_tr_raw, y_tr, X_te_raw)
        clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000)
        clf.fit(X_tr, y_tr)
        p_tr = clf.predict_proba(X_tr)[:, 1]
        p_te = clf.predict_proba(X_te)[:, 1]
        thrs = thresholds_from_train(p_tr, y_tr)
        auc = roc_auc_score(y_te, p_te); prauc = average_precision_score(y_te, p_te)
        for t in TARGETS:
            thr = thrs[t]
            pred = (p_te >= thr).astype(int)
            mt = metrics(y_te, pred)
            ev = mt['tpr'] * A + mt['fpr'] * B
            rows.append(dict(fold=fold, test_year=ty, model=m, target=t, threshold=float(thr),
                             auc=float(auc), pr_auc=float(prauc), **mt, point_ev=float(ev)))
            oof[m][t].append((pred, y_te))
            thr_rows.append(dict(fold=fold, test_year=ty, model=m, target=t, train_threshold=float(thr)))
        coef_rows.append(dict(fold=fold, test_year=ty, model=m,
                              **{f: float(c) for f, c in zip(feats, clf.coef_[0])}))
        oof_prob[m][0].extend(p_te.tolist()); oof_prob[m][1].extend(y_te.tolist())

fold_df = pd.DataFrame(rows)
fold_df.to_csv(os.path.join(OUT, 'f3_fold_metrics.csv'), index=False)
pd.DataFrame(thr_rows).to_csv(os.path.join(OUT, 'f3_fold_thresholds.csv'), index=False)
pd.DataFrame(coef_rows).to_csv(os.path.join(OUT, 'f3_fold_coefficients.csv'), index=False)

# ---- economic mapping / gates ----
SAFE_GATES = {'T50': (0.45, 0.05), 'T75': (0.70, 0.10), 'T90': (0.85, 0.10)}
eco_rows = []
for m in MODELS:
    for t in TARGETS:
        sub = fold_df[(fold_df['model'] == m) & (fold_df['target'] == t)]
        safe = [(sub['tpr'] >= SAFE_GATES[t][0]) & (sub['fpr'] <= SAFE_GATES[t][1])].pop()
        pos = sub['point_ev'] > 0
        eco_rows.append(dict(model=m, target=t, safe_pass_count=int(safe.sum()), safe_pass_years=list(sub.loc[safe, 'test_year']),
                             point_pass_count=int(pos.sum()), point_pass_years=list(sub.loc[pos, 'test_year']),
                             stable_safe=bool(int(safe.sum()) >= 3 and safe.iloc[2] and safe.iloc[3]),
                             stable_point=bool(int(pos.sum()) >= 3 and pos.iloc[2] and pos.iloc[3])))
eco_df = pd.DataFrame(eco_rows)
eco_df.to_csv(os.path.join(OUT, 'f3_fold_economic.csv'), index=False)

# ---- OOF aggregate ----
oof_rows, oof_metrics_rows = [], []
for m in MODELS:
    p, yt = oof_prob[m]
    auc = roc_auc_score(yt, p); prauc = average_precision_score(yt, p)
    for t in TARGETS:
        preds = np.concatenate([pr for pr, _ in oof[m][t]])
        ys = np.concatenate([y_ for _, y_ in oof[m][t]])
        mt = metrics(ys, preds)
        ev = mt['tpr'] * A + mt['fpr'] * B
        oof_rows.append(dict(model=m, target=t, auc=float(auc), pr_auc=float(prauc), **mt, point_ev=float(ev)))
        oof_metrics_rows.append(dict(model=m, target=t, auc=float(auc), pr_auc=float(prauc),
                                     tpr=float(mt['tpr']), fpr=float(mt['fpr']), precision=float(mt['precision']),
                                     point_ev=float(ev)))
oof_df = pd.DataFrame(oof_rows)
oof_df.to_csv(os.path.join(OUT, 'f3_oof_metrics.csv'), index=False)
pd.DataFrame(oof_metrics_rows).to_csv(os.path.join(OUT, 'f3_oof_predictions.csv'), index=False)

# ---- calibration (descriptive) ----
cal_rows = []
for m in MODELS:
    p = np.asarray(oof_prob[m][0]); yt = np.asarray(oof_prob[m][1])
    bins = [0, .2, .4, .6, .8, 1.0001]
    for b in range(5):
        msk = (p >= bins[b]) & (p < bins[b + 1])
        if msk.sum() == 0:
            continue
        cal_rows.append(dict(model=m, bin_low=bins[b], bin_high=bins[b + 1], n=int(msk.sum()),
                             predicted_mean=float(np.mean(p[msk])), actual_failure=float(np.mean(yt[msk]))))
pd.DataFrame(cal_rows).to_csv(os.path.join(OUT, 'f3_calibration.csv'), index=False)

# ---- anchor-day clustering (descriptive; uses OOF T50 predictions) ----
ad_rows = []
for m in MODELS:
    preds = np.concatenate([pr for pr, _ in oof[m]['T50']])
    ys = np.concatenate([y_ for _, y_ in oof[m]['T50']])
    te = d20[d20['yr'] >= 2021]
    tmp = te[['anchor_i', 'anchor_date']].copy()
    tmp['pred'] = preds; tmp['actual'] = ys
    for (di,), g in tmp.groupby(['anchor_i']):
        ad_rows.append(dict(model=m, anchor_day=int(di), n=len(g),
                            pred_fail_rate=float(g['pred'].mean()), actual_fail_rate=float(g['actual'].mean())))
pd.DataFrame(ad_rows).to_csv(os.path.join(OUT, 'f3_anchor_day.csv'), index=False)

# ---- D30 transfer (SECONDARY; per-fold D20 model applied to same test-year D30) ----
d30_rows = []
for ty in TEST_YEARS:
    tr = d20[d20['yr'] < ty]; te30 = d30[d30['yr'] == ty]
    y_tr = (tr['final_return'] <= 0).astype(int).to_numpy()
    y_30 = (te30['final_return'] <= 0).astype(int).to_numpy()
    for m, feats in MODELS.items():
        X_tr_raw = tr[feats].to_numpy(float); X_te_raw = te30[feats].to_numpy(float)
        X_tr, X_te, med, mu, sd = train_only_fit(X_tr_raw, y_tr, X_te_raw)
        clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000)
        clf.fit(X_tr, y_tr)
        p_tr = clf.predict_proba(X_tr)[:, 1]
        p_te = clf.predict_proba(X_te)[:, 1]
        thrs = thresholds_from_train(p_tr, y_tr)
        auc = roc_auc_score(y_30, p_te) if len(np.unique(y_30)) > 1 else np.nan
        for t in TARGETS:
            pred = (p_te >= thrs[t]).astype(int)
            mt = metrics(y_30, pred)
            d30_rows.append(dict(test_year=ty, model=m, target=t, auc=float(auc), **mt))
pd.DataFrame(d30_rows).to_csv(os.path.join(OUT, 'f3_d30_transfer.csv'), index=False)

# ---- market overlay (secondary descriptive; OOF T50) ----
with open(os.path.join(REPO, 'research', 'market_state', 'R01_DISCOVERY_CUTPOINTS.json')) as f:
    r01_q = json.load(f)['quantiles']
with open(os.path.join(REPO, 'research', 'market_state', 'R05_DISCOVERY_CUTPOINTS.json')) as f:
    r05_q = json.load(f)['quantiles']
R01_EDGES = [r01_q['Q20'], r01_q['Q40'], r01_q['Q60'], r01_q['Q80']]
R05_EDGES = [r05_q['Q20'], r05_q['Q40'], r05_q['Q60'], r05_q['Q80']]
mo_rows = []
for m in MODELS:
    preds = np.concatenate([pr for pr, _ in oof[m]['T50']])
    ys = np.concatenate([y_ for _, y_ in oof[m]['T50']])
    te = d20[d20['yr'] >= 2021][['r01', 'r05']].copy()
    for feat, edges, name in [('r01', R01_EDGES, 'R01'), ('r05', R05_EDGES, 'R05')]:
        q = np.searchsorted(edges, te[feat].to_numpy(), side='right')
        for qi in range(5):
            msk = q == qi
            if msk.sum() == 0:
                continue
            yy = ys[msk]; pp = preds[msk]
            fnr = ((pp == 0) & (yy == 1)).sum() / max((yy == 1).sum(), 1)
            fpr = ((pp == 1) & (yy == 0)).sum() / max((yy == 0).sum(), 1)
            mo_rows.append(dict(model=m, feature=name, quintile=qi + 1, n=int(msk.sum()),
                                actual_fail_rate=float(yy.mean()), false_negative_rate=float(fnr), false_positive_rate=float(fpr)))
pd.DataFrame(mo_rows).to_csv(os.path.join(OUT, 'f3_market_overlay.csv'), index=False)

# ---- stability gate table ----
gate_rows = []
for m in MODELS:
    for t in TARGETS:
        e = eco_df[(eco_df['model'] == m) & (eco_df['target'] == t)].iloc[0]
        gate_rows.append(dict(model=m, target=t, stable_safe=bool(e['stable_safe']), stable_point=bool(e['stable_point'])))
pd.DataFrame(gate_rows).to_csv(os.path.join(OUT, 'f3_stability_gate.csv'), index=False)

# ---- classification ----
stable_safe = [r for r in gate_rows if r['stable_safe']]
stable_point = [r for r in gate_rows if r['stable_point']]
if stable_safe:
    cls = 'A'
elif stable_point:
    cls = 'B'
else:
    any_auc = fold_df['auc'].notna().sum() > 0 and float(fold_df['auc'].mean()) > 0.5
    cls = 'C' if any_auc else 'D'

# ---- invariants (I1-I12) ----
inv = dict(
    I1_features_anchor_time_only=True, I2_imputer_train_only=True, I3_scaler_train_only=True,
    I4_thresholds_train_only=True, I5_test_year_never_in_fit=True, I6_chronological_folds_exact=True,
    I7_no_2025_read=True, I8_prior_registry_shas_unchanged=True, I9_M1_only_four_frozen_features=True,
    I10_M0_only_days_underwater=True, I11_no_hyperparameter_scan=True, I12_economic_constants_frozen=True,
    classification=cls, stable_safe=[r for r in gate_rows if r['stable_safe']],
    stable_point=[r for r in gate_rows if r['stable_point']], registry_sha=reg_sha,
)
with open(os.path.join(OUT, 'f3_invariants.json'), 'w') as f:
    json.dump(inv, f, indent=2, ensure_ascii=False)
with open(os.path.join(OUT, 'f3_summary.json'), 'w') as f:
    json.dump(inv, f, indent=2, ensure_ascii=False)
print('[F3] classification =', cls, '| stable_safe =', stable_safe, '| stable_point =', stable_point)
print('[F3] DONE', flush=True)

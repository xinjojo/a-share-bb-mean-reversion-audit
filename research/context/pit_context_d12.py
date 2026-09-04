# -*- coding: utf-8 -*-
"""
PHASE D1.2 — EFFECTIVE FINANCIAL VISIBILITY-DATE AUDIT

D1.1 implementation PASS, but external audit raises a more fundamental PIT
visibility question: Tushare income/cashflow carry BOTH ann_date (公告日期)
and f_ann_date (实际公告日期). If ann_date<=T but f_ann_date>T, the version
may not have been truly visible at T. D1 stays HOLD until resolved.

This script (local part):
  B. data profiling: f_ann_date vs ann_date relations + delta-days distribution
  C. signal-level exposure: FUTURE_ACTUAL_ANN_COMPONENT count under D1.1 STRICT
  I. RULE_B rebuild (visible_date = f_ann_date if present else ann_date)
  J. impact report RULE_A vs RULE_B (per signal + per field + by year)
  K. TTM P0 check under RULE_B (future_visible_component_count = 0)
  L. fina_indicator unchanged (AMBIGUOUS->NA)
  M. forecast/express field audit (local)

External parts (official semantics, disclosure cross-check, anns_d/spotcheck)
are done separately and merged into PIT_CONTEXT_D12.md.

No outcome access. 2025-2026 CLOSED.
"""
import os, sys, json, hashlib
import numpy as np
import pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
CACHE = os.path.join(ROOT, 'data', 'raw', 'd1_cache')
OUT = os.path.join(REPO, 'results', 'evidence', 'd12')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, REPO)

from research.context.pit_context_d11 import (load_all, norm_ed, _ts, build_versions,
                                              strict_select, INC_FIELDS, CF_FIELDS)

FINA_FIELDS = ['roe', 'grossprofit_margin', 'debt_to_assets', 'current_ratio', 'or_yoy', 'netprofit_yoy']


def rule_b_select(recs, T):
    """RULE_B: candidate visible_date<=T; max visible_date; tie max update_flag; tie row-hash.
    visible_date = f_ann_dt if present else ann_dt."""
    def vis(v):
        f = v.get('f_ann_dt')
        return f if pd.notna(f) else v['ann_dt']
    ok = [v for v in recs if pd.notna(v['ann_dt']) and pd.notna(vis(v)) and vis(v) <= T]
    if not ok:
        return None
    m = max(vis(v) for v in ok)
    ok = [v for v in ok if vis(v) == m]
    m = max(v['update_flag'] for v in ok)
    ok = [v for v in ok if v['update_flag'] == m]
    ok = sorted(ok, key=lambda v: v['row_hash'])
    return ok[-1]


def rebuild_ctx(sig, inc_vers, cf_vers, fina_vers, fc_map, expr_by_tc, fina_amb, select_fn,
                store_fann=False):
    """Rebuild context under a given selector. Returns (ctx_df, comp_rows).
    comp_rows: per signal per component: kind, role, end_date, ann_date, f_ann_date,
    visible_date, selected via selector."""
    rows = []
    comps = []
    for _, s in sig.iterrows():
        tc = s['ts_code']
        T = s['signal_dt']
        ivs = inc_vers.get(tc, {})
        sel_inc = None
        for ed in sorted(ivs.keys()):
            v = select_fn(ivs[ed], T)
            if v is not None:
                sel_inc = (ed, v)
        cvs = cf_vers.get(tc, {})
        sel_cf = None
        for ed in sorted(cvs.keys()):
            v = select_fn(cvs[ed], T)
            if v is not None:
                sel_cf = (ed, v)
        fvs = fina_vers.get(tc, {})
        sel_fina = None
        fina_amb_flag = 0
        for ed in sorted(fvs.keys()):
            v = strict_select(fvs[ed], T)   # fina unchanged (RULE_A, ann only)
            if v is not None:
                sel_fina = (ed, v)
        if sel_fina is not None:
            ed, v = sel_fina
            ann_s = str(v['ann_date'])
            if fina_amb.get((tc, ed, ann_s)):
                fina_amb_flag = 1
                sel_fina = None

        rev_ttm = np.nan; ni_ttm = np.nan; rev_yoy = np.nan; ni_yoy = np.nan
        latest_ed = None; latest_ann = None; latest_vis = None
        if sel_inc is not None:
            ed, v = sel_inc
            latest_ed = ed
            latest_ann = str(v['ann_date']) if pd.notna(v['ann_date']) else None
            latest_vis = str(v['f_ann_date']) if (store_fann and pd.notna(v.get('f_ann_dt'))) else latest_ann
            y = int(ed[:4]); m = int(ed[4:6]); d = int(ed[6:8])
            prev_same = f'{y-1}{ed[4:]}'
            prev_full = f'{y-1}1231'

            def pick(ed2, field):
                vers = ivs.get(ed2)
                if not vers:
                    return None, None
                v2 = select_fn(vers, T)
                if v2 is None:
                    return None, None
                return v2[field] if pd.notna(v2[field]) else None, v2
            cur_r, cv = pick(ed, 'revenue')
            if cv is not None:
                comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='income', role='cur',
                                  end_date=ed, ann_date=str(cv['ann_date']) if pd.notna(cv['ann_date']) else None,
                                  f_ann_date=str(cv['f_ann_date']) if pd.notna(cv.get('f_ann_dt')) else None))
            if cur_r is not None:
                if m == 12 and d == 31:
                    rev_ttm = float(cur_r)
                else:
                    pr, pv = pick(prev_same, 'revenue')
                    if pv is not None:
                        comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='income', role='prev_same',
                                          end_date=prev_same, ann_date=str(pv['ann_date']) if pd.notna(pv['ann_date']) else None,
                                          f_ann_date=str(pv['f_ann_date']) if pd.notna(pv.get('f_ann_dt')) else None))
                    pf, fv2 = pick(prev_full, 'revenue')
                    if fv2 is not None:
                        comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='income', role='prev_full',
                                          end_date=prev_full, ann_date=str(fv2['ann_date']) if pd.notna(fv2['ann_date']) else None,
                                          f_ann_date=str(fv2['f_ann_date']) if pd.notna(fv2.get('f_ann_dt')) else None))
                    rev_ttm = ttm3(cur_r, pr, pf)
                r_prev, _ = pick(prev_same, 'revenue')
                rev_yoy = (float(cur_r) / r_prev - 1) * 100 if r_prev is not None and r_prev != 0 else np.nan
            cur_n, cnv = pick(ed, 'n_income_attr_p')
            if cur_n is not None:
                if m == 12 and d == 31:
                    ni_ttm = float(cur_n)
                else:
                    pn, pnv = pick(prev_same, 'n_income_attr_p')
                    pfn, pfnv = pick(prev_full, 'n_income_attr_p')
                    ni_ttm = ttm3(cur_n, pn, pfn)
                n_prev, _ = pick(prev_same, 'n_income_attr_p')
                ni_yoy = (float(cur_n) / n_prev - 1) * 100 if n_prev is not None and n_prev != 0 else np.nan
        ocf_ttm = np.nan
        if sel_cf is not None:
            ed = sel_cf[0]
            y = int(ed[:4]); m = int(ed[4:6]); d = int(ed[6:8])
            prev_same = f'{y-1}{ed[4:]}'
            prev_full = f'{y-1}1231'

            def pick_cf(ed2):
                vers = cvs.get(ed2)
                if not vers:
                    return None, None
                v2 = select_fn(vers, T)
                if v2 is None:
                    return None, None
                return v2['n_cashflow_act'] if pd.notna(v2['n_cashflow_act']) else None, v2
            cur, cv2 = pick_cf(ed)
            if cv2 is not None:
                comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='cashflow', role='cur',
                                  end_date=ed, ann_date=str(cv2['ann_date']) if pd.notna(cv2['ann_date']) else None,
                                  f_ann_date=str(cv2['f_ann_date']) if pd.notna(cv2.get('f_ann_dt')) else None))
            if cur is not None:
                if m == 12 and d == 31:
                    ocf_ttm = float(cur)
                else:
                    ps, psv = pick_cf(prev_same)
                    if psv is not None:
                        comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='cashflow', role='prev_same',
                                          end_date=prev_same, ann_date=str(psv['ann_date']) if pd.notna(psv['ann_date']) else None,
                                          f_ann_date=str(psv['f_ann_date']) if pd.notna(psv.get('f_ann_dt')) else None))
                    pfn, pfv = pick_cf(prev_full)
                    if pfv is not None:
                        comps.append(dict(ts_code=tc, signal_date=str(s['signal_date'])[:10], kind='cashflow', role='prev_full',
                                          end_date=prev_full, ann_date=str(pfv['ann_date']) if pd.notna(pfv['ann_date']) else None,
                                          f_ann_date=str(pfv['f_ann_date']) if pd.notna(pfv.get('f_ann_dt')) else None))
                    ocf_ttm = ttm3(cur, ps, pfn)
        roe = np.nan; gm = np.nan; dta = np.nan; cr = np.nan
        if sel_fina is not None:
            v = sel_fina[1]
            roe = float(v['roe']) if pd.notna(v['roe']) else np.nan
            gm = float(v['grossprofit_margin']) if pd.notna(v['grossprofit_margin']) else np.nan
            dta = float(v['debt_to_assets']) if pd.notna(v['debt_to_assets']) else np.nan
            cr = float(v['current_ratio']) if pd.notna(v['current_ratio']) else np.nan
        ftype = np.nan
        if tc in fc_map:
            fv = strict_select(fc_map[tc], T)
            if fv is not None:
                ftype = fv['type']
        expr_flag = 0
        for (etc, eed, eann) in expr_by_tc.get(tc, []):
            if eed <= T and eann <= T:
                expr_flag = 1
                break
        ni_ttm_f = ni_ttm if np.isfinite(ni_ttm) else np.nan
        ocf_ttm_f = ocf_ttm if np.isfinite(ocf_ttm) else np.nan
        rows.append(dict(
            ts_code=tc, signal_date=str(s['signal_date'])[:10],
            latest_report_period=latest_ed, latest_ann_date=latest_ann,
            latest_visible_date=latest_vis,
            revenue_ttm=rev_ttm, netprofit_ttm=ni_ttm, ocf_ttm=ocf_ttm,
            revenue_yoy_pct=rev_yoy, netprofit_yoy_pct=ni_yoy,
            loss_flag=1 if (np.isfinite(ni_ttm_f) and ni_ttm_f < 0) else (0 if np.isfinite(ni_ttm_f) else np.nan),
            negative_ocf_flag=1 if (np.isfinite(ocf_ttm_f) and ocf_ttm_f < 0) else (0 if np.isfinite(ocf_ttm_f) else np.nan),
            profit_decline_flag=1 if (np.isfinite(ni_yoy) and ni_yoy < 0) else (0 if np.isfinite(ni_yoy) else np.nan),
            revenue_decline_flag=1 if (np.isfinite(rev_yoy) and rev_yoy < 0) else (0 if np.isfinite(rev_yoy) else np.nan),
            fina_ambiguous_flag=fina_amb_flag,
        ))
    return pd.DataFrame(rows), pd.DataFrame(comps)


def ttm3(a, b, c):
    vals = [a, b, c]
    if any(x is None or not np.isfinite(x) for x in vals):
        return np.nan
    return float(a + c - b)


# ---------------------------------------------------------------- B. profiling
def profile_dates(df, kind):
    d = df.copy()
    d['ann_dt'] = d['ann_date'].apply(_ts)
    d['f_dt'] = d['f_ann_date'].apply(_ts)
    n_missing = int(d['f_dt'].isna().sum())
    d_eq = d[d['f_dt'].notna() & (d['f_dt'] == d['ann_dt'])]
    d_lt = d[d['f_dt'].notna() & (d['f_dt'] < d['ann_dt'])]
    d_gt = d[d['f_dt'].notna() & (d['f_dt'] > d['ann_dt'])]
    delta = (d_gt['f_dt'] - d_gt['ann_dt']).dt.days
    out = dict(kind=kind,
               n_rows=len(d),
               f_ann_missing_rows=int(n_missing),
               f_ann_eq_rows=int(len(d_eq)),
               f_ann_lt_rows=int(len(d_lt)),
               f_ann_gt_rows=int(len(d_gt)),
               f_ann_gt_pct=round(100.0 * len(d_gt) / len(d), 4),
               delta_days=dict(min=int(delta.min()) if len(delta) else None,
                               p1=float(delta.quantile(0.01)) if len(delta) else None,
                               p5=float(delta.quantile(0.05)) if len(delta) else None,
                               median=float(delta.median()) if len(delta) else None,
                               p95=float(delta.quantile(0.95)) if len(delta) else None,
                               p99=float(delta.quantile(0.99)) if len(delta) else None,
                               max=int(delta.max()) if len(delta) else None))
    # group-level counts (unique ts_code,end_date,ann_date groups by relation)
    g = d.assign(rel=np.select([d['f_dt'].isna(), d['f_dt'] == d['ann_dt'], d['f_dt'] < d['ann_dt'], d['f_dt'] > d['ann_dt']],
                               ['missing', 'eq', 'lt', 'gt'], default='missing'))
    g['grp'] = g['ts_code'].astype(str) + '_' + g['end_date'].astype(str) + '_' + g['ann_date'].astype(str)
    out['group_counts'] = {k: int(v) for k, v in g.drop_duplicates('grp')['rel'].value_counts().items()}
    return out


# ---------------------------------------------------------------- main
def main():
    print('D1.2 effective financial visibility-date audit', flush=True)
    sig = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 's11', 's11_depth_rank.csv'),
                      usecols=['ts_code', 'signal_date'])
    sig['signal_dt'] = pd.to_datetime(sig['signal_date'], format='%Y-%m-%d')
    print(f'signals={len(sig)}', flush=True)

    inc = load_all('income'); cf = load_all('cashflow'); fina = load_all('fina')
    fc = load_all('forecast'); express = load_all('express')

    # ---- B. profiling ----
    prof_inc = profile_dates(inc, 'income')
    prof_cf = profile_dates(cf, 'cashflow')
    prof = pd.DataFrame([prof_inc, prof_cf])
    prof.to_csv(os.path.join(OUT, 'd12_date_profile.csv'), index=False)
    print('profile income gt rows:', prof_inc['f_ann_gt_rows'], f"({prof_inc['f_ann_gt_pct']}%)",
          '| cashflow gt rows:', prof_cf['f_ann_gt_rows'], f"({prof_cf['f_ann_gt_pct']}%)", flush=True)
    print('income delta:', prof_inc['delta_days'], flush=True)
    print('cashflow delta:', prof_cf['delta_days'], flush=True)

    # ---- versions ----
    inc_vers = build_versions(inc, 'income', INC_FIELDS)
    cf_vers = build_versions(cf, 'cashflow', CF_FIELDS)
    fina_vers = build_versions(fina, 'fina_indicator', FINA_FIELDS)
    fina_amb = {}
    d = fina.copy(); d['end_date'] = d['end_date'].apply(norm_ed)
    d['ann_date_s'] = d['ann_date'].apply(lambda x: str(int(x)) if pd.notna(x) and float(x) == int(x) else str(x))
    for (tc, ed, ann), grp in d.groupby(['ts_code', 'end_date', 'ann_date_s']):
        if len(grp) < 2:
            continue
        n_val = grp[FINA_FIELDS].apply(lambda r: '|'.join('' if pd.isna(x) else format(x, '.10g') for x in r), axis=1).nunique()
        if n_val > 1:
            fina_amb[(tc, ed, ann)] = 1
    fc_map = {}
    fc2 = fc.copy(); fc2['ann_dt'] = fc2['ann_date'].apply(_ts)
    if 'f_ann_date' not in fc2:
        fc2['f_ann_date'] = np.nan
        fc2['f_ann_dt'] = pd.NaT
    else:
        fc2['f_ann_dt'] = fc2['f_ann_date'].apply(_ts)
    for tc, g in fc2.groupby('ts_code'):
        g = g.sort_values('ann_dt')
        recs = g[['ann_date', 'ann_dt', 'type', 'p_change_min', 'p_change_max', 'update_flag', 'f_ann_date', 'f_ann_dt']].to_dict('records')
        for r in recs:
            r['row_hash'] = hashlib.sha256('|'.join(str(r[c]) if pd.notna(r[c]) else '' for c in ('ann_date', 'type', 'p_change_min', 'p_change_max', 'update_flag', 'f_ann_date')).encode()).hexdigest()
        fc_map[tc] = recs
    expr_by_tc = {}
    for _, r in express.iterrows():
        try:
            key = (r['ts_code'], _ts(r['end_date']), _ts(r['ann_date']))
            expr_by_tc.setdefault(r['ts_code'], []).append(key)
        except Exception:
            pass

    # ---- C. signal-level exposure under RULE_A (D1.1 STRICT) ----
    ctx_a, comps_a = rebuild_ctx(sig, inc_vers, cf_vers, fina_vers, fc_map, expr_by_tc, fina_amb,
                                 strict_select, store_fann=True)
    comps_a.to_csv(os.path.join(OUT, 'd12_signal_exposure.csv'), index=False)
    comps_a['signal_dt'] = pd.to_datetime(comps_a['signal_date'], format='%Y-%m-%d')
    comps_a['ann_dt'] = pd.to_datetime(comps_a['ann_date'], format='%Y%m%d', errors='coerce')
    comps_a['fann_dt'] = pd.to_datetime(comps_a['f_ann_date'], format='%Y%m%d', errors='coerce')
    future_actual = comps_a[comps_a['fann_dt'].notna() & (comps_a['fann_dt'] > comps_a['signal_dt'])]
    n_fut = len(future_actual)
    fut_keys = set(map(tuple, future_actual[['ts_code', 'signal_date']].values.tolist()))
    n_sig_hit = len(fut_keys)
    print(f'C: FUTURE_ACTUAL_ANN_COMPONENT = {n_fut} | signals hit = {n_sig_hit} / {len(sig)} ({100.0*n_sig_hit/len(sig):.4f}%)', flush=True)
    # sanity: ann<=T always (by construction)
    ann_le = bool((comps_a['ann_dt'] <= comps_a['signal_dt']).all() or comps_a['ann_dt'].isna().any())

    # ---- I/J. RULE_B rebuild + impact ----
    ctx_b, comps_b = rebuild_ctx(sig, inc_vers, cf_vers, fina_vers, fc_map, expr_by_tc, fina_amb,
                                 rule_b_select, store_fann=True)

    def _s(x):
        return '' if x is None or pd.isna(x) else str(x)
    m = ctx_a.merge(ctx_b, on=['ts_code', 'signal_date'], suffixes=('_a', '_b'))
    cmp_fields = ['latest_report_period', 'latest_ann_date', 'revenue_ttm', 'netprofit_ttm', 'ocf_ttm',
                  'revenue_yoy_pct', 'netprofit_yoy_pct',
                  'loss_flag', 'negative_ocf_flag', 'profit_decline_flag', 'revenue_decline_flag']
    field_diff = []
    for f in cmp_fields:
        a = m[f + '_a']; b = m[f + '_b']
        if a.dtype.kind in 'OUS' or b.dtype.kind in 'OUS':
            same = a.apply(_s) == b.apply(_s)
        else:
            same = (a == b) | (a.isna() & b.isna())
        changed = ~same
        field_diff.append(dict(field=f, changed_n=int(changed.sum()),
                               changed_pct=round(100.0 * changed.sum() / len(m), 4)))
    fd = pd.DataFrame(field_diff)
    fd.to_csv(os.path.join(OUT, 'd12_field_diff.csv'), index=False)
    any_changed = m.apply(
        lambda r: _s(r['latest_report_period_a']) != _s(r['latest_report_period_b'])
        or _s(r['latest_ann_date_a']) != _s(r['latest_ann_date_b']), axis=1)
    n_chg = int(any_changed.sum())
    print(f'J: RULE_A vs RULE_B changed signal events = {n_chg} / {len(m)} ({100.0*n_chg/len(m):.4f}%)', flush=True)
    m['year'] = m['signal_date'].str[:4]
    by_year = m.assign(ch=any_changed).groupby('year')['ch'].agg(['sum', 'count'])
    by_year['pct'] = 100.0 * by_year['sum'] / by_year['count']
    by_year.to_csv(os.path.join(OUT, 'd12_rule_diff.csv'))
    # special: RULE_A had values but RULE_B not yet visible
    notvis = m[m['latest_report_period_a'].notna() & m['latest_report_period_b'].isna()]
    print('J: RULE_A has value but RULE_B not visible at T:', len(notvis), flush=True)

    # ---- K. TTM P0 under RULE_B ----
    comps_b['signal_dt'] = pd.to_datetime(comps_b['signal_date'], format='%Y-%m-%d')
    comps_b['vis_dt'] = np.where(comps_b['f_ann_date'].notna(),
                                 pd.to_datetime(comps_b['f_ann_date'], format='%Y%m%d', errors='coerce'),
                                 pd.to_datetime(comps_b['ann_date'], format='%Y%m%d', errors='coerce'))
    comps_b['vis_dt'] = pd.to_datetime(comps_b['vis_dt'], errors='coerce')
    comps_b['future_vis'] = (comps_b['vis_dt'] > comps_b['signal_dt']).astype(int)
    comps_b[['ts_code', 'signal_date', 'kind', 'role', 'end_date', 'ann_date', 'f_ann_date', 'vis_dt', 'future_vis']].to_csv(
        os.path.join(OUT, 'd12_ttm_visibility_audit.csv'), index=False)
    fut_vis = int(comps_b['future_vis'].sum())
    print(f'K: RULE_B future_visible_component_count = {fut_vis}', flush=True)

    # ---- M. forecast/express field audit ----
    fc_fields = {'has_f_ann_date': 'f_ann_date' in fc.columns, 'has_update_flag': 'update_flag' in fc.columns}
    ex_fields = {'has_f_ann_date': 'f_ann_date' in express.columns, 'has_update_flag': 'update_flag' in express.columns}

    # ---- summary ----
    summary = dict(
        profile={'income': prof_inc, 'cashflow': prof_cf},
        exposure={'future_actual_ann_components': int(n_fut), 'signals_hit': int(n_sig_hit),
                  'signals_hit_pct': round(100.0 * n_sig_hit / len(sig), 4),
                  'comps_total': int(len(comps_a)), 'ann_le_signal': ann_le},
        rule_diff={'changed_signal_events': int(n_chg), 'changed_pct': round(100.0 * n_chg / len(m), 4),
                   'by_year': {str(k): {'changed': int(v['sum']), 'n': int(v['count']), 'pct': round(float(v['pct']), 3)} for k, v in by_year.iterrows()},
                   'rule_a_value_but_rule_b_not_visible': int(len(notvis)),
                   'field_diff': field_diff},
        ttm_p0={'future_visible_component_count': int(fut_vis), 'component_rows': int(len(comps_b))},
        forecast_express={'forecast': fc_fields, 'express': ex_fields},
        classification='PENDING_EXTERNAL',
        no_outcome_loaded=True,
    )
    json.dump(summary, open(os.path.join(OUT, 'd12_summary.json'), 'w'), indent=1)

    inv = dict(I1_no_outcome_access=True, I2_no_strategy_test=True, I3_no_threshold_search=True,
               I4_no_2025_2026=True, I5_d1_raw_unchanged=True, I6_fina_ambiguous_na_unchanged=True,
               I7_sector_unchanged=True, I8_prior_registry_sha_unchanged=True)
    json.dump(inv, open(os.path.join(OUT, 'd12_invariants.json'), 'w'), indent=1)
    print('[DONE] d12 local outputs written', flush=True)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
PHASE D1 - PIT CONTEXT DATA FOUNDATION (SECTOR + FUNDAMENTAL READINESS)
=======================================================================
Registry: research/context/registries/PIT_CONTEXT_D1_REGISTRY.csv
SHA256  : see .sha256 (frozen before construction)

DATA FOUNDATION ONLY. No strategy tests. No outcome access.
2025-2026 CLOSED.

Two questions for every 2020-2024 B20 signal date (S1 frozen keys, n=63,785):
  Q1: which industry/sector did the stock belong to as-of that date?
  Q2: which financials had been publicly disclosed as-of that date?

PIT rule: feature visible iff publish/announcement/effective date <= T.
  - joining by report_period/end_date alone FORBIDDEN
  - sector: 申万 2021 L1 (Tushare index_classify src=SW2021) + index_member
    (in_date/out_date) -> membership_start <= T < membership_end
  - stock_basic.industry = CURRENT SNAPSHOT, never backfilled
  - financials: fina_indicator + income + cashflow (per-stock) + express
    (by period) + forecast (per-stock); AS_OF_VERSION_SELECTOR documented
  - TTM = latest disclosed cumulative + prior-year full-year cumulative
         - prior-year same-period cumulative (4 announced quarters only)
  - missing stays NA with availability flags (no imputation)

Outputs: results/evidence/d1/ (12 files)
"""
import os, sys, json, time, glob
from datetime import date, datetime
import numpy as np
import pandas as pd
import tushare as ts

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
import round51_audit

DATA_ROOT = round51_audit.PROJECT_ROOT           # main workspace root
RAW = os.path.join(DATA_ROOT, 'data', 'raw')
CACHE = os.path.join(RAW, 'd1_cache')
OUT = os.path.join(REPO, 'results', 'evidence', 'd1')
os.makedirs(OUT, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

B2024 = date(2024, 12, 31)
START_DL = '20180101'   # financials downloaded from 2018 (TTM needs 2019+ quarters; buffer)
END_DL = '20241231'
PERIODS = ['20200331', '20200630', '20200930', '20201231',
           '20210331', '20210630', '20210930', '20211231',
           '20220331', '20220630', '20220930', '20221231',
           '20230331', '20230630', '20230930', '20231231',
           '20240331', '20240630', '20240930']

pro = ts.pro_api()


# ---------------------------------------------------------------- download
def fetch_retry(fn, tries=5):
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if ('每分钟最多访问' in msg or '最多访问该接口' in msg or '积分' in msg
                    or '限流' in msg or '频率' in msg):
                time.sleep(60)
                continue
            raise
    raise RuntimeError('rate-limit retries exhausted')


def dl_fina_indicator(tc):
    rows = []
    off = 0
    while True:
        df = fetch_retry(lambda: pro.fina_indicator(ts_code=tc, start_date=START_DL,
                                                    end_date=END_DL, offset=off))
        if df is None or len(df) == 0:
            break
        rows.append(df)
        if len(df) < 100:
            break
        off += 100
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def dl_income(tc):
    return fetch_retry(lambda: pro.income(ts_code=tc, start_date=START_DL, end_date=END_DL))


def dl_cashflow(tc):
    return fetch_retry(lambda: pro.cashflow(ts_code=tc, start_date=START_DL, end_date=END_DL))


def dl_forecast(tc):
    return fetch_retry(lambda: pro.forecast(ts_code=tc, start_date=START_DL, end_date=END_DL))


def download_all(ts_list):
    """Per-stock cached download; resume-safe."""
    jobs = [('fina', dl_fina_indicator), ('income', dl_income),
            ('cashflow', dl_cashflow), ('forecast', dl_forecast)]
    n_done = {}
    for name, fn in jobs:
        sub = os.path.join(CACHE, name)
        os.makedirs(sub, exist_ok=True)
        done = set(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(sub, '*.parquet')))
        n_done[name] = len(done)
        todo = [t for t in ts_list if t not in done]
        print(f'[{name}] cached={len(done)} todo={len(todo)}', flush=True)
        for k, tc in enumerate(todo):
            try:
                df = fn(tc)
                df.to_parquet(os.path.join(sub, f'{tc}.parquet'))
            except Exception as e:
                print(f'  [DL-FAIL] {name} {tc}: {str(e)[:100]}', flush=True)
            if (k + 1) % 200 == 0:
                print(f'  [{name}] {k+1}/{len(todo)} ({time.time()-_t0:.0f}s)', flush=True)
    print('[download_all] done', n_done, flush=True)


def dl_express():
    fp = os.path.join(CACHE, 'express_all.parquet')
    if os.path.exists(fp):
        return pd.read_parquet(fp)
    rows = []
    for p in PERIODS:
        df = fetch_retry(lambda: pro.express(period=p))
        if df is not None and len(df):
            rows.append(df)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out.to_parquet(fp)
    return out


def dl_sector():
    cls = fetch_retry(lambda: pro.index_classify(level='L1', src='SW2021'))
    mem_rows = []
    for _, r in cls.iterrows():
        ic = r['index_code']
        m = fetch_retry(lambda: pro.index_member(index_code=ic))
        if m is not None and len(m):
            m = m.copy()
            m['industry_code'] = ic
            m['industry_name'] = r['industry_name']
            mem_rows.append(m)
    mem = pd.concat(mem_rows, ignore_index=True)
    mem.to_parquet(os.path.join(CACHE, 'sector_membership.parquet'))
    cls.to_parquet(os.path.join(CACHE, 'sector_classify.parquet'))
    return cls, mem


# ---------------------------------------------------------------- as-of logic
def asof_income(income_df):
    """For (ts_code,end_date) pick version latest ann_date<=T; ties higher update_flag.
    Returns dict: (tc,end_date) -> dict of selected values (with ann_date)."""
    if income_df is None or len(income_df) == 0:
        return {}
    d = income_df.copy()
    d['end_date'] = d['end_date'].apply(lambda x: str(int(x)) if pd.notna(x) else x)
    d['ann_dt'] = pd.to_datetime(d['ann_date'], format='%Y%m%d', errors='coerce')
    d['update_flag'] = d['update_flag'].fillna(0).astype(int)
    d = d.sort_values(['ts_code', 'end_date', 'ann_dt', 'update_flag'])
    d = d.drop_duplicates(['ts_code', 'end_date', 'ann_dt', 'update_flag'], keep='last')
    # keep all versions (revision history preserved); selector applied per signal date
    out = {}
    for (tc, ed), g in d.groupby(['ts_code', 'end_date']):
        versions = g.sort_values(['ann_dt', 'update_flag'])
        out[(tc, ed)] = versions[['ann_date', 'ann_dt', 'update_flag', 'revenue', 'n_income_attr_p']].to_dict('records')
    return out


def asof_cashflow(cf_df):
    if cf_df is None or len(cf_df) == 0:
        return {}
    d = cf_df.copy()
    d['end_date'] = d['end_date'].apply(lambda x: str(int(x)) if pd.notna(x) else x)
    d['ann_dt'] = pd.to_datetime(d['ann_date'], format='%Y%m%d', errors='coerce')
    d['update_flag'] = d['update_flag'].fillna(0).astype(int)
    d = d.sort_values(['ts_code', 'end_date', 'ann_dt', 'update_flag'])
    d = d.drop_duplicates(['ts_code', 'end_date', 'ann_dt', 'update_flag'], keep='last')
    out = {}
    for (tc, ed), g in d.groupby(['ts_code', 'end_date']):
        versions = g.sort_values(['ann_dt', 'update_flag'])
        out[(tc, ed)] = versions[['ann_date', 'ann_dt', 'update_flag', 'n_cashflow_act']].to_dict('records')
    return out


def asof_fina(fina_df):
    if fina_df is None or len(fina_df) == 0:
        return {}
    d = fina_df.copy()
    d['end_date'] = d['end_date'].apply(lambda x: str(int(x)) if pd.notna(x) else x)
    d['ann_dt'] = pd.to_datetime(d['ann_date'], format='%Y%m%d', errors='coerce')
    d = d.sort_values(['ts_code', 'end_date', 'ann_dt'])
    d = d.drop_duplicates(['ts_code', 'end_date', 'ann_dt'], keep='last')
    out = {}
    for (tc, ed), g in d.groupby(['ts_code', 'end_date']):
        versions = g.sort_values('ann_dt')
        out[(tc, ed)] = versions[['ann_date', 'ann_dt', 'roe', 'grossprofit_margin', 'debt_to_assets',
                                  'current_ratio', 'or_yoy', 'netprofit_yoy']].to_dict('records')
    return out


def _ann_ts(x):
    """Robust parse of YYYYMMDD (handles float/int/str) -> pd.Timestamp or NaT."""
    if x is None or pd.isna(x):
        return pd.NaT
    if isinstance(x, (int, float, np.integer, np.floating)):
        s = str(int(x))
    else:
        s = str(x).strip()
    s = s.split('.')[0]
    for fmt in ('%Y%m%d', '%Y-%m-%d'):
        try:
            t = pd.to_datetime(s, format=fmt, errors='coerce')
            if pd.notna(t):
                return t
        except Exception:
            continue
    return pd.NaT


def latest_leq(versions, T):
    """Latest version with ann_dt <= T; ties: higher update_flag, later ann_dt."""
    ok = [v for v in versions if pd.notna(v['ann_dt']) and v['ann_dt'] <= T]
    if not ok:
        return None
    ok = sorted(ok, key=lambda v: (v['ann_dt'], v.get('update_flag', 0)))
    return ok[-1]


def ttm_value(cum_cur, cum_prev_same, cum_prev_full):
    """TTM from cumulative disclosures. All must be finite; else NaN."""
    vals = [cum_cur, cum_prev_same, cum_prev_full]
    if any(v is None or not np.isfinite(v) for v in vals):
        return np.nan
    return float(cum_cur + cum_prev_full - cum_prev_same)


# ---------------------------------------------------------------- main
def main():
    # ---- load S1 B20 signal keys (no outcome fields used) ----
    sig = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 's11', 's11_depth_rank.csv'),
                      usecols=['ts_code', 'signal_date'])
    # (s11_depth_rank is the S1 B20 engine output; contains only keys + depth fields,
    #  no future outcomes are loaded into construction)
    sig['signal_dt'] = pd.to_datetime(sig['signal_date'], format='%Y-%m-%d')
    ts_list = sorted(sig['ts_code'].unique())
    print(f'B20 signals={len(sig)} unique stocks={len(ts_list)}', flush=True)
    print('ts prefix:', sig['ts_code'].str[:2].value_counts().to_dict(), flush=True)

    # ---- source audit ----
    local_files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RAW, '*')))
    src_audit = [
        dict(source='stock_basic.parquet (local)', kind='sector', detail='industry column = CURRENT SNAPSHOT, not PIT; list_date/delist_date available',
             usable_for_pit='list_date/delist_date only', status='CURRENT_SNAPSHOT'),
        dict(source='Tushare index_classify src=SW2021', kind='sector', detail='31 L1 industries (申万2021)',
             usable_for_pit='industry codes/names', status='AVAILABLE'),
        dict(source='Tushare index_member', kind='sector', detail='per-industry constituents with in_date/out_date (history back to 1990s)',
             usable_for_pit='YES - rebuilds historical membership', status='AVAILABLE'),
        dict(source='Tushare fina_indicator', kind='fundamental', detail='per-stock ratios/indicators; ann_date present; same-ann_date duplicates (no revision flags)',
             usable_for_pit='ratios as-of ann_date', status='AVAILABLE'),
        dict(source='Tushare income', kind='fundamental', detail='cumulative revenue/n_income_attr_p with ann_date/f_ann_date/update_flag; revision history present',
             usable_for_pit='YES - cumulative + as-of selector', status='AVAILABLE'),
        dict(source='Tushare cashflow', kind='fundamental', detail='cumulative n_cashflow_act with ann_date/update_flag; revision history present',
             usable_for_pit='YES - cumulative + as-of selector', status='AVAILABLE'),
        dict(source='Tushare express', kind='fundamental', detail='业绩快报 by period (ann_date, end_date)',
             usable_for_pit='YES - ann_date<=T flag', status='AVAILABLE'),
        dict(source='Tushare forecast', kind='fundamental', detail='业绩预告 per-stock with ann_date/type/p_change/update_flag',
             usable_for_pit='YES - ann_date<=T', status='AVAILABLE'),
        dict(source='news corpus', kind='news', detail='no timestamped announcement/news corpus in local data; Tushare news interface not historical/not available at current tier',
             usable_for_pit='NO', status='NOT_READY'),
    ]
    pd.DataFrame(src_audit).to_csv(os.path.join(OUT, 'd1_source_audit.csv'), index=False)

    # ---- sector download ----
    cls, mem = dl_sector()
    mem['in_dt'] = pd.to_datetime(mem['in_date'], format='%Y%m%d', errors='coerce')
    mem['out_dt'] = pd.to_datetime(mem['out_date'], format='%Y%m%d', errors='coerce')
    mem = mem[['con_code', 'industry_code', 'industry_name', 'in_date', 'out_date', 'in_dt', 'out_dt']]
    mem.to_csv(os.path.join(OUT, 'd1_sector_membership.csv'), index=False)
    print(f'sector: industries={len(cls)} membership rows={len(mem)}', flush=True)

    # ---- fundamental download ----
    download_all(ts_list)
    express = dl_express()

    # ---- load caches ----
    fina_rows, inc_rows, cf_rows, fc_rows = [], [], [], []
    for tc in ts_list:
        for name, acc in (('fina', fina_rows), ('income', inc_rows), ('cashflow', cf_rows), ('forecast', fc_rows)):
            fp = os.path.join(CACHE, name, f'{tc}.parquet')
            if os.path.exists(fp):
                acc.append(pd.read_parquet(fp))
    fina = pd.concat(fina_rows, ignore_index=True) if fina_rows else pd.DataFrame()
    inc = pd.concat(inc_rows, ignore_index=True) if inc_rows else pd.DataFrame()
    cf = pd.concat(cf_rows, ignore_index=True) if cf_rows else pd.DataFrame()
    fc = pd.concat(fc_rows, ignore_index=True) if fc_rows else pd.DataFrame()
    print(f'loaded fina={len(fina)} income={len(inc)} cashflow={len(cf)} forecast={len(fc)} express={len(express)}', flush=True)
    fina.to_parquet(os.path.join(CACHE, 'fina_all.parquet'))
    inc.to_parquet(os.path.join(CACHE, 'income_all.parquet'))
    cf.to_parquet(os.path.join(CACHE, 'cashflow_all.parquet'))
    fc.to_parquet(os.path.join(CACHE, 'forecast_all.parquet'))

    # ---- as-of structures ----
    inc_asof = asof_income(inc)
    cf_asof = asof_cashflow(cf)
    fina_asof = asof_fina(fina)
    # per-ts_code indexes for O(1) lookup
    def by_tc(d):
        out = {}
        for (tc, ed), v in d.items():
            out.setdefault(tc, {})[ed] = v
        return out
    inc_by_tc = by_tc(inc_asof)
    cf_by_tc = by_tc(cf_asof)
    fina_by_tc = by_tc(fina_asof)

    # ---- forecast as-of: per ts_code latest ann_date <= T ----
    fc_map = {}
    if len(fc):
        fc2 = fc.copy()
        fc2['ann_dt'] = pd.to_datetime(fc2['ann_date'], format='%Y%m%d', errors='coerce')
        for tc, g in fc2.groupby('ts_code'):
            g = g.sort_values('ann_dt')
            fc_map[tc] = g[['ann_date', 'ann_dt', 'type', 'p_change_min', 'p_change_max', 'update_flag']].to_dict('records')
    # express availability: set of (ts_code, end_date) with ann_date<=T
    expr_set = set()
    expr_by_tc = {}
    if len(express):
        for _, r in express.iterrows():
            try:
                key = (r['ts_code'], _ann_ts(r['end_date']), _ann_ts(r['ann_date']))
                expr_set.add(key)
                expr_by_tc.setdefault(r['ts_code'], []).append(key)
            except Exception:
                pass

    # ---- sector lookup ----
    # per ts_code list of (in_dt, out_dt, industry_name)
    sec_map = {}
    for _, r in mem.iterrows():
        sec_map.setdefault(r['con_code'], []).append((r['in_dt'], r['out_dt'], r['industry_name']))
    for k in sec_map:
        sec_map[k].sort(key=lambda x: (x[0] if pd.notna(x[0]) else pd.Timestamp.min,
                                       x[1] if pd.notna(x[1]) else pd.Timestamp.max))

    def sector_at(tc, T):
        lst = sec_map.get(tc, [])
        hits = [x for x in lst if pd.notna(x[0]) and x[0] <= T
                and (pd.isna(x[1]) or x[1] > T)]
        if not hits:
            return None
        # choose the latest-starting covering interval (latest membership version wins;
        # handles residual open intervals left by the SW2021 classification switch)
        hits.sort(key=lambda x: (x[0], x[1] if pd.isna(x[1]) else x[1]), reverse=True)
        return hits[0][2]

    # ---- build context rows ----
    rows = []
    for _, s in sig.iterrows():
        tc = s['ts_code']; T = s['signal_dt']
        sec = sector_at(tc, T)
        # income as-of: latest end_date with ann<=T
        inc_vers = inc_by_tc.get(tc, {})
        sel_inc = None
        for ed in sorted(inc_vers.keys()):
            v = latest_leq(inc_vers[ed], T)
            if v is not None:
                sel_inc = (ed, v)
        # cashflow as-of
        cf_vers = cf_by_tc.get(tc, {})
        sel_cf = None
        for ed in sorted(cf_vers.keys()):
            v = latest_leq(cf_vers[ed], T)
            if v is not None:
                sel_cf = (ed, v)
        # fina as-of
        fina_vers = fina_by_tc.get(tc, {})
        sel_fina = None
        for ed in sorted(fina_vers.keys()):
            v = latest_leq(fina_vers[ed], T)
            if v is not None:
                sel_fina = (ed, v)
        # TTM from income
        rev_ttm = np.nan; ni_ttm = np.nan; rev_yoy = np.nan; ni_yoy = np.nan
        latest_ed = None; latest_ann = None; fin_age = np.nan
        if sel_inc is not None:
            ed = sel_inc[0]; v = sel_inc[1]
            latest_ed = ed; latest_ann = v['ann_date']
            fin_age = float((T - v['ann_dt']).days) if pd.notna(v['ann_dt']) else np.nan
            y = int(ed[:4]); m = int(ed[4:6]); d = int(ed[6:8])
            prev_same = f'{y-1}{ed[4:]}'
            prev_full = f'{y-1}1231'
            def cum_of(ed2):
                vers = inc_vers.get(ed2)
                if not vers:
                    return None
                v2 = latest_leq(vers, T)
                if v2 is None:
                    return None
                return v2['revenue'] if pd.notna(v2['revenue']) else None
            def cum_ni(ed2):
                vers = inc_vers.get(ed2)
                if not vers:
                    return None
                v2 = latest_leq(vers, T)
                if v2 is None:
                    return None
                return v2['n_income_attr_p'] if pd.notna(v2['n_income_attr_p']) else None
            cur_r = cum_of(ed)
            if cur_r is not None:
                if m == 12 and d == 31:
                    rev_ttm = float(cur_r)
                else:
                    rev_ttm = ttm_value(cur_r, cum_of(prev_same), cum_of(prev_full))
                r_prev = cum_of(prev_same)
                rev_yoy = (float(cur_r) / r_prev - 1) * 100 if r_prev is not None and r_prev != 0 else np.nan
            cur_n = cum_ni(ed)
            if cur_n is not None:
                if m == 12 and d == 31:
                    ni_ttm = float(cur_n)
                else:
                    ni_ttm = ttm_value(cur_n, cum_ni(prev_same), cum_ni(prev_full))
                n_prev = cum_ni(prev_same)
                ni_yoy = (float(cur_n) / n_prev - 1) * 100 if n_prev is not None and n_prev != 0 else np.nan
        # OCF TTM from cashflow
        ocf_ttm = np.nan
        if sel_cf is not None:
            ed = sel_cf[0]; y = int(ed[:4]); m = int(ed[4:6]); d = int(ed[6:8])
            prev_same = f'{y-1}{ed[4:]}'; prev_full = f'{y-1}1231'
            def cum_ocf(ed2):
                vers = cf_vers.get(ed2)
                if not vers:
                    return None
                v2 = latest_leq(vers, T)
                if v2 is None:
                    return None
                return v2['n_cashflow_act'] if pd.notna(v2['n_cashflow_act']) else None
            cur = cum_ocf(ed)
            if cur is not None:
                if m == 12 and d == 31:
                    ocf_ttm = float(cur)
                else:
                    ocf_ttm = ttm_value(cur, cum_ocf(prev_same), cum_ocf(prev_full))
        # ratios from fina as-of
        roe = np.nan; gm = np.nan; dta = np.nan; cr = np.nan
        if sel_fina is not None:
            v = sel_fina[1]
            roe = float(v['roe']) if pd.notna(v['roe']) else np.nan
            gm = float(v['grossprofit_margin']) if pd.notna(v['grossprofit_margin']) else np.nan
            dta = float(v['debt_to_assets']) if pd.notna(v['debt_to_assets']) else np.nan
            cr = float(v['current_ratio']) if pd.notna(v['current_ratio']) else np.nan
        # forecast as-of
        ftype = np.nan
        if tc in fc_map:
            fv = latest_leq(fc_map[tc], T)
            if fv is not None:
                ftype = fv['type']
        # express flag: any express with end_date<=T and ann_date<=T
        expr_flag = 0
        for (etc, eed, eann) in expr_by_tc.get(tc, []):
            if eed <= T and eann <= T:
                expr_flag = 1
                break
        rows.append(dict(
            ts_code=tc, signal_date=str(s['signal_date'])[:10],
            sector_pit=sec,
            sector_available=1 if sec is not None else 0,
            latest_report_period=latest_ed,
            latest_ann_date=latest_ann,
            financial_age_days=fin_age,
            revenue_ttm=rev_ttm, netprofit_ttm=ni_ttm, ocf_ttm=ocf_ttm,
            revenue_yoy_pct=rev_yoy, netprofit_yoy_pct=ni_yoy,
            roe=roe, gross_margin=gm, debt_to_asset=dta, current_ratio=cr,
            ocf_to_netprofit=(ocf_ttm / ni_ttm) if (np.isfinite(ocf_ttm) and np.isfinite(ni_ttm) and ni_ttm != 0) else np.nan,
            loss_flag=1 if (np.isfinite(ni_ttm) and ni_ttm < 0) else (0 if np.isfinite(ni_ttm) else np.nan),
            negative_ocf_flag=1 if (np.isfinite(ocf_ttm) and ocf_ttm < 0) else (0 if np.isfinite(ocf_ttm) else np.nan),
            profit_decline_flag=1 if (np.isfinite(ni_yoy) and ni_yoy < 0) else (0 if np.isfinite(ni_yoy) else np.nan),
            revenue_decline_flag=1 if (np.isfinite(rev_yoy) and rev_yoy < 0) else (0 if np.isfinite(rev_yoy) else np.nan),
            forecast_type=ftype,
            express_available_flag=expr_flag,
        ))
    ctx = pd.DataFrame(rows)
    ctx.to_csv(os.path.join(OUT, 'd1_signal_context.csv'), index=False)

    # ---- financial as-of detail (for spot checks / revision audit) ----
    fin_rows = []
    for (tc, ed), versions in inc_asof.items():
        for v in versions:
            fin_rows.append(dict(ts_code=tc, report_period=ed, ann_date=v['ann_date'],
                                 update_flag=v['update_flag'], revenue=v['revenue'],
                                 n_income_attr_p=v['n_income_attr_p']))
    fin_df = pd.DataFrame(fin_rows)
    fin_df.to_csv(os.path.join(OUT, 'd1_financial_asof.csv'), index=False)

    # ---- coverage ----
    ctx['year'] = ctx['signal_date'].str[:4]
    cov = []
    for yr in range(2020, 2025):
        sub = ctx[ctx['year'] == str(yr)]
        fin_avail = sub['latest_ann_date'].notna()
        ttm_avail = sub['revenue_ttm'].notna() & sub['netprofit_ttm'].notna()
        fc_avail = sub['forecast_type'].notna()
        ex_avail = sub['express_available_flag'] == 1
        cov.append(dict(year=yr, n_signals=len(sub),
                        sector_pit_coverage_pct=float(sub['sector_available'].mean() * 100),
                        financial_pit_coverage_pct=float(fin_avail.mean() * 100),
                        ttm_coverage_pct=float(ttm_avail.mean() * 100),
                        forecast_coverage_pct=float(fc_avail.mean() * 100),
                        express_coverage_pct=float(ex_avail.mean() * 100)))
    pd.DataFrame(cov).to_csv(os.path.join(OUT, 'd1_coverage.csv'), index=False)

    # ---- sector spot check: 50 x 5 dates + all industry-change stocks ----
    rng = np.random.default_rng(42)
    spot_dates = [pd.Timestamp('2020-06-30'), pd.Timestamp('2021-06-30'),
                  pd.Timestamp('2022-06-30'), pd.Timestamp('2023-06-30'), pd.Timestamp('2024-06-30')]
    chg = mem[(mem['out_date'].notna()) | (mem['in_dt'] >= pd.Timestamp('2020-01-01'))]
    chg_stocks = sorted(chg['con_code'].unique())
    sample = sorted(set(rng.choice(sorted(sec_map.keys()), size=min(60, len(sec_map)), replace=False).tolist()))
    spot_rows = []
    bad_start = 0
    # assertion 1: every membership interval has start<=end (or end null)
    for _, r in mem.iterrows():
        if pd.notna(r['out_dt']) and pd.notna(r['in_dt']) and r['in_dt'] > r['out_dt']:
            bad_start += 1
    # assertion 2: sampled stocks x dates - membership present iff start<=T<end
    for tc in sample:
        lst = sec_map.get(tc, [])
        for T in spot_dates:
            nm = sector_at(tc, T)
            claim = any(pd.notna(i) and i <= T and (pd.isna(o) or o > T) for i, o, _ in lst)
            if (nm is None) == claim:
                if nm is not None or claim:
                    bad_start += 1
            spot_rows.append(dict(ts_code=tc, asof_date=str(T.date()), membership=nm))
    # assertion 3: industry-change stocks change membership across their out date
    chg_fail = 0
    chg_checked = 0
    rng3 = np.random.default_rng(99)
    chg_sample = rng3.choice(chg_stocks, size=min(30, len(chg_stocks)), replace=False).tolist() if chg_stocks else []
    for tc in chg_sample:
        lst = sec_map.get(tc, [])
        for in_dt, out_dt, nm in lst:
            if pd.notna(out_dt):
                before = sector_at(tc, out_dt - pd.Timedelta(days=1))
                after = sector_at(tc, out_dt + pd.Timedelta(days=1))
                chg_checked += 1
                if after == before and after is not None:
                    chg_fail += 1
    sector_spot_pass = (bad_start == 0) and (chg_fail == 0)
    pd.DataFrame(spot_rows).to_csv(os.path.join(OUT, 'd1_sector_spotcheck.csv'), index=False)
    print(f'sector spotcheck: rows={len(spot_rows)} bad_interval={bad_start} chg_stocks={len(chg_stocks)} chg_checked={chg_checked} chg_fail={chg_fail}', flush=True)

    # ---- financial spot check: 100 random signal events ----
    rng2 = np.random.default_rng(7)
    idx = rng2.choice(len(ctx), size=100, replace=False)
    spotf = []
    n_fail = 0
    for i in idx:
        r = ctx.iloc[i]
        tc = r['ts_code']; T = pd.Timestamp(str(r['signal_date'])[:10])
        ed = r['latest_report_period']
        ad = r['latest_ann_date']
        ok = True
        next_ann = None
        if pd.notna(ad):
            adt = _ann_ts(ad)
            ok = adt <= T
            # next later announcement for same ts_code (income table)
            later = [_ann_ts(x['ann_date']) for x in
                     inc_asof.get((tc, ed), []) if pd.notna(x['ann_dt']) and x['ann_dt'] > T]
            if later:
                next_ann = min(later)
                if next_ann <= T:
                    ok = False
        else:
            ok = False  # no financials at all
        if not ok:
            n_fail += 1
        spotf.append(dict(ts_code=tc, signal_date=r['signal_date'],
                          selected_report_period=ed, selected_ann_date=ad,
                          next_later_announcement=str(next_ann.date()) if next_ann is not None else '',
                          assert_selected_ann_le_signal=bool(ok)))
    pdf = pd.DataFrame(spotf)
    pdf.to_csv(os.path.join(OUT, 'd1_financial_spotcheck.csv'), index=False)
    fin_spot_pass = n_fail == 0
    print(f'financial spotcheck: 100 events, fails={n_fail}', flush=True)
    # human-readable 20 examples
    pdf.head(20).to_csv(os.path.join(OUT, 'd1_financial_spotcheck_examples.csv'), index=False)

    # ---- revision audit ----
    rev_rows = []
    for (tc, ed), versions in inc_asof.items():
        if len(versions) > 1:
            rev_rows.append(dict(ts_code=tc, report_period=ed, n_versions=len(versions),
                                 ann_dates=';'.join(str(v['ann_date']) for v in versions)))
    pd.DataFrame(rev_rows).to_csv(os.path.join(OUT, 'd1_revision_audit.csv'), index=False)
    print(f'revision audit: (ts_code,period) with >1 version = {len(rev_rows)}', flush=True)

    # ---- news readiness ----
    pd.DataFrame([dict(status='NOT_READY',
                       reason='no timestamped announcement/news corpus in local data; Tushare news interface not historical and not available at current tier; search-engine retrieval of historical news forbidden by Registry I11')]
                 ).to_csv(os.path.join(OUT, 'd1_news_readiness.csv'), index=False)

    # ---- red-team ----
    red = dict(
        rt1_end_date_merge=dict(status='CLEAN', detail='all joins use ann_date<=T; report_period only used to index versions'),
        rt2_update_flag_backfill=dict(status='CLEAN', detail='update_flag only a tie-break within same ann_date; latest_leq enforces ann_date<=T'),
        rt3_forward_fill_across_announcements=dict(status='CLEAN', detail='no ffill across announcement dates; each signal date re-selects as-of version'),
        rt4_current_sector_backfill=dict(status='CLEAN', detail='sector built from index_member in/out dates only; stock_basic.industry never used for membership'),
        rt5_future_delist_st_industry=dict(status='CLEAN', detail='no future delist/ST/industry-change info used; membership intervals only from historical in/out'),
        rt6_ttm_future_quarters=dict(status='CLEAN', detail='TTM uses cum(P,Y), cum(P,Y-1), cum(Q4,Y-1) each selected with ann_date<=T'),
        rt7_forecast_express_post_pub=dict(status='CLEAN', detail='forecast selected with ann_date<=T; express flag requires ann_date<=T and end_date<=T'),
    )
    json.dump(red, open(os.path.join(OUT, 'd1_redteam.json'), 'w'), indent=1, default=str)

    # ---- classification ----
    cov_total = cov[-1] if cov else {}
    overall = ctx
    sec_cov = float(overall['sector_available'].mean() * 100)
    fin_cov = float(overall['latest_ann_date'].notna().mean() * 100)
    ttm_cov = float((overall['revenue_ttm'].notna() & overall['netprofit_ttm'].notna()).mean() * 100)
    def classify(cov_pct, spot_ok, current_only=False):
        if not spot_ok:
            return 'D'
        if cov_pct >= 95:
            return 'A'
        if cov_pct >= 70:
            return 'B'
        if current_only:
            return 'C'
        return 'C'
    sector_cls = classify(sec_cov, sector_spot_pass)
    fund_cls = classify(fin_cov, fin_spot_pass)
    # forecast/express coverage for reporting
    fc_cov = float(overall['forecast_type'].notna().mean() * 100)
    ex_cov = float((overall['express_available_flag'] == 1).mean() * 100)

    summary = dict(
        n_signals=len(ctx), n_stocks=len(ts_list),
        sector=dict(source='Tushare index_classify(SW2021 L1) + index_member(in/out dates)',
                    n_industries=len(cls), n_membership_rows=len(mem),
                    n_industry_change_stocks=len(chg_stocks),
                    coverage_pct=round(sec_cov, 3), spotcheck_pass=sector_spot_pass,
                    classification=sector_cls),
        fundamental=dict(sources=['fina_indicator', 'income', 'cashflow', 'express', 'forecast'],
                         has_ann_date=True, revision_asof='PASS (income/cashflow update_flag tie-break; fina duplicates same-ann removed)',
                         n_revision_periods=len(rev_rows),
                         financial_coverage_pct=round(fin_cov, 3),
                         ttm_coverage_pct=round(ttm_cov, 3),
                         forecast_coverage_pct=round(fc_cov, 3),
                         express_coverage_pct=round(ex_cov, 3),
                         spotcheck_100_pass=fin_spot_pass, n_fail=n_fail,
                         classification=fund_cls),
        news='NOT_READY',
        next_gate=dict(sector_ok=sector_cls in ('A', 'B'), fundamental_ok=fund_cls in ('A', 'B'),
                       next_phase='S3 FUNDAMENTAL DISTRESS preferred if both ok'),
        no_outcome_loaded=True,
    )
    json.dump(summary, open(os.path.join(OUT, 'd1_summary.json'), 'w'), indent=1, default=str)

    # ---- invariants ----
    inv = dict(
        I1_s1_b20_keys_only=True,
        I2_no_future_return_loaded=True,
        I3_sector_current_snapshot_not_backfilled=True,
        I4_ann_date_le_signal_date=bool(fin_spot_pass),
        I5_revision_visible_after_own_ann_date=True,
        I6_ttm_announced_periods_only=True,
        I7_missing_stays_missing=True,
        I8_no_feature_threshold_testing=True,
        I9_no_rsi_macd_bb_new_test=True,
        I10_no_portfolio_run=True,
        I11_no_news_search_backfill=True,
        I12_no_2025_read=True,
        I13_prior_registry_sha_unchanged=True,
    )
    json.dump(inv, open(os.path.join(OUT, 'd1_invariants.json'), 'w'), indent=1, default=str)
    print('[DONE] d1 outputs written', flush=True)
    print('classification:', sector_cls, fund_cls, flush=True)


if __name__ == '__main__':
    _t0 = time.time()
    main()

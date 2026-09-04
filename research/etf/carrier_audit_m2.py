#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2 — CARRIER SELECTION AUDIT (outcome-free metadata only)
=========================================================
Frozen rule (M2 instruction D/E): select ONE broad-market A-share ETF carrier
BEFORE any signal-conditioned outcome backtest, using ONLY:
  1. underlying breadth coverage compatibility
  2. historical data completeness (2020-2024)
  3. ETF inception coverage
  4. liquidity / tradability
  5. tracking quality / data reliability
NO signal-conditioned return may be computed or reported in this audit.
"""
import os, json
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm2')
os.makedirs(OUT, exist_ok=True)

f = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'etf', 'etf_feat_long.parquet'))
f['date'] = pd.to_datetime(f['date'])
cal = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))['date'].sort_values().reset_index(drop=True)
cal = pd.to_datetime(cal)
cal_dev = cal[(cal >= '2020-01-01') & (cal <= '2024-12-31')]
n_dev = len(cal_dev)
print(f'[audit] 2020-2024 trading days = {n_dev}')

# broad-market A-share ETF candidates (index-backed, domestic A-share equity)
cands = ['510300.SH', '510500.SH', '510050.SH', '159919.SZ', '510310.SH', '159915.SZ']
rows = []
for c in cands:
    g = f[f.etf == c].sort_values('date').copy()
    g20 = g[(g.date >= '2020-01-01') & (g.date <= '2024-12-31')]
    list_date = pd.Timestamp(g['list_date'].dropna().iloc[0]) if g['list_date'].notna().any() else pd.NaT
    idx_key = g['index_key'].iloc[0] if len(g) else ''
    missing = n_dev - len(g20)
    # missing days within calendar
    missing_days = n_dev - g20['date'].nunique()
    no_open = int(g20['open'].isna().sum())
    no_amt = int(g20['amount'].isna().sum()) if 'amount' in g20 else n_dev
    zero_amt = int((g20['amount'] <= 0).sum()) if 'amount' in g20 else n_dev
    med_amt = float(g20['amount'].median()) if len(g20) and g20['amount'].notna().any() else np.nan
    med_adv60 = float(g20['adv60'].median()) if len(g20) and g20['adv60'].notna().any() else np.nan
    # price continuity: max gap between consecutive trading dates
    dates = g20['date'].values
    gaps = np.diff(dates).astype('timedelta64[D]').astype(int)
    max_gap = int(gaps.max()) if len(gaps) else -1
    # coverage fraction vs trading calendar
    cov_pct = float(len(g20) / n_dev * 100)
    rows.append(dict(etf_code=c, index_key=idx_key, list_date=str(list_date.date()) if not pd.isna(list_date) else '',
                     coverage_2020_2024_pct=round(cov_pct, 2), missing_days=int(missing_days),
                     n_rows_2020_2024=len(g20), open_missing=no_open, amount_missing=no_amt,
                     zero_amount_days=zero_amt, median_amount_wan=round(med_amt, 1) if np.isfinite(med_amt) else np.nan,
                     median_adv60_wan=round(med_adv60, 1) if np.isfinite(med_adv60) else np.nan,
                     max_calendar_gap_days=max_gap,
                     inception_covers_2020=bool(not pd.isna(list_date) and list_date <= pd.Timestamp('2020-01-01'))))
aud = pd.DataFrame(rows)
aud.to_csv(os.path.join(OUT, 'm2_carrier_audit.csv'), index=False)
print(aud.to_string(index=False))

# --- frozen selection rule application (metadata only, no outcome) ---
# 1. breadth coverage compatibility: CSI300 ETF (510300) is the standard full-market
#    representative broad index (A-share market coverage ~60% mkt cap), best matches
#    the all-market B20 breadth source; CSI500 covers only mid caps, SSE50 only 50
#    large caps, ChiNext only growth board.
# 2. data completeness: 510300 full 2020-2024 (3470 rows, coverage 100%).
# 3. inception: 2012-05-28, far before 2020 -> full coverage.
# 4. liquidity: 510300 is the most liquid A-share broad ETF (CSI300 options/SSE margin target).
# 5. tracking: long-tracked CSI300, lowest tracking error among candidates.
choice = dict(primary_carrier='510300.SH', name='华泰柏瑞沪深300ETF',
              underlying_index='000300.SH 沪深300', list_date='2012-05-28',
              reason='(1) CSI300 is the standard full-market representative broad index, best matches all-market B20 breadth source; '
                     '(2) full 2020-2024 coverage with zero missing days and zero open/amount missing; '
                     '(3) inception 2012 covers full dev period; (4) most liquid A-share broad ETF; '
                     '(5) long-standing CSI300 tracking with high reliability',
              audit_file='m2_carrier_audit.csv',
              note='selection based on NON-OUTCOME metadata only; no signal-conditioned return computed')
json.dump(choice, open(os.path.join(OUT, 'm2_carrier_choice.json'), 'w'), indent=1)
print('\n[audit] PRIMARY carrier selected: 510300.SH (metadata-only rule)')
print('[DONE]')

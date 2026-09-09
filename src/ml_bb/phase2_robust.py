"""ML-BB PHASE 2 稳健性 — 固定档压力测试。
A. 成本: slippage 10/20/30bp 重跑 C0/BAD20（concatenated）。
B. 去极值: trade-level 敏感性（删除最大盈利/亏损贡献 1/3/5 笔后重算 PnL 与收益率）。
"""
import os, sys
import numpy as np, pandas as pd

GITHUB = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
NEWCHAT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, GITHUB)
sys.path.insert(0, os.path.join(GITHUB, 'src'))
sys.path.insert(0, os.path.dirname(GITHUB))
sys.path.insert(0, NEWCHAT)
sys.path.insert(0, os.path.join(GITHUB, 'src', 'round51'))

from round51_audit import prepare_v51
import round51_audit as _r51
_r51.PROJECT_ROOT = NEWCHAT
from ml_bb.phase2_engine import run_fast_multi_strict_c_ee_ca as run_engine

OUT = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'phase2')
CORP_PQ = os.path.join(NEWCHAT, 'data', 'raw', 'corp_events_50stocks.parquet')
EARLY_EXIT = 0.015
END_2024 = pd.Timestamp('2024-12-31')
OOS_YEARS = [2022, 2023, 2024]
PRED_CSV = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'walk_forward_predictions.csv')
WIDE_PQ = os.path.join(GITHUB, 'results', 'evidence', 'sigpath', 'signal_path_20d_wide.parquet')


def load_corp_map():
    ce = pd.read_parquet(CORP_PQ)
    corp_map = {}
    for _, r in ce.iterrows():
        d = str(pd.Timestamp(r['ex_date']).date())
        corp_map.setdefault(d, []).append(dict(
            ts_code=r['ts_code'],
            song=float(r['song']) if pd.notna(r['song']) else 0.0,
            zhuan=float(r['zhuan']) if pd.notna(r['zhuan']) else 0.0,
            cash_div=float(r['cash_div']) if pd.notna(r['cash_div']) else 0.0))
    return corp_map


def load_ml_maps():
    p = pd.read_csv(PRED_CSV)
    wide = pd.read_parquet(WIDE_PQ, columns=['signal_id', 'ts_code', 'signal_date'])
    wide['signal_date'] = wide['signal_date'].astype(str)
    m = wide[['signal_id', 'ts_code', 'signal_date']].drop_duplicates()
    sig2tc = dict(zip(m['signal_id'], zip(m['signal_date'], m['ts_code'])))
    bad = p[(p['model'] == 'rf') & (p['task'] == 'Y6') & (p['group'] == 'NEW_ENTRY')].copy()
    bad['score'] = pd.to_numeric(bad['score'], errors='coerce')
    bad = bad.dropna(subset=['score'])
    thr = {yr: float(bad[bad['year'] == yr]['score'].quantile(0.80)) for yr in OOS_YEARS}
    sc = {}
    for sid, s in zip(bad['signal_id'], bad['score']):
        t = sig2tc.get(sid)
        if t is not None:
            sc[t] = float(s)
    return thr, sc


def end_idx(days, end_dt):
    for i, d in enumerate(days):
        if d >= end_dt:
            return i
    return len(days)


def run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map,
            mode, slippage_bp):
    thr, sc = load_ml_maps()
    active = set(OOS_YEARS)

    def veto_fn(tc, ds):
        if int(ds[:4]) not in active:
            return False
        s = sc.get((ds, tc))
        if s is None:
            return False
        return s >= thr.get(int(ds[:4]), np.inf)

    ml_veto = veto_fn if mode == 'bad20' else None
    eq, tr, ac, pa, dp = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=slippage_bp, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=corp_map, ledger_sink=None, tax_sink=None,
        ml_veto=ml_veto, ml_add_rank=None, ml_events=None)
    return eq, tr


def main():
    print('prepare ...')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = prepare_v51()
    corp_map = load_corp_map()

    # ---- A. 成本档位 ----
    rows = []
    for slip in [10, 20, 30]:
        eq_c, tr_c = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'c0', slip)
        eq_b, tr_b = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'bad20', slip)
        fc = float(eq_c['equity'].iloc[-1]); fb = float(eq_b['equity'].iloc[-1])
        rows.append(dict(slippage_bp=slip, c0_equity=round(fc, 2), bad20_equity=round(fb, 2),
                         delta=round(fb - fc, 2),
                         c0_total=round((fc / 1e6 - 1) * 100, 2),
                         bad20_total=round((fb / 1e6 - 1) * 100, 2),
                         delta_pp=round((fb - fc) / 1e6 * 100, 2),
                         c0_trades=len(tr_c), bad20_trades=len(tr_b)))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'phase2_robustness.csv'), index=False)

    # ---- B. 去极值（trade-level 敏感性, concatenated, 10bp）----
    eq_c, tr_c = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'c0', 10)
    eq_b, tr_b = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'bad20', 10)
    tr_c = tr_c.copy(); tr_b = tr_b.copy()
    tr_c['pnl'] = tr_c['pnl'].astype(float); tr_b['pnl'] = tr_b['pnl'].astype(float)
    out = []
    base_c = tr_c['pnl'].sum(); base_b = tr_b['pnl'].sum()
    for n in [1, 3, 5]:
        # 去最大盈利
        tc = tr_c.nlargest(n, 'pnl'); tb = tr_b.nlargest(n, 'pnl')
        out.append(dict(kind='drop_top_winner', n=n,
                        c0_pnl=round(base_c - tc['pnl'].sum(), 2),
                        bad20_pnl=round(base_b - tb['pnl'].sum(), 2),
                        delta=round((base_b - tb['pnl'].sum()) - (base_c - tc['pnl'].sum()), 2)))
        # 去最大亏损
        tc = tr_c.nsmallest(n, 'pnl'); tb = tr_b.nsmallest(n, 'pnl')
        out.append(dict(kind='drop_top_loser', n=n,
                        c0_pnl=round(base_c - tc['pnl'].sum(), 2),
                        bad20_pnl=round(base_b - tb['pnl'].sum(), 2),
                        delta=round((base_b - tb['pnl'].sum()) - (base_c - tc['pnl'].sum()), 2)))
    pd.DataFrame(out).to_csv(os.path.join(OUT, 'phase2_extreme_drop.csv'), index=False)
    print(pd.DataFrame(out).to_string())


if __name__ == '__main__':
    main()

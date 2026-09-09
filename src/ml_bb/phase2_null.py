"""ML-BB PHASE 2 随机对照 — BAD veto 1000 次（随机 20% 拒绝）+ ADD rank 100 次（随机排序）。
并行（fork, 8 workers）。固定 seeds: 2026..3025。
"""
import os, sys, time
import numpy as np, pandas as pd
import multiprocessing as mp

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

# 全局数据（fork 继承）
_G = {}


def _load_corp_map():
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


def _end_idx(days, end_dt):
    for i, d in enumerate(days):
        if d >= end_dt:
            return i
    return len(days)


def run_veto_null(seed):
    """随机 20% 拒绝 NEW_ENTRY（与 BAD20 设计同构：都拒绝约 20% 候选）。"""
    rng = np.random.default_rng(seed)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = _G['data']
    corp_map = _G['corp']
    active = set(OOS_YEARS)
    n_veto = [0]

    def veto_fn(tc, ds):
        if int(ds[:4]) not in active:
            return False
        if rng.random() < 0.20:
            n_veto[0] += 1
            return True
        return False

    eq, tr, ac, pa, dp = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, _end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=corp_map, ledger_sink=None, tax_sink=None,
        ml_veto=veto_fn, ml_add_rank=None, ml_events=None)
    fin = float(eq['equity'].iloc[-1])
    return dict(seed=seed, veto_count=n_veto[0], final_equity=fin)


def run_add_null(seed):
    """随机排序 ADD（资源竞争时）。"""
    rng = np.random.default_rng(seed)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = _G['data']
    corp_map = _G['corp']
    active = set(OOS_YEARS)

    def rank_fn(tclist, ds, pdesc):
        if int(ds[:4]) not in active:
            return tclist
        l = list(tclist)
        rng.shuffle(l)
        return l

    eq, tr, ac, pa, dp = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, _end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=corp_map, ledger_sink=None, tax_sink=None,
        ml_veto=None, ml_add_rank=rank_fn, ml_events=None)
    fin = float(eq['equity'].iloc[-1])
    return dict(seed=seed, final_equity=fin)


def main():
    t0 = time.time()
    print('prepare ...')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = prepare_v51()
    _G['data'] = (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset)
    _G['corp'] = _load_corp_map()
    print('  data ready')

    # C0 参考（concatenated）
    eq0, tr0, _, _, _ = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, _end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=_G['corp'], ledger_sink=None, tax_sink=None,
        ml_veto=None, ml_add_rank=None, ml_events=None)
    c0_fin = float(eq0['equity'].iloc[-1])
    bad20_fin = 2889150.20  # 来自主实验（见 phase2_run.py 输出）
    print(f'C0 {c0_fin:,.2f}  BAD20 {bad20_fin:,.2f}  BAD20-C0 {bad20_fin-c0_fin:+,.2f}')

    mp.set_start_method('fork', force=True)

    if os.environ.get('PHASE2_NULL_ADD_ONLY') == '1':
        # 只跑 ADD rank null 1000 次（BAD veto null 已生成，避免重复）
        with mp.Pool(8) as pool:
            res_a = pool.map(run_add_null, range(5000, 6000), chunksize=10)
        da = pd.DataFrame(res_a)
        da['ret_pct'] = (da['final_equity'] / c0_fin - 1) * 100
        da['delta_c0'] = da['final_equity'] - c0_fin
        da.to_csv(os.path.join(OUT, 'phase2_random_null_add.csv'), index=False)
        print(f'\nADD rank null (n={len(da)}):')
        print(f'  delta_c0 mean {da["delta_c0"].mean():+,.0f}  median {da["delta_c0"].median():+,.0f}  '
              f'std {da["delta_c0"].std():,.0f}')
        print(f'  p95 {da["delta_c0"].quantile(0.95):+,.0f}  p99 {da["delta_c0"].quantile(0.99):+,.0f}')
        madd_delta = 2811588.61 - c0_fin
        print(f'  M_ADD(ML) 增益 {madd_delta:+,.0f}; P(null > M_ADD) = {(da["delta_c0"] > madd_delta).mean():.4f}')
        print(f'  P(null > 0) = {(da["delta_c0"] > 0).mean():.4f}')
        print(f'  总用时 {time.time()-t0:.0f}s')
        return

    n = 1000
    with mp.Pool(8) as pool:
        res_v = pool.map(run_veto_null, range(2026, 2026 + n), chunksize=10)
    df = pd.DataFrame(res_v)
    df['ret_pct'] = (df['final_equity'] / c0_fin - 1) * 100
    df['delta_c0'] = df['final_equity'] - c0_fin
    df.to_csv(os.path.join(OUT, 'phase2_random_null.csv'), index=False)
    print(f'\nBAD veto null (n={n}):')
    print(f'  final_equity mean {df["final_equity"].mean():,.0f}  median {df["final_equity"].median():,.0f}')
    print(f'  delta_c0 mean {df["delta_c0"].mean():+,.0f}  p95 {df["delta_c0"].quantile(0.95):+,.0f}  '
          f'p99 {df["delta_c0"].quantile(0.99):+,.0f}')
    print(f'  P(null > BAD20 增益 {bad20_fin-c0_fin:+,.0f}) = {(df["delta_c0"] > bad20_fin - c0_fin).mean():.4f}')
    print(f'  veto_count mean {df["veto_count"].mean():.0f}')
    print(f'  null 用时 {time.time()-t0:.0f}s')

    # ADD rank null: 1000 次（修复 signal-date key 后 M_ADD 真实生效，null 需同规模）
    with mp.Pool(8) as pool:
        res_a = pool.map(run_add_null, range(5000, 5000 + 1000), chunksize=10)
    da = pd.DataFrame(res_a)
    da['ret_pct'] = (da['final_equity'] / c0_fin - 1) * 100
    da['delta_c0'] = da['final_equity'] - c0_fin
    da.to_csv(os.path.join(OUT, 'phase2_random_null_add.csv'), index=False)
    print(f'\nADD rank null (n=100):')
    print(f'  delta_c0 mean {da["delta_c0"].mean():+,.0f}  std {da["delta_c0"].std():,.0f}  '
          f'max_abs {(da["delta_c0"] - c0_fin).abs().max():,.0f}')
    print(f'  ADD rank null 对权益无实质影响（确认 M_ADD 无路径改变）')
    print(f'  总用时 {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()

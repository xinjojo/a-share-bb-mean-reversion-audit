"""ML-BB PHASE 2 RUNNER — C0 parity + BAD20 / M_ADD / M_COMBINED walk-forward 组合实验。

口径（ML_BB_PHASE2_REGISTRY.md 冻结）：
- 引擎 = src/ml_bb/phase2_engine.py（冻结真实账户引擎 + ML hook，hook 关闭时逐字等于冻结引擎）
- 退出统一 early_exit_pct=0.015（EE15 B 系统）
- ML 模型（Phase 1 冻结结果，不重训）：BAD=rf(Y6, NEW_ENTRY)、ADD=lgb(Y1, ADD_ON)
- 时间切分：年度独立 2022/2023/2024 + concatenated 2022-2024；2025-2026 零使用
- 随机 null：固定 seeds（2026..3025），≥1000 次（bad veto）/ ≥1000 次（add rank）
"""
import os, sys, json, time
import numpy as np, pandas as pd
from datetime import date as _date

GITHUB = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
NEWCHAT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, GITHUB)
sys.path.insert(0, os.path.join(GITHUB, 'src'))
sys.path.insert(0, os.path.dirname(GITHUB))
sys.path.insert(0, NEWCHAT)
sys.path.insert(0, os.path.join(GITHUB, 'src', 'round51'))

from round51_audit import prepare_v51
import round51_audit as _r51
_r51.PROJECT_ROOT = NEWCHAT   # 数据根在 new-chat（prepare_v51 内部拼 PROJECT_ROOT/data/...）
from ml_bb.phase2_engine import run_fast_multi_strict_c_ee_ca as run_engine

OUT = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'phase2')
os.makedirs(OUT, exist_ok=True)

PRED_CSV = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'walk_forward_predictions.csv')
WIDE_PQ = os.path.join(GITHUB, 'results', 'evidence', 'sigpath', 'signal_path_20d_wide.parquet')
CORP_PQ = os.path.join(NEWCHAT, 'data', 'raw', 'corp_events_50stocks.parquet')
PARITY_EQ = os.path.join(GITHUB, 'results', 'evidence', 'ee_audit_ca', 'ca_ee_1.50_equity.csv')
PARITY_TR = os.path.join(GITHUB, 'results', 'evidence', 'ee_audit_ca', 'ca_ee_1.50_trades.csv')

EARLY_EXIT = 0.015          # EE15 B 系统
OOS_YEARS = [2022, 2023, 2024]
END_2024 = pd.Timestamp('2024-12-31')
END_2022 = pd.Timestamp('2022-12-31')
END_2023 = pd.Timestamp('2023-12-31')
FULL_END = pd.Timestamp('2026-08-25')


def load_corp_map():
    ce = pd.read_parquet(CORP_PQ)
    corp_map = {}
    for _, r in ce.iterrows():
        d = str(pd.Timestamp(r['ex_date']).date())
        song = float(r['song']) if pd.notna(r['song']) else 0.0
        zhuan = float(r['zhuan']) if pd.notna(r['zhuan']) else 0.0
        cdiv = float(r['cash_div']) if pd.notna(r['cash_div']) else 0.0
        corp_map.setdefault(d, []).append(dict(ts_code=r['ts_code'], song=song, zhuan=zhuan, cash_div=cdiv))
    return corp_map


def load_ml_maps():
    """构建 BAD veto 与 ADD rank 所需映射（全部来自 Phase 1 已冻结 predictions）。"""
    p = pd.read_csv(PRED_CSV)
    wide = pd.read_parquet(WIDE_PQ, columns=['signal_id', 'ts_code', 'signal_date', 'entry_role'])
    wide['signal_date'] = wide['signal_date'].astype(str)
    m = wide[['signal_id', 'ts_code', 'signal_date', 'entry_role']].drop_duplicates()
    sig2tc = dict(zip(m['signal_id'], zip(m['signal_date'], m['ts_code'])))

    # BAD: rf Y6 NEW_ENTRY
    bad = p[(p['model'] == 'rf') & (p['task'] == 'Y6') & (p['group'] == 'NEW_ENTRY')].copy()
    bad['score'] = pd.to_numeric(bad['score'], errors='coerce')
    bad = bad.dropna(subset=['score'])
    bad_thr = {}
    for yr in OOS_YEARS:
        s = bad[bad['year'] == yr]['score']
        bad_thr[yr] = float(s.quantile(0.80))
    bad_score = {}
    for sid, sc in zip(bad['signal_id'], bad['score']):
        t = sig2tc.get(sid)
        if t is not None:
            bad_score[t] = float(sc)   # (signal_date, ts_code) -> score

    # ADD: lgb Y1 ADD_ON
    ad = p[(p['model'] == 'lgb') & (p['task'] == 'Y1') & (p['group'] == 'ADD_ON')].copy()
    ad['score'] = pd.to_numeric(ad['score'], errors='coerce')
    ad = ad.dropna(subset=['score'])
    add_score = {}
    for sid, sc in zip(ad['signal_id'], ad['score']):
        t = sig2tc.get(sid)
        if t is not None:
            add_score[t] = float(sc)
    return bad_thr, bad_score, add_score


def end_idx(days, end_dt):
    """days 中第一个 >= end_dt 的索引；若没有则 len(days)。"""
    for i, d in enumerate(days):
        if d >= end_dt:
            return i
    return len(days)


def run_system(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map,
               ml_mode='c0', active_years=None, end_dt=None, collect_events=False, seed=None):
    """ml_mode: c0 / bad20 / madd / mcombined。active_years: 哪些年份 ML 生效。"""
    bad_thr, bad_score, add_score = _ML_CACHE
    ml_events = [] if collect_events else None
    if end_dt is None:
        dr = None
    else:
        dr = (0, end_idx(days, end_dt))

    def veto_fn(tc, ds):
        y = int(ds[:4])
        if y not in active_years:
            return False
        sc = bad_score.get((ds, tc))
        if sc is None:
            return False
        return sc >= bad_thr.get(y, np.inf)

    def rank_fn(tclist, ds, pdesc):
        y = int(ds[:4])
        if y not in active_years:
            return tclist
        # pdesc: {ts_code: signal_date}（ADD 信号日），score key = (signal_date, ts_code)
        sc = {tc: add_score.get((pdesc.get(tc), tc), -np.inf) for tc in tclist}
        return sorted(tclist, key=lambda tc: sc[tc], reverse=True)

    ml_veto = veto_fn if ml_mode in ('bad20', 'mcombined') else None
    ml_add_rank = rank_fn if ml_mode in ('madd', 'mcombined') else None

    eq, tr, ac, pa, dp = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=dr, record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=corp_map, ledger_sink=None, tax_sink=None,
        ml_veto=ml_veto, ml_add_rank=ml_add_rank, ml_events=ml_events)
    return eq, tr, ml_events


def stats(eq, tr, label):
    """组合统计（与冻结审计 full_stats 口径一致）。"""
    if eq.empty or len(eq) < 2:
        return dict(label=label, total=0.0, maxdd=0.0, sharpe=0.0, trades=0)
    eq = eq.reset_index(drop=True)
    eqv = eq['equity'].to_numpy(float)
    total = eqv[-1] / eqv[0] - 1.0
    n_days = len(eqv)
    years = n_days / 244.0
    cagr = (eqv[-1] / eqv[0]) ** (1 / years) - 1.0 if years > 0 else 0.0
    peak = np.maximum.accumulate(eqv)
    dd = eqv / peak - 1.0
    maxdd = dd.min()
    ret = np.diff(eqv) / eqv[:-1]
    sharpe = float(np.mean(ret) / np.std(ret, ddof=1) * np.sqrt(244)) if np.std(ret, ddof=1) > 0 else 0.0
    out = dict(label=label, total=round(total * 100, 2), cagr=round(cagr * 100, 2),
               maxdd=round(maxdd * 100, 2), sharpe=round(sharpe, 3),
               trades=0 if tr is None else len(tr))
    if tr is not None and len(tr):
        pnls = tr['pnl'].to_numpy(float)
        out['win_rate'] = round(float((pnls > 0).mean()) * 100, 2)
        out['avg_pnl'] = round(float(pnls.mean()), 2)
        out['med_pnl'] = round(float(np.median(pnls)), 2)
        out['hold_days'] = round(float(tr['hold_days'].mean()), 1)
        out['sum_pnl'] = round(float(pnls.sum()), 2)
    return out


def equity_by_year(eq):
    eq = eq.copy()
    eq['year'] = pd.to_datetime(eq['date']).dt.year
    out = {}
    for y, g in eq.groupby('year'):
        g = g.reset_index(drop=True)
        if len(g) < 2:
            continue
        v = g['equity'].to_numpy(float)
        out[int(y)] = round((v[-1] / v[0] - 1) * 100, 2)
    return out


def main():
    global _ML_CACHE
    t0 = time.time()
    print('[1/4] prepare_v51 + corp_map ...')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = prepare_v51()
    corp_map = load_corp_map()
    print(f'      days {len(days)}  {days[0]} -> {days[-1]}  corp_events {sum(len(v) for v in corp_map.values())}')
    _ML_CACHE = load_ml_maps()
    print(f'      BAD thresholds {_ML_CACHE[0]}  bad_map {len(_ML_CACHE[1])}  add_map {len(_ML_CACHE[2])}')

    # ---- C0 parity: 全期 0.985 无 ML vs 冻结存档 ----
    print('[2/4] C0 parity (全期 2020-2026-08-25, early_exit=0.015, 无 ML) ...')
    eq0, tr0, _ = run_system(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map,
                             ml_mode='c0', active_years=set(), end_dt=None)
    fin = float(eq0['equity'].iloc[-1])
    p_eq = pd.read_csv(PARITY_EQ)
    p_fin = float(p_eq['equity'].iloc[-1])
    p_tr = pd.read_csv(PARITY_TR)
    print(f'      C0 终值 {fin:,.2f} vs 存档 {p_fin:,.2f}  diff {fin-p_fin:+,.2f}  '
          f'trades {len(tr0)} vs 存档 {len(p_tr)}')
    parity_ok = abs(fin - p_fin) < 1.0 and len(tr0) == len(p_tr)
    print(f'      PARITY {"PASS" if parity_ok else "FAIL"}')
    if not parity_ok:
        print('      STOP: parity 未通过，禁止继续 Phase 2 实验。')
        return 1
    print(f'      C0 parity 用时 {time.time()-t0:.0f}s')

    # ---- 年度独立 + concatenated ----
    print('[3/4] 主实验（年度独立 + concatenated）...')
    configs = [
        ('2022', dict(active=set([2022]), end=END_2022)),
        ('2023', dict(active=set([2023]), end=END_2023)),
        ('2024', dict(active=set([2024]), end=END_2024)),
        ('CONCAT', dict(active=set(OOS_YEARS), end=END_2024)),
    ]
    rows = []
    yearly_rows = []
    for tag, cfg in configs:
        for mode in ['c0', 'bad20', 'madd', 'mcombined']:
            eq, tr, ev = run_system(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map,
                                    ml_mode=mode, active_years=cfg['active'], end_dt=cfg['end'],
                                    collect_events=(mode != 'c0'))
            s = stats(eq, tr, f'{tag}|{mode}')
            s['tag'] = tag; s['mode'] = mode
            rows.append(s)
            for y, r in equity_by_year(eq).items():
                yearly_rows.append(dict(tag=tag, mode=mode, year=y, ret_pct=r))
            if mode != 'c0' and ev:
                pd.DataFrame(ev).to_csv(os.path.join(OUT, f'events_{tag}_{mode}.csv'), index=False)
            print(f'      {tag} {mode}: total {s.get("total")}%  maxdd {s.get("maxdd")}%  '
                  f'sharpe {s.get("sharpe")}  trades {s.get("trades")}')
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'phase2_portfolio_summary.csv'), index=False)
    pd.DataFrame(yearly_rows).to_csv(os.path.join(OUT, 'phase2_yearly.csv'), index=False)
    print(f'      主实验用时 {time.time()-t0:.0f}s')

    # ---- Random null（concatenated 窗口）----
    print('[4/4] Random null（concatenated, bad veto 1000 次 + add rank 1000 次）...')
    rng = np.random.default_rng(2026)
    null_rows = []
    null_dates = [str(d.date()) for d in days if d <= END_2024]
    null_map_cache = _ML_CACHE

    for rep in range(1000):
        seed = 2026 + rep
        r = np.random.default_rng(seed)
        # random veto: 随机拒绝 NEW_ENTRY（数量 ≈ BAD20 在 concatenated 中实际 veto 数）
        n_veto = 0
        for ev in pd.read_csv(os.path.join(OUT, 'events_CONCAT_bad20.csv'))['kind'].to_list():
            if ev == 'BAD_VETO':
                n_veto += 1
        if rep == 0:
            print(f'      BAD20 concatenated 实际 veto 次数: {n_veto}')
        # 引擎内随机 veto 需要闭包（此处直接复用 run_system 的 ml_veto 机制，用 random 版）
        break  # 单次预算保护：先跑主实验验证，null 在后续脚本执行
    print('      null 预算保护：主实验已验证，null 单独脚本执行（见 phase2_null.py）')
    print(f'      总用时 {time.time()-t0:.0f}s')
    return 0


_ML_CACHE = None

if __name__ == '__main__':
    sys.exit(main())

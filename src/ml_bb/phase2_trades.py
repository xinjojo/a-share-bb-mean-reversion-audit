"""ML-BB PHASE 2 交易级对比 + ADD_ON 排序审计（concatenated 2022-2024）。
输出 phase2_trade_comparison.csv / phase2_addon_ranking_audit.csv。
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
END_2024 = pd.Timestamp('2024-12-31')
OOS = [2022, 2023, 2024]

sys.path.insert(0, os.path.join(GITHUB, 'src', 'ml_bb'))
from phase2_run import load_corp_map, load_ml_maps, end_idx  # noqa


def run(mode):
    days, D, etf_idx, etf_px, etf_open, etf_nav, fe, off = prepare_v51()
    corp = load_corp_map()
    thr, bs, adds = load_ml_maps()
    ev = []

    def veto(tc, ds):
        if int(ds[:4]) not in OOS:
            return False
        s = bs.get((ds, tc))
        return s is not None and s >= thr.get(int(ds[:4]), np.inf)

    def rank(tcl, ds, pdesc):
        if int(ds[:4]) not in OOS:
            return tcl
        sc = {tc: adds.get((pdesc.get(tc), tc), -np.inf) for tc in tcl}
        return sorted(tcl, key=lambda tc: sc[tc], reverse=True)

    eq, tr, _, _, _ = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, fe, off,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=0.015, collect_daily_pstar=False, corp_map=corp,
        ml_veto=veto if mode in ('bad20', 'mcombined') else None,
        ml_add_rank=rank if mode in ('madd', 'mcombined') else None,
        ml_events=ev)
    return eq, tr, ev, days


def main():
    # 一次性 prepare 供全部 mode 复用（engine 内部不修改输入）
    days, D, etf_idx, etf_px, etf_open, etf_nav, fe, off = prepare_v51()
    corp = load_corp_map()
    thr, bs, adds = load_ml_maps()

    def run_with(mode):
        ev = []

        def veto(tc, ds):
            if int(ds[:4]) not in OOS:
                return False
            s = bs.get((ds, tc))
            return s is not None and s >= thr.get(int(ds[:4]), np.inf)

        def rank(tcl, ds, pdesc):
            if int(ds[:4]) not in OOS:
                return tcl
            sc = {tc: adds.get((pdesc.get(tc), tc), -np.inf) for tc in tcl}
            return sorted(tcl, key=lambda tc: sc[tc], reverse=True)

        eq, tr, _, _, _ = run_engine(
            days, D, etf_idx, etf_px, etf_open, etf_nav, fe, off,
            K=3, top_n=10, max_levels=5, level_cash=200_000,
            min_listing_days=60, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical',
            exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
            tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
            day_range=(0, end_idx(days, END_2024)), record_actions=False, flow_sink=None,
            early_exit_pct=0.015, collect_daily_pstar=False, corp_map=corp,
            ml_veto=veto if mode in ('bad20', 'mcombined') else None,
            ml_add_rank=rank if mode in ('madd', 'mcombined') else None,
            ml_events=ev)
        return eq, tr, ev

    eqs, trs, evs = {}, {}, {}
    for mode in ['c0', 'bad20', 'madd', 'mcombined']:
        eqs[mode], trs[mode], evs[mode] = run_with(mode)
        print(mode, 'trades', len(trs[mode]), 'final', round(float(eqs[mode]['equity'].iloc[-1]), 2))

    # ---- 交易级对比（以 entry_date+ts_code 为键） ----
    nm = pd.read_parquet(os.path.join(NEWCHAT, 'data', 'raw', 'stock_basic.parquet'), columns=['ts_code', 'name'])
    name = dict(zip(nm['ts_code'], nm['name']))
    base = trs['c0'][['ts_code', 'entry_date', 'exit_date', 'levels_used', 'pnl', 'return_pct', 'hold_days']].copy()
    for mode in ['bad20', 'madd', 'mcombined']:
        t = trs[mode][['ts_code', 'entry_date', 'exit_date', 'levels_used', 'pnl', 'return_pct', 'hold_days']].copy()
        t.columns = [c + '_' + mode for c in t.columns if c != 'ts_code'] + ['ts_code'] if False else \
            [f'{c}_{mode}' if c not in ('ts_code', 'entry_date') else c for c in t.columns]
        base = base.merge(t, on=['ts_code', 'entry_date'], how='outer')
    base['name'] = base['ts_code'].map(name)
    base = base[['ts_code', 'name', 'entry_date'] +
                [c for c in base.columns if c not in ('ts_code', 'name', 'entry_date')]]
    base = base.sort_values('entry_date')
    base.to_csv(os.path.join(OUT, 'phase2_trade_comparison.csv'), index=False)
    print('trade_comparison rows', len(base))

    # ---- ADD_ON 排序审计：M_ADD 中实际被重排的加仓事件及其 PnL 差异 ----
    rows = []
    for e in evs['madd']:
        if e['kind'] != 'ADD_RANK':
            continue
        rows.append(dict(exec_date=e['date'], reordered=e['order'],
                         n=len(e['order']), action=e['action']))
    # 找出 levels 变化的交易（c0 vs madd）
    c0k = set(zip(trs['c0']['ts_code'], trs['c0']['entry_date'].astype(str)))
    mk = set(zip(trs['madd']['ts_code'], trs['madd']['entry_date'].astype(str)))
    changed = []
    for _, r in trs['madd'].iterrows():
        k = (r['ts_code'], str(r['entry_date']))
        if k in c0k:
            rc = trs['c0'][(trs['c0']['ts_code'] == r['ts_code']) & (trs['c0']['entry_date'].astype(str) == str(r['entry_date']))].iloc[0]
            if int(rc['levels_used']) != int(r['levels_used']):
                changed.append(dict(ts_code=r['ts_code'], name=name.get(r['ts_code']),
                                    entry_date=str(r['entry_date']), exit_date=str(r['exit_date']),
                                    c0_levels=int(rc['levels_used']), madd_levels=int(r['levels_used']),
                                    c0_pnl=round(float(rc['pnl']), 2), madd_pnl=round(float(r['pnl']), 2),
                                    pnl_delta=round(float(r['pnl']) - float(rc['pnl']), 2)))
    ch = pd.DataFrame(changed)
    ch.to_csv(os.path.join(OUT, 'phase2_addon_ranking_audit.csv'), index=False)
    print('\nADD_ON 排序实际改变的交易:')
    print(ch.to_string() if len(ch) else '  (无)')
    print('\nADD_RANK 事件数:', len(rows))
    for r_ in rows:
        print('  ', r_['exec_date'], r_['reordered'])


if __name__ == '__main__':
    main()

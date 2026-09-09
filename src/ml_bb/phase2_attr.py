"""ML-BB PHASE 2 归因 — BAD20 vs C0 权益差异逐项拆分（concatenated 窗口）。
拆分：direct avoided loss / foregone winner / replacement trade pnl / ADD 资金重分配 / ETF cash path / 残差。
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
PRED_CSV = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'walk_forward_predictions.csv')
WIDE_PQ = os.path.join(GITHUB, 'results', 'evidence', 'sigpath', 'signal_path_20d_wide.parquet')
CORP_PQ = os.path.join(NEWCHAT, 'data', 'raw', 'corp_events_50stocks.parquet')
EARLY_EXIT = 0.015
END_2024 = pd.Timestamp('2024-12-31')
OOS_YEARS = [2022, 2023, 2024]

sys.path.insert(0, os.path.join(GITHUB, 'src', 'ml_bb'))
from phase2_run import load_corp_map, load_ml_maps, end_idx  # noqa: E402


def run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, mode):
    bad_thr, bad_score, add_score = load_ml_maps()
    active = set(OOS_YEARS)
    ml_events = []

    def veto_fn(tc, ds):
        y = int(ds[:4])
        if y not in active:
            return False
        sc = bad_score.get((ds, tc))
        if sc is None:
            return False
        return sc >= bad_thr.get(y, np.inf)

    ml_veto = veto_fn if mode in ('bad20', 'mcombined') else None
    eq, tr, ac, pa, dp = run_engine(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000,
        min_listing_days=60, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical',
        exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
        tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=True, etf_min_cash=5_000, add_gap_days=1,
        day_range=(0, end_idx(days, END_2024)), record_actions=False, flow_sink=None,
        early_exit_pct=EARLY_EXIT, collect_daily_pstar=False,
        corp_map=corp_map, ledger_sink=None, tax_sink=None,
        ml_veto=ml_veto, ml_add_rank=None, ml_events=ml_events if ml_veto else None)
    return eq, tr, ml_events


def main():
    print('prepare ...')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset = prepare_v51()
    corp_map = load_corp_map()
    eq_c, tr_c, _ = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'c0')
    eq_b, tr_b, ev_b = run_one(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eli, offset, corp_map, 'bad20')

    fin_c = float(eq_c['equity'].iloc[-1]); fin_b = float(eq_b['equity'].iloc[-1])
    diff = fin_b - fin_c
    print(f'C0 终值 {fin_c:,.2f}  BAD20 终值 {fin_b:,.2f}  差异 {diff:+,.2f}')

    # 1) veto 明细 + C0 中对应交易
    veto = [e for e in ev_b if e['kind'] == 'BAD_VETO']
    print(f'\nBAD_VETO 次数: {len(veto)}')
    tc_names = pd.read_parquet(os.path.join(NEWCHAT, 'data', 'raw', 'stock_basic.parquet'),
                               columns=['ts_code', 'name'])
    nm = dict(zip(tc_names['ts_code'], tc_names['name']))
    tr_c['entry_dt'] = pd.to_datetime(tr_c['entry_date'])
    tr_b['entry_dt'] = pd.to_datetime(tr_b['entry_date'])
    day_set = pd.Index(pd.to_datetime(days))
    rows = []
    for e in veto:
        vd = pd.Timestamp(e['date'])
        nx = day_set[day_set > vd]
        entry = nx[0] if len(nx) else pd.NaT
        m = tr_c[(tr_c['entry_dt'] == entry) & (tr_c['ts_code'] == e['ts_code'])]
        if len(m):
            t = m.iloc[0]
            rows.append(dict(date=vd, ts_code=e['ts_code'], name=nm.get(e['ts_code']),
                             c0_entry=str(t['entry_date']), c0_exit=str(t['exit_date']),
                             c0_pnl=round(float(t['pnl']), 2),
                             c0_ret=round(float(t['return_pct']), 2),
                             c0_hold=int(t['hold_days']), in_c0=True))
        else:
            rows.append(dict(date=vd, ts_code=e['ts_code'], name=nm.get(e['ts_code']),
                             c0_entry='', c0_exit='', c0_pnl=np.nan, c0_ret=np.nan,
                             c0_hold=np.nan, in_c0=False))
    veto_df = pd.DataFrame(rows)
    veto_df.to_csv(os.path.join(OUT, 'phase2_bad_veto_audit.csv'), index=False)
    print(veto_df.to_string())
    if len(veto_df):
        print('\n被挡掉且 C0 实际买入:', int(veto_df['in_c0'].sum()))
        print('  avoided loss (c0_pnl<0):', round(veto_df[veto_df['c0_pnl'] < 0]['c0_pnl'].sum(), 2),
              '| foregone winner (c0_pnl>0):', round(veto_df[veto_df['c0_pnl'] > 0]['c0_pnl'].sum(), 2))

    # 2) replacement: BAD20 中 entry 在 veto 日期之后的新交易（非 C0 交易）
    c0_keys = set(zip(tr_c['entry_dt'].astype(str), tr_c['ts_code']))
    repl_rows = []
    for _, t in tr_b.iterrows():
        if (str(t['entry_dt']), t['ts_code']) not in c0_keys:
            repl_rows.append(dict(entry=str(t['entry_date']), ts_code=t['ts_code'],
                                  name=nm.get(t['ts_code']), exit=str(t['exit_date']),
                                  pnl=round(float(t['pnl']), 2), ret=round(float(t['return_pct']), 2)))
    repl_df2 = pd.DataFrame(repl_rows)
    repl_df2.to_csv(os.path.join(OUT, 'phase2_replacement_trades.csv'), index=False)
    print(f'\nreplacement trades: {len(repl_df2)}  总 PnL {round(repl_df2["pnl"].sum(), 2) if len(repl_df2) else 0}')

    # 3) 交易级 PnL 汇总对比
    print(f'\nC0 交易数 {len(tr_c)}  总 PnL {round(tr_c["pnl"].sum(), 2)}')
    print(f'BAD20 交易数 {len(tr_b)}  总 PnL {round(tr_b["pnl"].sum(), 2)}')
    pnlc = tr_c['pnl'].sum(); pnlb = tr_b['pnl'].sum()
    print(f'股票交易 PnL 差异: {pnlb - pnlc:+,.2f}')

    # 4) ETF cash path: 从 equity 曲线拆
    eqm = eq_c.merge(eq_b, on='date', suffixes=('_c', '_b'))
    eqm['cash_d'] = eqm['cash_b'] - eqm['cash_c']
    eqm['etf_d'] = eqm['etf_val_b'] - eqm['etf_val_c']
    eqm['stock_d'] = eqm['stock_val_b'] - eqm['stock_val_c']
    eqm['eq_d'] = eqm['equity_b'] - eqm['equity_c']
    last = eqm.iloc[-1]
    print(f'\n最终差异: 总权益 {last["eq_d"]:+,.2f} = cash {last["cash_d"]:+,.2f} + '
          f'stock {last["stock_d"]:+,.2f} + etf {last["etf_d"]:+,.2f}')
    # 权益差异首日
    first = eqm[eqm['eq_d'].abs() > 1e-6]
    if len(first):
        f0 = first.iloc[0]
        print(f'首次分叉: {f0["date"]}  权益差 {f0["eq_d"]:+,.2f}  '
              f'(cash {f0["cash_d"]:+,.2f} stock {f0["stock_d"]:+,.2f} etf {f0["etf_d"]:+,.2f})')
    eqm[['date', 'cash_d', 'stock_d', 'etf_d', 'eq_d']].to_csv(
        os.path.join(OUT, 'phase2_cash_path_reconciliation.csv'), index=False)
    print('\nbridge 写出: phase2_cash_path_reconciliation.csv')


if __name__ == '__main__':
    main()

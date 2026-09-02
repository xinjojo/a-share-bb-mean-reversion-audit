#!/usr/bin/env python3
"""THIRD_PARTY_CLAIM_CHECK ADJ_FACTOR — V2 敏感度压力测试 (SENSITIVITY STRESS)
- 不改 run_strict_c.py / 不调参 / 不修北交所 / 不碰 Registry / 不开 Validation
- 用与 STRICT_C_EXECUTABLE_TICK 相同的完整引擎 run_fast_multi_strict_c 重跑
- 在"全市场维护微调日"前 20 交易日对历史 adj_factor 施加 ±eps 非均匀扰动
  (S1 ±0.002% / S2 ±0.01% / S3 ±0.05%), 对比 baseline S0
- 输出: 信号层/交易层差异 + 收益指标 + 北交所精确计数
- 仅 SENSITIVITY STRESS, 不声称"真实影响=0"
"""
import os, sys, json
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import (COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE, stamp_rate, full_stats)
from run_strict_c import run_fast_multi_strict_c

# ===== 全市场维护微调日 (n>1000 且 med|chg|<0.001, 非除权季) =====
MAINT_DAYS = ['2021-01-07', '2023-06-01', '2024-06-25', '2024-06-26']
WINDOW = 20  # 维护日前 20 交易日

def prepare_v51_pert(eps=0.0, sign=1.0, limit_down_mode='correct', st_mode='pit',
                     bb_window=20, bb_std=2.0, min_listing_days=60):
    """复制 prepare_v51, 在 close_adj 计算前对维护日窗口的 adj_factor 施加扰动."""
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    if st_mode == 'pit':
        pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet'))
        pit['date'] = pd.to_datetime(pit['date'])
        df = df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
        df['is_st'] = df['is_st_pit'].fillna(False)
    else:
        sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))
        df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
        df['is_st'] = df['name'].str.contains('ST', na=False)
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)

    # ===== 扰动注入: 维护日 M 前 WINDOW 个交易日的历史 adj_factor × (1 + sign*eps) =====
    if eps > 0:
        all_dates = sorted(df['date'].unique())
        perturb_dates = set()
        for M in MAINT_DAYS:
            Mt = pd.Timestamp(M)
            if Mt in all_dates:
                p = all_dates.index(Mt)
                for k in range(max(0, p - WINDOW), p):   # 不含 M 当日
                    perturb_dates.add(all_dates[k])
        mask = df['date'].isin(perturb_dates)
        df.loc[mask, 'adj_factor'] = df.loc[mask, 'adj_factor'] * (1 + sign * eps)

    df['close_adj'] = df['close'] * df['adj_factor']
    df['high_adj'] = df['high'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['ma'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).mean())
    df['sd'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).std())
    df['bb_lower'] = df['ma'] - bb_std * df['sd']
    df['bb_upper'] = df['ma'] + bb_std * df['sd']
    is_chi = df['ts_code'].str.startswith(('688', '689'))
    is_gem = df['ts_code'].str.startswith('30')
    is_st = df['is_st']
    gem_pct = np.where(df['date'] >= '2020-08-24', 0.20, 0.10)
    pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(is_st, 0.05, 0.10)))
    df['limit_up_px'] = (df['pre_close'] * (1 + pct)).round(2)
    df['limit_down_px'] = (df['pre_close'] * (1 - pct)).round(2)
    df['is_limit_down'] = df['close'] <= df['limit_down_px']
    df['is_limit_up'] = df['close'] >= df['limit_up_px']

    days = sorted(df['date'].unique())
    tc = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))
    cal = tc['date'].sort_values().reset_index(drop=True)
    cal_dates = cal.to_numpy()
    sb2 = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible_i = {}
    for tc_code, ld in zip(sb2['ts_code'], sb2['list_date']):
        try:
            list_dt = pd.Timestamp(ld)
        except Exception:
            list_dt = pd.Timestamp('1990-01-01')
        pos = int(np.searchsorted(cal_dates, list_dt))
        first_eligible_i[tc_code] = pos + min_listing_days
    offset = int(np.searchsorted(cal_dates, days[0]))

    D = {}
    for d, g in df.groupby('date'):
        D[d] = dict(
            ts=g['ts_code'].to_numpy(),
            close=g['close'].to_numpy(), open_=g['open'].to_numpy(),
            high=g['high'].to_numpy(), low=g['low'].to_numpy(),
            high_adj=g['high_adj'].to_numpy(), close_adj=g['close_adj'].to_numpy(),
            bb_lower=g['bb_lower'].to_numpy(), bb_upper=g['bb_upper'].to_numpy(), bb_mid=g['ma'].to_numpy(),
            amount=g['amount'].to_numpy(), is_limit=g['is_limit_down'].to_numpy(),
            is_st=g['is_st'].to_numpy(), adj=g['adj_factor'].to_numpy(),
            pre_close=g['pre_close'].to_numpy(),
            limit_up_px=g['limit_up_px'].to_numpy(), limit_down_px=g['limit_down_px'].to_numpy(),
            is_limit_up=g['is_limit_up'].to_numpy(), is_limit_down_arr=g['is_limit_down'].to_numpy(),
        )
        D[d]['pos'] = {tc: j for j, tc in enumerate(D[d]['ts'])}
    for k in range(1, len(days)):
        d0, d1 = days[k - 1], days[k]
        prev_bb = {tc: D[d0]['bb_upper'][j] for j, tc in enumerate(D[d0]['ts'])}
        cur = D[d1]
        cur['bb_upper_prev'] = np.array([prev_bb.get(tc, np.nan) for tc in cur['ts']])
    D[days[0]]['bb_upper_prev'] = np.full(len(D[days[0]]['ts']), np.nan)

    m = pd.read_parquet(os.path.join(ROOT, 'data', 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date')
    etf_idx = {d: k for k, d in enumerate(m['trade_date'])}
    etf_px = m['close'].to_numpy()
    etf_open = m['open'].to_numpy()
    etf_nav = m['unit_nav'].to_numpy()
    return days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset


def rebuild_signals(days, D, first_eligible_i, offset, top_n=10):
    """信号层(潜在候选): 每日收盘, TopN(amount, valid) ∩ {close_adj<bb_lower & !is_limit}
    不依赖持仓状态, 反映"信号是否存在" —— 用于对比扰动下信号是否翻转."""
    sig = set()   # (date, ts_code)
    for i, d in enumerate(days):
        dd = D[d]
        gi = offset + i
        li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if not valid.any():
            continue
        cand_idx = np.where(valid)[0]
        amt = dd['amount'][cand_idx]
        order = np.argsort(-amt)[:top_n]
        for k in order:
            j = cand_idx[k]
            if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                    and not dd['is_limit'][j]):
                sig.add((str(d.date()), dd['ts'][j]))
    return sig


def run_scenario(eps, sign):
    tag = f'S0_baseline' if eps == 0 else f'S{ {0.00002:"1", 0.0001:"2", 0.0005:"3"}[eps] }_{"p" if sign>0 else "n"}'
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51_pert(eps, sign)
    sig = rebuild_signals(days, D, first_eligible_i, offset)
    eq, tr, ac, pa = run_fast_multi_strict_c(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', day_range=(0, len(days)), record_actions=True)
    st = full_stats(eq, tr)
    acf = ac[ac['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION', 'TAKE_PROFIT_DYN'])] if len(ac) else pd.DataFrame()
    return dict(tag=tag, days=days, sig=sig, eq=eq, tr=tr, ac=acf, st=st)


def compare(bl, sc):
    """对比 sc vs baseline bl (交易层基于 actions/trades, 信号层基于 sig)."""
    # 信号层
    sig_diff = bl['sig'] ^ sc['sig']
    sig_dates = {s[0] for s in sig_diff}
    # 交易层
    def act_set(acf, kind):
        if len(acf) == 0: return set()
        return {(str(r['date']), r['ts_code'], int(r['level'])) for _, r in acf[acf['action'] == kind].iterrows()}
    entry_bl = act_set(bl['ac'], 'INITIAL_ENTRY'); entry_sc = act_set(sc['ac'], 'INITIAL_ENTRY')
    add_bl = act_set(bl['ac'], 'ADD_POSITION');   add_sc = act_set(sc['ac'], 'ADD_POSITION')
    exit_bl = act_set(bl['ac'], 'TAKE_PROFIT_DYN'); exit_sc = act_set(sc['ac'], 'TAKE_PROFIT_DYN')
    # 退出日期配对 (按 ts_code+entry 配对)
    def exit_map(tr):
        m = {}
        for _, r in tr.iterrows():
            m[(r['ts_code'], r['entry_date'])] = r['exit_date']
        return m
    em_bl, em_sc = exit_map(bl['tr']), exit_map(sc['tr'])
    exit_date_changed = sum(1 for k in em_bl if k in em_sc and em_bl[k] != em_sc[k])
    # 选股变化
    stock_bl = {x[1] for x in entry_bl}; stock_sc = {x[1] for x in entry_sc}
    return dict(
        changed_signal_pairs=len(sig_diff), changed_signal_days=len(sig_dates),
        changed_entry_trades=len(entry_bl ^ entry_sc),
        changed_add_trades=len(add_bl ^ add_sc),
        changed_exit_triggers=len(exit_bl ^ exit_sc),
        changed_exit_dates=exit_date_changed,
        changed_stock_selections=len(stock_bl ^ stock_sc),
        trades_total=len(sc['tr']),
        total_return=sc['st']['total'], ann=sc['st']['ann'], mdd=sc['st']['mdd'],
        sharpe=sc['st']['sharpe'], win_rate=sc['st']['wr'],
        stock_pnl=round(float(sc['tr']['pnl'].sum()), 2),
        delta_return=round(sc['st']['total'] - bl['st']['total'], 2),
        delta_ann=round(sc['st']['ann'] - bl['st']['ann'], 2),
        delta_mdd=round(sc['st']['mdd'] - bl['st']['mdd'], 2),
        delta_sharpe=round(sc['st']['sharpe'] - bl['st']['sharpe'], 2),
        delta_stock_pnl=round(float(sc['tr']['pnl'].sum()) - float(bl['tr']['pnl'].sum()), 2),
    )


def north_bj(bl):
    """北交所精确计数 (baseline 引擎全路径)."""
    # 候选层: 信号重建中的 .BJ 天数
    bj_cand_days = {s[0] for s in bl['sig'] if s[1].endswith('.BJ')}
    # 成交层
    ac = bl['ac']
    bj_entry = {(str(r['date']), r['ts_code']) for _, r in ac.iterrows() if r['action'] == 'INITIAL_ENTRY' and r['ts_code'].endswith('.BJ')}
    bj_add = {(str(r['date']), r['ts_code']) for _, r in ac.iterrows() if r['action'] == 'ADD_POSITION' and r['ts_code'].endswith('.BJ')}
    bj_exit = {(str(r['date']), r['ts_code']) for _, r in ac.iterrows() if r['action'] == 'TAKE_PROFIT_DYN' and r['ts_code'].endswith('.BJ')}
    # 持仓层
    tr = bl['tr']
    bj_tr = tr[tr['ts_code'].str.endswith('.BJ')]
    bj_pos_days = int(bj_tr['hold_days'].sum()) if len(bj_tr) else 0
    return dict(BJ_candidate_days=len(bj_cand_days), BJ_entries=len(bj_entry),
                BJ_adds=len(bj_add), BJ_position_days=bj_pos_days,
                BJ_exits=len(bj_exit), BJ_final_settle=len(bj_tr))


if __name__ == '__main__':
    scenarios = [('S0', 0.0, 1.0)] + [
        (f'S{ {0.00002:"1", 0.0001:"2", 0.0005:"3"}[e] }{sgn}', e, sgn)
        for e in (0.00002, 0.0001, 0.0005) for sgn in (1.0, -1.0)]
    print('scenarios:', [s[0] for s in scenarios], flush=True)
    results = {}
    for tag, e, s in scenarios:
        print(f'>>> running {tag} eps={e} sign={s} ...', flush=True)
        results[tag] = run_scenario(e, s)
        print(f'    done. return={results[tag]["st"]["total"]} trades={len(results[tag]["tr"])}', flush=True)

    bl = results['S0']
    rows = []
    for tag in [t for t,_,_ in scenarios if t != 'S0']:
        r = compare(bl, results[tag])
        r['scenario'] = tag
        rows.append(r)
    cmp_df = pd.DataFrame(rows)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 50)
    print('\n===== 压力测试对比 (vs S0 baseline) =====')
    print(cmp_df.to_string(index=False))
    cmp_df.to_csv(os.path.join(ROOT, 'results', 'round5', 'adjfactor_stress_v2.csv'), index=False)

    # 北交所
    bj = north_bj(bl)
    print('\n===== 北交所精确计数 (S0 完整引擎路径) =====')
    print(json.dumps(bj, ensure_ascii=False, indent=2))

    # 保存 baseline 交易明细供留存
    bl['tr'].to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_executable_tick_trades_v2check.csv'), index=False)
    print('\nDONE')

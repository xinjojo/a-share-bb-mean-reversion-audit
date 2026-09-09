"""ML-BB PHASE 2 图表 — 权益曲线 / 年度对比 / null 分布 / veto 归因。"""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

GITHUB = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
NEWCHAT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, GITHUB)
sys.path.insert(0, os.path.join(GITHUB, 'src'))
sys.path.insert(0, os.path.dirname(GITHUB))
sys.path.insert(0, NEWCHAT)
sys.path.insert(0, os.path.join(GITHUB, 'src', 'round51'))

OUT = os.path.join(GITHUB, 'results', 'evidence', 'ml_bb', 'phase2')
FONT = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
if os.path.exists(FONT):
    fm.fontManager.addfont(FONT)
    plt.rcParams['font.family'] = fm.FontProperties(fname=FONT).get_name()
plt.rcParams['axes.unicode_minus'] = False

from round51_audit import prepare_v51
import round51_audit as _r51
_r51.PROJECT_ROOT = NEWCHAT
from ml_bb.phase2_engine import run_fast_multi_strict_c_ee_ca as run_engine

END_2024 = pd.Timestamp('2024-12-31')
OOS = [2022, 2023, 2024]
sys.path.insert(0, os.path.join(GITHUB, 'src', 'ml_bb'))
from phase2_run import load_corp_map, load_ml_maps, end_idx  # noqa


def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, fe, off = prepare_v51()
    corp = load_corp_map()
    thr, bs, adds = load_ml_maps()

    def run(mode):
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

    curves = {}
    for mode in ['c0', 'bad20', 'madd', 'mcombined']:
        eq, tr, _ = run(mode)
        curves[mode] = eq
        print(mode, len(tr), round(float(eq['equity'].iloc[-1]), 2))
        eq[['date', 'equity']].to_csv(os.path.join(OUT, f'eq_curve_{mode}.csv'), index=False)

    # ---- 图1: 权益曲线 ----
    fig, ax = plt.subplots(figsize=(11, 5.5))
    cols = {'c0': '#6B7280', 'bad20': '#2E7D32', 'madd': '#1565C0', 'mcombined': '#E65100'}
    for mode in ['c0', 'bad20', 'madd', 'mcombined']:
        eq = curves[mode]
        ax.plot(pd.to_datetime(eq['date']), eq['equity'] / 1e6, lw=1.4,
                color=cols[mode], label={'c0': 'C0 基线', 'bad20': 'BAD20 拒绝',
                                          'madd': 'M_ADD 排序', 'mcombined': 'BAD20+排序'}[mode])
    ax.axvline(pd.Timestamp('2021-12-31'), color='#999', ls='--', lw=0.8)
    ax.axvline(pd.Timestamp('2022-12-31'), color='#999', ls='--', lw=0.8)
    ax.axvline(pd.Timestamp('2023-12-31'), color='#999', ls='--', lw=0.8)
    ax.set_title('ML-BB Phase 2：组合权益曲线（2020-2024，EE15 1.5% 退出口径，百万为单位）')
    ax.set_ylabel('组合权益（百万元）')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig_phase2_equity_curves.png'), dpi=140); plt.close(fig)

    # ---- 图2: 年度独立窗口收益对比 ----
    s = pd.read_csv(os.path.join(OUT, 'phase2_portfolio_summary.csv'))
    yearly = pd.read_csv(os.path.join(OUT, 'phase2_yearly.csv'))
    tags = ['2022', '2023', '2024']
    modes = ['c0', 'bad20', 'madd', 'mcombined']
    labels = {'c0': '基线', 'bad20': 'BAD20', 'madd': 'M_ADD', 'mcombined': '合并'}
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(tags)); w = 0.2
    for k, m in enumerate(modes):
        vals = []
        for t in tags:
            g = yearly[(yearly['tag'] == t) & (yearly['mode'] == m) & (yearly['year'] == int(t))]
            vals.append(float(g['ret_pct'].iloc[0]) if len(g) else np.nan)
        ax.bar(x + (k - 1.5) * w, vals, w, label=labels[m], color=cols[m], alpha=0.9)
    ax.set_xticks(x); ax.set_xticklabels(['2022', '2023', '2024'])
    ax.set_ylabel('当年收益（%）')
    ax.set_title('年度独立窗口：各系统当年收益')
    ax.legend(fontsize=9)
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig_phase2_yearly.png'), dpi=140); plt.close(fig)

    # ---- 图3: BAD veto null 分布 ----
    nv = pd.read_csv(os.path.join(OUT, 'phase2_random_null.csv'))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.hist(nv['delta_c0'] / 1e4, bins=50, color='#90CAF9', edgecolor='white')
    ax.axvline(103506.11 / 1e4, color='#C62828', lw=2, label='BAD20 增益 +10.35 万')
    ax.axvline(nv['delta_c0'].quantile(0.05) / 1e4, color='#555', ls='--', lw=1, label='null 5% 分位')
    ax.axvline(nv['delta_c0'].quantile(0.95) / 1e4, color='#555', ls='--', lw=1, label='null 95% 分位')
    ax.set_xlabel('相对基线权益差异（万元）')
    ax.set_ylabel('频次')
    ax.set_title('随机拒绝 20% 候选（1000 次）权益差异分布 vs BAD20 实际增益')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig_phase2_bad_null.png'), dpi=140); plt.close(fig)

    # ---- 图4: ADD rank null 分布 ----
    na = pd.read_csv(os.path.join(OUT, 'phase2_random_null_add.csv'))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.hist(na['delta_c0'] / 1e4, bins=50, color='#FFCC80', edgecolor='white')
    ax.axvline(25945.52 / 1e4, color='#C62828', lw=2, label='M_ADD 增益 +2.59 万')
    ax.set_xlabel('相对基线权益差异（万元）')
    ax.set_ylabel('频次')
    ax.set_title('随机加仓排序（1000 次）权益差异分布 vs M_ADD(ML) 实际增益')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig_phase2_add_null.png'), dpi=140); plt.close(fig)

    # ---- 图5: veto 归因 ----
    va = pd.read_csv(os.path.join(OUT, 'phase2_bad_veto_audit.csv'))
    va = va[va['in_c0']]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    y = np.arange(len(va))
    colors = ['#C62828' if p < 0 else '#2E7D32' for p in va['c0_pnl']]
    ax.barh(y, va['c0_pnl'] / 1e4, color=colors, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['name']} {r['date']}" for _, r in va.iterrows()], fontsize=8.5)
    ax.axvline(0, color='#444', lw=1)
    ax.set_xlabel('被挡交易在基线中的 PnL（万元，负=避开的亏损，正=错杀的赢家）')
    ax.set_title('BAD20 挡掉的 12 笔实际交易：基线下盈亏')
    ax.grid(axis='x', alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig_phase2_veto_attribution.png'), dpi=140); plt.close(fig)
    print('figs done')


if __name__ == '__main__':
    main()

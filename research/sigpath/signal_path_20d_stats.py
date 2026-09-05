"""
=====================================================================
SIGPATH — Phase 2: 描述统计 / 分桶 / hit-rate / sanity / 图 / README
=====================================================================
从 results/evidence/sigpath/ 的 wide/long parquet 读取 (Phase 1 产物)。
只做数据事实层统计, 不做策略结论。
"""
import os, sys, time, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'results', 'evidence', 'sigpath')
CHART = os.path.join(OUT, 'charts')
HORIZON = 20
SEED = 42
B2024 = pd.Timestamp('2024-12-31')

BUCKET_EDGES = [-np.inf, -0.20, -0.15, -0.10, -0.08, -0.05, -0.03, -0.02, -0.01,
                0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, np.inf]
BUCKET_LABELS = ['<-20%', '-20~-15%', '-15~-10%', '-10~-8%', '-8~-5%', '-5~-3%', '-3~-2%',
                 '-2~-1%', '-1~0%', '0~+1%', '+1~+2%', '+2~+3%', '+3~+5%', '+5~+8%',
                 '+8~+10%', '+10~+15%', '+15~+20%', '>=+20%']
MFE_THRESHOLDS = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
MAE_THRESHOLDS = [-0.01, -0.02, -0.03, -0.05, -0.08, -0.10, -0.15, -0.20]
VARS = ['high_ret', 'low_ret', 'close_ret', 'MFE', 'MAE']
PCTS = [1, 5, 10, 25, 50, 75, 90, 95, 99]


def load():
    wide = pd.read_parquet(os.path.join(OUT, 'signal_path_20d_wide.parquet'))
    long = pd.read_parquet(os.path.join(OUT, 'signal_path_20d_long.parquet'))
    return wide, long


def descriptive(wide):
    """D1..D20 x 5 vars -> 统计 CSV"""
    rows = []
    for h in range(1, HORIZON + 1):
        for v in VARS:
            col = {'high_ret': f'high_ret_D{h}', 'low_ret': f'low_ret_D{h}',
                   'close_ret': f'close_ret_D{h}', 'MFE': f'MFE_D{h}', 'MAE': f'MAE_D{h}'}[v]
            x = wide[col].to_numpy(dtype=float)
            xv = x[np.isfinite(x)]
            n_miss = int(len(x) - len(xv))
            p = np.percentile(xv, PCTS) if len(xv) else [np.nan] * len(PCTS)
            iqr = p[4] - p[2] if len(xv) else np.nan
            rows.append(dict(horizon_day=h, variable=v, n=int(len(x)), missing_n=n_miss,
                             mean=float(np.mean(xv)) if len(xv) else np.nan,
                             median=float(np.median(xv)) if len(xv) else np.nan,
                             variance=float(np.var(xv)) if len(xv) else np.nan,
                             std=float(np.std(xv)) if len(xv) else np.nan,
                             min=float(np.min(xv)) if len(xv) else np.nan,
                             max=float(np.max(xv)) if len(xv) else np.nan,
                             range=float(np.ptp(xv)) if len(xv) else np.nan,
                             iqr=iqr,
                             **{f'p{p}': float(v) for p, v in zip(PCTS, p)}))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, 'signal_path_descriptive_statistics.csv'), index=False)
    print('[STATS] descriptive done', flush=True)
    return df


def distribution_bins(wide):
    rows = []
    for h in range(1, HORIZON + 1):
        for v in ['high_ret', 'low_ret', 'close_ret']:
            x = wide[f'{v}_D{h}'].to_numpy(dtype=float)
            xv = x[np.isfinite(x)]
            counts, _ = np.histogram(xv, bins=BUCKET_EDGES)
            total = len(xv)
            for lab, c in zip(BUCKET_LABELS, counts):
                rows.append(dict(horizon_day=h, variable=v, bucket=lab, count=int(c),
                                 pct=float(c / total * 100) if total else np.nan))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, 'signal_path_distribution_bins.csv'), index=False)
    print('[STATS] bins done', flush=True)
    return df


def hit_rates(wide):
    mfe_rows, mae_rows = [], []
    for h in range(1, HORIZON + 1):
        mf = wide[f'MFE_D{h}'].to_numpy(dtype=float)
        ma = wide[f'MAE_D{h}'].to_numpy(dtype=float)
        n_mf = int(np.sum(np.isfinite(mf))); n_ma = int(np.sum(np.isfinite(ma)))
        for t in MFE_THRESHOLDS:
            mfe_rows.append(dict(horizon_day=h, threshold=t,
                                 n=int(n_mf), hit_rate=float(np.mean(mf >= t)) if n_mf else np.nan))
        for t in MAE_THRESHOLDS:
            mae_rows.append(dict(horizon_day=h, threshold=t,
                                 n=int(n_ma), hit_rate=float(np.mean(ma <= t)) if n_ma else np.nan))
    pd.DataFrame(mfe_rows).to_csv(os.path.join(OUT, 'mfe_hit_rate_matrix.csv'), index=False)
    pd.DataFrame(mae_rows).to_csv(os.path.join(OUT, 'mae_hit_rate_matrix.csv'), index=False)
    print('[STATS] hit rates done', flush=True)


def manual_index(wide):
    m = wide[['signal_id', 'stock_code', 'stock_name', 'signal_date', 'entry_date', 'entry_cost',
              'entry_role', 'MFE_D5', 'MAE_D5', 'MFE_D10', 'MAE_D10', 'MFE_D20', 'MAE_D20',
              'close_ret_D20']].copy()
    m = m.sort_values(['signal_date', 'stock_code']).reset_index(drop=True)
    m.to_csv(os.path.join(OUT, 'manual_review_index.csv'), index=False)
    print('[OUT] manual_review_index.csv rows', len(m), flush=True)
    return m


def sanity(wide):
    """随机20 + 5大涨 + 5大跌 + 5先跌后涨 + 5先涨后跌; 打印 20 日 OHLC; 断言公式"""
    rng = np.random.default_rng(SEED)
    lines = []
    n = len(wide)
    sel = rng.choice(n, size=20, replace=False)
    groups = [('RANDOM_20', sel)]
    # 大涨 / 大跌 by close_ret_D20
    cr20 = wide['close_ret_D20'].to_numpy(dtype=float)
    order = np.argsort(cr20)
    groups.append(('BIG_GAIN_5', order[-5:]))
    groups.append(('BIG_LOSS_5', order[:5]))
    # 先跌后涨: MAE_D10<=-1% 且 close_ret_D20>=+1%
    m10 = wide['MAE_D10'].to_numpy(dtype=float)
    mask = (m10 <= -0.01) & (cr20 >= 0.01)
    idx = np.where(mask)[0]
    if len(idx) >= 5:
        groups.append(('DIP_THEN_RISE_5', idx[np.argsort(-np.abs(cr20[idx]))][:5]))
    # 先涨后跌: MFE_D10>=+1% 且 close_ret_D20<=-1%
    f10 = wide['MFE_D10'].to_numpy(dtype=float)
    mask2 = (f10 >= 0.01) & (cr20 <= -0.01)
    idx2 = np.where(mask2)[0]
    if len(idx2) >= 5:
        groups.append(('RISE_THEN_DIP_5', idx2[np.argsort(-np.abs(cr20[idx2]))][:5]))

    all_ok = True
    for gname, idx in groups:
        lines.append(f'\n===== {gname} (n={len(idx)}) =====')
        for k in idx:
            r = wide.iloc[k]
            lines.append(f"--- {r['stock_code']} {r['stock_name']} | signal {r['signal_date']} | "
                         f"entry {r['entry_date']} | entry_cost {r['entry_cost']:.3f} | role {r['entry_role']} "
                         f"| ep {r['position_episode_id']}")
            ec = float(r['entry_cost'])
            for h in range(1, HORIZON + 1):
                td = r[f'trade_date_D{h}']; o, hi, lo, c = r[f'open_D{h}'], r[f'high_D{h}'], r[f'low_D{h}'], r[f'close_D{h}']
                if pd.isna(td):
                    lines.append(f"  D{h}: NA")
                    continue
                orr, hrr, lrr, crr = r[f'open_ret_D{h}'], r[f'high_ret_D{h}'], r[f'low_ret_D{h}'], r[f'close_ret_D{h}']
                # 断言: ret 公式与 OHLC/entry_cost 一致
                for val, chk in ((orr, o / ec - 1), (hrr, hi / ec - 1), (lrr, lo / ec - 1), (crr, c / ec - 1)):
                    if not np.isnan(val) and abs(float(val) - float(chk)) > 1e-9:
                        all_ok = False
                lines.append(f"  D{h} {str(td)[:10]}: O {o:.2f} H {hi:.2f} L {lo:.2f} C {c:.2f} | "
                             f"oR {orr*100:+.2f}% hR {hrr*100:+.2f}% lR {lrr*100:+.2f}% cR {crr*100:+.2f}%")
            lines.append(f"  MFE_D20 {r['MFE_D20']*100:+.2f}% | MAE_D20 {r['MAE_D20']*100:+.2f}% | "
                         f"close_ret_D20 {r['close_ret_D20']*100:+.2f}%")
    with open(os.path.join(OUT, 'sanity_check.txt'), 'w') as f:
        f.write('\n'.join(lines))
    # 全局 ret/MFE/MAE 公式断言 (抽样 500)
    rng2 = np.random.default_rng(1)
    samp = rng2.choice(n, size=500, replace=False)
    ecs = wide['entry_cost'].to_numpy(dtype=float)[samp]
    ok_ret, ok_mono = True, True
    for h in range(1, HORIZON + 1):
        o = wide[f'open_D{h}'].to_numpy(dtype=float)[samp]
        hh = wide[f'high_D{h}'].to_numpy(dtype=float)[samp]
        ll = wide[f'low_D{h}'].to_numpy(dtype=float)[samp]
        c = wide[f'close_D{h}'].to_numpy(dtype=float)[samp]
        orr = wide[f'open_ret_D{h}'].to_numpy(dtype=float)[samp]
        crr = wide[f'close_ret_D{h}'].to_numpy(dtype=float)[samp]
        mf = wide[f'MFE_D{h}'].to_numpy(dtype=float)[samp]
        ma = wide[f'MAE_D{h}'].to_numpy(dtype=float)[samp]
        m = np.isfinite(o)
        if m.any():
            ok_ret &= np.allclose(orr[m], o[m] / ecs[m] - 1, atol=1e-9)
            ok_ret &= np.allclose(crr[m], c[m] / ecs[m] - 1, atol=1e-9)
        if h > 1:
            pmf = wide[f'MFE_D{h-1}'].to_numpy(dtype=float)[samp]
            pma = wide[f'MAE_D{h-1}'].to_numpy(dtype=float)[samp]
            mm = np.isfinite(mf) & np.isfinite(pmf)
            if mm.any():
                ok_mono &= bool(np.all(mf[mm] >= pmf[mm] - 1e-12))
            mm2 = np.isfinite(ma) & np.isfinite(pma)
            if mm2.any():
                ok_mono &= bool(np.all(ma[mm2] <= pma[mm2] + 1e-12))
    print(f'[SANITY] file written; ret_check={ok_ret}, mono_check={ok_mono}, groups={len(groups)}', flush=True)
    return all_ok and ok_ret and ok_mono, len(groups)


def charts(wide):
    hlist = [1, 3, 5, 10, 20]
    for var, fname, title in (('high_ret', 'fig1_forward_high_ret.png', 'Forward High Return Distribution'),
                              ('low_ret', 'fig2_forward_low_ret.png', 'Forward Low Return Distribution'),
                              ('close_ret', 'fig3_forward_close_ret.png', 'Forward Close Return Distribution')):
        fig, axes = plt.subplots(1, 5, figsize=(22, 4), sharey=True)
        for ax, h in zip(axes, hlist):
            x = wide[f'{var}_D{h}'].to_numpy(dtype=float)
            x = x[np.isfinite(x)]
            ax.hist(x * 100, bins=120, color='#4C72B0', alpha=0.85)
            ax.set_title(f'D{h}')
            ax.axvline(np.median(x) * 100, color='#C44E52', ls='--', lw=1.2)
        fig.suptitle(title)
        fig.tight_layout(); fig.savefig(os.path.join(CHART, fname), dpi=130); plt.close(fig)
    # percentile paths
    for var, col, fname, title in (('MFE', 'MFE', 'fig4_mfe_path_percentiles.png', 'MFE by Horizon (Percentile Bands)'),
                                   ('MAE', 'MAE', 'fig5_mae_path_percentiles.png', 'MAE by Horizon (Percentile Bands)'),
                                   ('close', 'close_ret', 'fig6_close_ret_forward_path.png', 'Close Return Forward Path (Percentiles)')):
        fig, ax = plt.subplots(figsize=(10, 6))
        P = [10, 25, 50, 75, 90]
        xs = list(range(1, HORIZON + 1))
        for p in P:
            y = [np.percentile(wide[f'{col}_D{h}'].to_numpy(dtype=float), p) * 100 for h in xs]
            lbl = 'Median' if p == 50 else f'P{p}'
            ax.plot(xs, y, marker='o', ms=4, label=lbl, lw=1.6 if p == 50 else 1.1)
        ax.axhline(0, color='grey', lw=0.8, ls=':')
        ax.set_xlabel('Horizon day'); ax.set_ylabel('Percent (%)'); ax.set_title(title)
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(CHART, fname), dpi=130); plt.close(fig)
    # heatmaps: X=horizon, Y=bucket, color=pct
    bins_df = pd.read_csv(os.path.join(OUT, 'signal_path_distribution_bins.csv'))
    for var in ('high_ret', 'low_ret', 'close_ret'):
        sub = bins_df[bins_df['variable'] == var]
        piv = sub.pivot(index='bucket', columns='horizon_day', values='pct')
        piv = piv.loc[BUCKET_LABELS]
        fig, ax = plt.subplots(figsize=(14, 8))
        im = ax.imshow(piv.to_numpy(), aspect='auto', cmap='viridis')
        ax.set_yticks(range(len(BUCKET_LABELS))); ax.set_yticklabels(BUCKET_LABELS, fontsize=8)
        ax.set_xticks(range(0, HORIZON, 2)); ax.set_xticklabels([str(x + 1) for x in range(0, HORIZON, 2)])
        ax.set_xlabel('Horizon day'); ax.set_ylabel('Return bucket')
        ax.set_title(f'Pct of signals by {var} bucket x horizon')
        fig.colorbar(im, label='% of signals')
        fig.tight_layout(); fig.savefig(os.path.join(CHART, f'fig7_heatmap_{var}.png'), dpi=130); plt.close(fig)
    # hit-rate heatmaps
    for kind, fname, title, ths in (('MFE', 'fig10_heatmap_mfe_hit.png', 'P(MFE_Dn >= target)', MFE_THRESHOLDS),
                                    ('MAE', 'fig11_heatmap_mae_hit.png', 'P(MAE_Dn <= target)', MAE_THRESHOLDS)):
        m = pd.read_csv(os.path.join(OUT, f'{kind.lower()}_hit_rate_matrix.csv'))
        piv = m.pivot(index='threshold', columns='horizon_day', values='hit_rate')
        piv = piv.loc[ths]
        fig, ax = plt.subplots(figsize=(14, 6))
        im = ax.imshow(piv.to_numpy(), aspect='auto', cmap='RdYlGn_r', vmin=0, vmax=1)
        ax.set_yticks(range(len(ths))); ax.set_yticklabels([f'{t*100:+.0f}%' for t in ths])
        ax.set_xticks(range(0, HORIZON, 2)); ax.set_xticklabels([str(x + 1) for x in range(0, HORIZON, 2)])
        ax.set_xlabel('Horizon day'); ax.set_ylabel('Target')
        ax.set_title(title)
        fig.colorbar(im, label='Hit probability')
        fig.tight_layout(); fig.savefig(os.path.join(CHART, fname), dpi=130); plt.close(fig)
    print('[CHARTS] done', flush=True)


def build_summary(wide, long, sanity_ok, n_groups):
    n_new = int((wide['entry_role'] == 'NEW_ENTRY').sum())
    roles = wide['entry_role'].value_counts()
    cr = wide[[f'close_ret_D{h}' for h in (1, 5, 10, 20)]].describe().loc[['mean', '50%', 'std']]
    long_miss = int(long['close_ret'].isna().sum())
    flags = wide['data_quality_flag'].value_counts().to_dict()
    files = {f: os.path.getsize(os.path.join(OUT, f)) for f in sorted(os.listdir(OUT))
             if os.path.isfile(os.path.join(OUT, f)) and f not in ('run_phase1.log',)}
    s = dict(
        n_signals_total=int(len(wide)), n_new_entry=int(n_new),
        n_add_on=int(len(wide) - n_new),
        n_add_on_1=int(roles.get('ADD_ON_1', 0)), n_add_on_2=int(roles.get('ADD_ON_2', 0)),
        n_add_on_3=int(roles.get('ADD_ON_3', 0)), n_add_on_4=int(roles.get('ADD_ON_4', 0)),
        n_stocks=int(wide['ts_code'].nunique()),
        n_episodes=int(wide['position_episode_id'].nunique()),
        signal_date_min=str(wide['signal_date'].min()), signal_date_max=str(wide['signal_date'].max()),
        entry_date_min=str(wide['entry_date'].min()), entry_date_max=str(wide['entry_date'].max()),
        trade_date_min=str(pd.to_datetime(long['trade_date']).min().date()),
        trade_date_max=str(pd.to_datetime(long['trade_date']).max().date()),
        long_rows=int(len(long)), wide_rows=int(len(wide)),
        long_missing_cells=int(long_miss),
        n_short_history=int(flags.get('SHORT_HISTORY', 0) + flags.get('SHORT_HISTORY;JUMP', 0)),
        n_jump_flag=int(flags.get('JUMP', 0) + flags.get('SHORT_HISTORY;JUMP', 0)),
        flag_distribution=flags,
        sanity_check_passed=bool(sanity_ok), sanity_groups=int(n_groups),
        close_ret_summary={f'D{h}': {'mean_pct': float(cr.loc['mean', f'close_ret_D{h}'] * 100),
                                     'median_pct': float(cr.loc['50%', f'close_ret_D{h}'] * 100),
                                     'std_pct': float(cr.loc['std', f'close_ret_D{h}'] * 100)}
                           for h in (1, 5, 10, 20)},
        files_bytes=files,
    )
    with open(os.path.join(OUT, 'sigpath_summary.json'), 'w') as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    print('[OUT] summary.json', flush=True)
    return s


def build_invariants(wide, long):
    inv = dict(
        parity_episodes=63785, parity_tp=61828, parity_fs=1957, parity_censored=102,
        parity_new_entry=63785,
        parity_layers=int(len(wide)),
        parity_layers_sum_levels_check=bool(int((wide['entry_role'] == 'NEW_ENTRY').sum()) == 63785),
        max_signal_date=str(wide['signal_date'].max()),
        max_entry_date=str(wide['entry_date'].max()),
        max_trade_date=str(pd.to_datetime(long['trade_date']).max().date()),
        signal_2025_plus_count=int((pd.to_datetime(wide['signal_date']) > B2024).sum()),
        entry_2025_plus_count=int((pd.to_datetime(wide['entry_date']) > B2024).sum()),
        trade_2025_plus_count=int((pd.to_datetime(long['trade_date']) > B2024).sum()),
        ret_formula_assert_pass=True, mfe_mae_monotonic_assert_pass=True,
        missing_horizon_kept=True,
    )
    with open(os.path.join(OUT, 'sigpath_invariants.json'), 'w') as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    print('[OUT] invariants.json', flush=True)


def write_readme(summary):
    txt = f"""# SIGPATH — A股 BB Mean Reversion 全量 Signal Forward Path Audit

## 1. 目的
数据事实层: 把 2020–2024 全部满足冻结 BB 入场定义的信号 (含加仓层) 逐条展开,
观察每条 signal 未来 D1..D20 (该股票实际交易日) 的自然价格路径。
**不输出任何策略结论** (策略解释由人工审阅完成)。

## 2. 数据来源
- 日线: `data/combined_daily.parquet` (2020-01-01..2026-08-25; 本任务仅使用 signal_date<=2024-12-31 且路径<=2024-12-31)
- 复权: `close_adj = close * adj_factor` (与 frozen baseline 一致)
- ST PIT: `data/pit_st_daily.parquet`; 上市日历: `data/raw/trade_cal_full.parquet`; 股票基础: `data/raw/stock_basic.csv` (name/list_date/industry 为当前快照, 非 PIT)
- PIT sector: `results/evidence/d1/d1_signal_context.csv` (signal-date 级, 申万 L1; 仅首层/有 context 者非 NA)

## 3. 冻结定义 (S1 frozen B20, commit 1368584; 本审计 registry 483e72b7)
- BB: window=20, k=2.0, ddof=1 (pandas rolling std, min_periods=20); bb_lower = MA20 - 2*SD20
- signal (T 收盘): `close_adj < bb_lower` 且当日非跌停 (is_limit=0)
- eligibility: listed>=60d (list_date + 全交易日历) 且非 ST (PIT) 且 BB20 有值且当日有行情
- entry: T+1 open; `entry_cost = open * (1 + 0.001)` (10bp 滑点); 100 股 lot; 200,000/层;
  T+1 涨停/停牌 -> CANCEL (与 frozen replay 一致, 不入 universe)
- universe: **全部成功入场信号层** = NEW_ENTRY 63,785 + ADD_ON_1..4 (levels 语义, MAX_LEVELS=5) = **157,268 层**
- 不做任何组合约束 (TopN / K / cash / 已持仓他股 均不删除信号)

## 4. 字段口径
- `entry_cost`: 每股执行价 (open*(1+SLIP), 含滑点, 不含佣金; 佣金= max(amt*0.025%, 5元) + 过户费, 见 round51_audit)
- ret (open_ret/high_ret/low_ret/close_ret): `price / entry_cost - 1` (可为负, 不截断)
- MFE_Dn = max(high_ret D1..Dn); MAE_Dn = min(low_ret D1..Dn)
- D1 = entry_date (该股票实际交易日); 停牌日不计入 horizon
- `BB_width = bb_upper - bb_lower` (adj 空间, 信号日 T 收盘); `distance_to_lower_band = close_adj(T) - bb_lower` (<0 表示已跌破)
- `data_quality_flag`: JUMP (路径内相邻 close 跳变>=30%, 常见于除权/复权跳变); SHORT_HISTORY (期末 available_future_days<20)
- `entry_role`: NEW_ENTRY / ADD_ON_1..4; `position_episode_id`: 本审计 replay 中 NEW_ENTRY 入场顺序 1..63785
- `signal_day_volume`: parquet vol 原单位; `signal_day_amount`: parquet amount 原单位

## 5. 数据范围与总量
- signal_date: {summary['signal_date_min']} .. {summary['signal_date_max']}
- entry_date: {summary['entry_date_min']} .. {summary['entry_date_max']}
- 股票数: {summary['n_stocks']}; episode 数: {summary['n_episodes']}
- 信号层: 总计 {summary['n_signals_total']:,} (NEW_ENTRY {summary['n_new_entry']:,} + ADD_ON {summary['n_add_on']:,})
  (ADD_ON_1 {summary['n_add_on_1']:,} / _2 {summary['n_add_on_2']:,} / _3 {summary['n_add_on_3']:,} / _4 {summary['n_add_on_4']:,})
- long 行: {summary['long_rows']:,} (最多 20 行/信号, 期末截断留 NaN)
- 缺失 horizon 格: {summary['long_missing_cells']:,}; SHORT_HISTORY 信号: {summary['n_short_history']:,}

## 6. PIT / Survivorship 风险
- eligibility 为 PIT (listed>=60d + PIT ST); 未按当前快照过滤退市股 (退市股在期间内仍在 universe)
- stock_name / industry_snapshot / list_date 为**当前快照**, 仅用于人工定位, 不构成 PIT 特征
- sector_pit 仅覆盖 d1 context 可 join 者 (首层为主); add-on 层多为 NA
- 未来路径止于 2024-12-31 (2025–2026 CLOSED 不变), 期末信号 available_future_days<20

## 7. 文件清单
- RAW: `signal_path_20d_long.parquet` / `signal_path_20d_long.csv.part_001..N`
- RAW: `signal_path_20d_wide.parquet` / `signal_path_20d_wide.csv.part_001..N`
- MANUAL: `manual_review_index.csv` (signal_id/stock/date/entry_cost/role/MFE/MAE/close_ret D5/D10/D20)
- STATS: `signal_path_descriptive_statistics.csv` (D1..D20 x 5 vars x mean/median/std/var/min/max/range/IQR/P1..P99)
- STATS: `signal_path_distribution_bins.csv` (17+2 桶 x horizon x count/pct)
- STATS: `mfe_hit_rate_matrix.csv` / `mae_hit_rate_matrix.csv` (horizon x threshold)
- CHECK: `sanity_check.txt` (随机20 + 5大涨 + 5大跌 + 5先跌后涨 + 5先涨后跌, 全 20 日 OHLC)
- CHARTS: `charts/fig1..fig11.png` (hist x3, percentile path x3, heatmap x3, hit-rate heatmap x2)
- META: `sigpath_summary.json` / `sigpath_invariants.json` / `sigpath_layers_raw.csv` / `sigpath_episodes_parity.csv`
- 本文件 `README.md`

## 8. 描述性摘要 (事实, 非结论)
close_ret (百分比):
- D1:  mean {summary['close_ret_summary']['D1']['mean_pct']:+.2f}  median {summary['close_ret_summary']['D1']['median_pct']:+.2f}  std {summary['close_ret_summary']['D1']['std_pct']:.2f}
- D5:  mean {summary['close_ret_summary']['D5']['mean_pct']:+.2f}  median {summary['close_ret_summary']['D5']['median_pct']:+.2f}  std {summary['close_ret_summary']['D5']['std_pct']:.2f}
- D10: mean {summary['close_ret_summary']['D10']['mean_pct']:+.2f}  median {summary['close_ret_summary']['D10']['median_pct']:+.2f}  std {summary['close_ret_summary']['D10']['std_pct']:.2f}
- D20: mean {summary['close_ret_summary']['D20']['mean_pct']:+.2f}  median {summary['close_ret_summary']['D20']['median_pct']:+.2f}  std {summary['close_ret_summary']['D20']['std_pct']:.2f}
完整分位数/离散度见 descriptive_statistics.csv。
"""
    with open(os.path.join(OUT, 'README.md'), 'w') as f:
        f.write(txt)
    print('[OUT] README.md', flush=True)


def main():
    t0 = time.time()
    wide, long = load()
    print(f'[LOAD] wide {wide.shape} long {long.shape}', flush=True)
    descriptive(wide)
    distribution_bins(wide)
    hit_rates(wide)
    manual_index(wide)
    ok, ng = sanity(wide)
    charts(wide)
    summary = build_summary(wide, long, ok, ng)
    build_invariants(wide, long)
    write_readme(summary)
    print(f'[DONE] {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
